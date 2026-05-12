"""Telethon error handling: retry decorator + dispatcher.

Two responsibilities:

1. ``with_telethon_retries`` — async context manager that wraps a block in
   exponential-backoff retry on transient *network* errors only.
2. ``handle_telegram_exception`` — typed dispatch on Telethon exceptions:
   FloodWait (sleep + return), ChannelPrivate (mark inactive + notify_admin
   log), AuthKey (critical log + SystemExit), unknown (re-raise).
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, NamedTuple, ParamSpec, TypeVar
from uuid import UUID

import structlog
from sqlalchemy import update

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


@asynccontextmanager
async def with_telethon_retries(
    *, max_attempts: int = 5, base_delay: float = 1.0
) -> AsyncIterator[None]:
    """Wrap an awaitable block in exp-backoff retry on transient errors.

    Only catches ``ConnectionError``, ``asyncio.TimeoutError``, ``OSError``.
    ``FloodWaitError`` is intentionally NOT caught here — Telethon's own
    ``flood_sleep_threshold`` handles short waits, longer ones surface to
    the caller via :func:`handle_telegram_exception`.
    """

    attempt = 0
    while True:
        try:
            yield
            return
        except (ConnectionError, TimeoutError, OSError) as exc:
            attempt += 1
            if attempt >= max_attempts:
                logger.error(
                    "telethon_retries_exhausted",
                    attempts=attempt,
                    exc_type=type(exc).__name__,
                )
                raise
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            logger.warning(
                "telethon_retry",
                attempt=attempt,
                max_attempts=max_attempts,
                delay=round(delay, 3),
                exc=str(exc),
            )
            await asyncio.sleep(delay)


def retry_telethon(
    *, max_attempts: int = 5, base_delay: float = 1.0
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorator form — retries the wrapped coroutine on transient errors.

    Uses the same exception set and backoff schedule as
    :func:`with_telethon_retries`. This is the API that listener / worker
    callers actually use.
    """

    def decorator(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            attempt = 0
            while True:
                try:
                    return await fn(*args, **kwargs)
                except (ConnectionError, TimeoutError, OSError) as exc:
                    attempt += 1
                    if attempt >= max_attempts:
                        logger.error(
                            "telethon_retries_exhausted",
                            fn=fn.__name__,
                            attempts=attempt,
                        )
                        raise
                    delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                    logger.warning(
                        "telethon_retry",
                        fn=fn.__name__,
                        attempt=attempt,
                        delay=round(delay, 3),
                        exc=str(exc),
                    )
                    await asyncio.sleep(delay)

        return wrapper

    return decorator


class _TelethonExceptionTypes(NamedTuple):
    """Tuple of Telethon exception classes loaded lazily.

    Late import keeps ``telethon`` out of module-load time so unit tests
    that don't touch the dispatcher don't pay for the import.
    """

    auth_key: type[Exception]
    channel_private: type[Exception]
    chat_admin_required: type[Exception]
    flood_wait: type[Exception]
    session_password_needed: type[Exception]


def _telethon_exceptions() -> _TelethonExceptionTypes:
    """Late import — avoids hard dependency at module-load time."""

    from telethon.errors import (
        AuthKeyError,
        ChannelPrivateError,
        ChatAdminRequiredError,
        FloodWaitError,
        SessionPasswordNeededError,
    )

    return _TelethonExceptionTypes(
        auth_key=AuthKeyError,
        channel_private=ChannelPrivateError,
        chat_admin_required=ChatAdminRequiredError,
        flood_wait=FloodWaitError,
        session_password_needed=SessionPasswordNeededError,
    )


async def handle_telegram_exception(
    exc: Exception,
    *,
    source_id: UUID | None,
    db: AsyncSession,
) -> None:
    """Dispatch a Telethon exception by type. Mutating side-effects only here.

    * ``FloodWaitError`` — sleep ``seconds * 1.1`` and return.
    * ``ChannelPrivateError`` / ``ChatAdminRequiredError`` — mark the source
      inactive in the DB and log ``admin_notify``.
    * ``AuthKeyError`` / ``SessionPasswordNeededError`` — log critical and
      ``SystemExit(1)`` so the supervisor restarts a fresh session.
    * Anything else — re-raise unchanged.
    """

    types = _telethon_exceptions()

    if isinstance(exc, types.flood_wait):
        seconds = float(getattr(exc, "seconds", 0))
        logger.warning(
            "telethon_flood_wait",
            seconds=seconds,
            source_id=str(source_id) if source_id else None,
        )
        await asyncio.sleep(seconds * 1.1)
        return

    if isinstance(exc, types.channel_private | types.chat_admin_required):
        from shared.db.tables.telegram_source import TelegramSource

        if source_id is not None:
            await db.execute(
                update(TelegramSource).where(TelegramSource.id == source_id).values(is_active=False)
            )
            await db.commit()
        logger.error(
            "admin_notify",
            source_id=str(source_id) if source_id else None,
            reason="channel_private",
            exc_type=type(exc).__name__,
        )
        return

    if isinstance(exc, types.auth_key | types.session_password_needed):
        logger.critical("auth_key_invalid", exc_type=type(exc).__name__)
        raise SystemExit(1)

    raise exc
