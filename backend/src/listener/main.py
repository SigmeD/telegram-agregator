"""Telethon listener entry-point — wires SessionManager + reconciliation +
NewMessage handler + graceful shutdown.

Run via container CMD ``listener`` (resolves to ``python -m listener``).
"""

from __future__ import annotations

import asyncio
import signal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select, update
from telethon import TelegramClient, events

from listener.processing import handle_message
from shared.config import get_settings
from shared.db.session import get_engine, get_sessionmaker
from shared.db.tables.telegram_source import TelegramSource
from shared.observability.logging import configure_logging
from shared.telegram.errors import handle_telegram_exception
from shared.telegram.session_manager import SessionManager

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = structlog.get_logger(__name__)

# TODO(Phase 2): move to settings.SESSION_PATH when session rotation lands.
# This path is duplicated in:
#   - infra/compose/docker-compose.yml (volume mount target)
#   - infra/scripts/rotate-session.sh
# Single source of truth needed when rotation/multi-account ships.
SESSION_PATH = Path("/var/lib/tlg/sessions/tlg_aggregator.session.enc")


class _SessionPool:
    """Minimal adapter so ``handle_message`` can call ``pool.session()``.

    ``handle_message`` (Task 4) expects an object exposing ``.session()`` that
    returns an async context manager. ``async_sessionmaker.__call__()`` already
    returns an ``AsyncSession`` usable as an async CM — we just rename it.
    """

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    def session(self) -> AsyncSession:
        return self._sessionmaker()


async def _reconcile_sources(
    client: TelegramClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> dict[int, TelegramSource]:
    """Read active sources, resolve ``chat_id`` for NULL rows via ``get_entity``.

    Sleep 0.3s between ``get_entity`` calls to stay well below TG rate-limits
    (32 sources * 300ms ~= 10s startup overhead — acceptable for Phase 1).
    Exceptions from ``get_entity`` are routed through
    :func:`handle_telegram_exception` (which may mark a source inactive, sleep
    on FloodWait, or ``SystemExit`` on AuthKey).
    """
    async with sessionmaker() as s:
        rows = (
            (await s.execute(select(TelegramSource).where(TelegramSource.is_active)))
            .scalars()
            .all()
        )

    resolved: dict[int, TelegramSource] = {}
    for src in rows:
        if src.chat_id is None:
            if src.username is None:
                logger.warning("source_missing_username", source_id=str(src.id))
                continue
            try:
                entity = await client.get_entity(src.username)
            except Exception as exc:
                async with sessionmaker() as s:
                    await handle_telegram_exception(exc, source_id=src.id, db=s)
                await asyncio.sleep(0.3)
                continue
            async with sessionmaker() as s:
                await s.execute(
                    update(TelegramSource)
                    .where(TelegramSource.id == src.id)
                    .values(chat_id=entity.id)
                )
                await s.commit()
            src.chat_id = entity.id
            logger.info("source_resolved", username=src.username, chat_id=entity.id)
            await asyncio.sleep(0.3)
        if src.chat_id is not None:
            resolved[src.chat_id] = src
    return resolved


async def _wait_for_shutdown(stop_event: asyncio.Event, client: TelegramClient) -> None:
    """Block until SIGTERM/SIGINT, then trigger ``client.disconnect()`` with timeout.

    Bounded ``asyncio.wait_for`` keeps us under Docker's default 10s grace period
    so SIGKILL doesn't fire before the final session save flushes.
    """
    await stop_event.wait()
    logger.info("listener_shutdown_signal_received")
    try:
        await asyncio.wait_for(client.disconnect(), timeout=8.0)
    except TimeoutError:
        logger.warning("listener_disconnect_timeout", timeout=8.0)


async def run() -> None:
    """Wire SessionManager + reconciliation + handler + graceful shutdown."""
    configure_logging()
    settings = get_settings()

    session_mgr = SessionManager(
        session_path=SESSION_PATH,
        session_key=settings.TELETHON_SESSION_KEY.get_secret_value().encode(),
        api_id=settings.TELEGRAM_API_ID,
        api_hash=settings.TELEGRAM_API_HASH.get_secret_value(),
    )

    client = await session_mgr.connect()
    sessionmaker = get_sessionmaker()
    engine = get_engine()
    try:
        pool = _SessionPool(sessionmaker)

        source_by_chat_id = await _reconcile_sources(client, sessionmaker)
        if not source_by_chat_id:
            logger.warning("listener_started_with_no_sources")

        @client.on(events.NewMessage(chats=list(source_by_chat_id)))  # type: ignore[untyped-decorator]
        async def _handler(event: Any) -> None:
            await handle_message(event, pool, source_by_chat_id)

        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        registered_signals: list[str] = []
        for sig_name in ("SIGTERM", "SIGINT"):
            sig = getattr(signal, sig_name, None)
            if sig is None:
                continue
            try:
                loop.add_signal_handler(sig, stop_event.set)
                registered_signals.append(sig_name)
            except NotImplementedError:
                pass

        if not registered_signals:
            logger.warning(
                "listener_signal_handlers_unavailable",
                reason="event_loop_lacks_add_signal_handler",
                impact="graceful shutdown via SIGTERM/SIGINT will not work; SIGKILL only",
            )
        else:
            logger.info("listener_signals_registered", signals=registered_signals)

        logger.info("listener_ready", source_count=len(source_by_chat_id))
        await asyncio.gather(
            client.run_until_disconnected(),
            _wait_for_shutdown(stop_event, client),
            return_exceptions=False,
        )
    finally:
        await session_mgr.disconnect()
        await engine.dispose()
        logger.info("listener_stopped")


def main() -> None:
    """Synchronous wrapper used by the console script / ``python -m listener``."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
