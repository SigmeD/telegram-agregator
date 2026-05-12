"""Telethon session lifecycle manager (FEATURE-01).

Responsibilities:
* Load Fernet-encrypted ``.session.enc`` blob, decrypt with ``TELETHON_SESSION_KEY``.
* Instantiate ``telethon.TelegramClient`` with production-safe defaults.
* Periodically re-serialise and re-encrypt session state (Telethon may
  update server salts / DC info during normal operation).
* Expose ``connect`` / ``disconnect`` / ``is_authorized`` for listener
  bootstrap and health-checks.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

import structlog
from cryptography.fernet import Fernet
from telethon import TelegramClient
from telethon.errors import AuthKeyError
from telethon.sessions import StringSession

logger = structlog.get_logger(__name__)


class SessionManager:
    """Manage one Telethon user-session backed by a Fernet-encrypted file."""

    _DEVICE = "tlg-aggregator"
    _SYSTEM = "Linux"
    _APP_VERSION = "0.1.0"
    _FLOOD_SLEEP_THRESHOLD = 60
    _REQUEST_RETRIES = 5
    _WRITER_INTERVAL_SEC = 30

    def __init__(
        self,
        *,
        session_path: Path,
        session_key: bytes,
        api_id: int,
        api_hash: str,
    ) -> None:
        self._session_path = session_path
        self._fernet = Fernet(session_key)
        self._api_id = api_id
        self._api_hash = api_hash
        self._client: TelegramClient | None = None
        self._writer_task: asyncio.Task[None] | None = None

    async def connect(self) -> TelegramClient:
        """Load blob, decrypt, build authorised TelegramClient.

        Raises:
            cryptography.fernet.InvalidToken: wrong session_key.
            telethon.errors.AuthKeyError: session blob is no longer valid.
        """
        blob = self._session_path.read_bytes()
        decrypted = self._fernet.decrypt(blob).decode()
        string_session = StringSession(decrypted)

        self._client = TelegramClient(
            string_session,
            self._api_id,
            self._api_hash,
            device_model=self._DEVICE,
            system_version=self._SYSTEM,
            app_version=self._APP_VERSION,
            flood_sleep_threshold=self._FLOOD_SLEEP_THRESHOLD,
            request_retries=self._REQUEST_RETRIES,
        )
        await self._client.connect()
        try:
            if not await self._client.is_user_authorized():
                raise AuthKeyError(request=None, message="SESSION_REVOKED")
        except BaseException:
            # Auth check failed (or itself raised) — MTProto socket is open but
            # session unusable. Close the socket and clear state so the caller
            # can drop this manager cleanly without leaking the connection.
            await self._client.disconnect()
            self._client = None
            raise

        self._writer_task = asyncio.create_task(self._writer_loop())
        _mark_alive()
        logger.info("session_manager_connected", path=str(self._session_path))
        return self._client

    async def disconnect(self) -> None:
        """Cancel writer task, save final state, close MTProto.

        Idempotent: safe to call before ``connect()`` (no-op) and after
        a failed ``connect()`` (cleans up whichever of writer_task / client
        was set).
        """
        # Capture whether anything was ever brought to life. Guards both the
        # disconnect log line and _mark_dead() from firing on a manager that
        # never connected (e.g. disconnect() called defensively before
        # connect(), or connect() raising InvalidToken before _mark_alive()).
        # _mark_dead() itself is idempotent via FileNotFoundError suppression,
        # but emitting "session_manager_disconnected" for a session that
        # never lived is misleading in logs.
        was_alive = self._writer_task is not None or self._client is not None

        # Two independent guards: connect() failure modes may leave one set
        # without the other (e.g. AuthKeyError path now in connect() resets
        # _client to None but never started _writer_task — both guards
        # short-circuit cleanly).
        if self._writer_task is not None:
            self._writer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._writer_task
            self._writer_task = None

        if self._client is not None:
            await self._save_session()
            await self._client.disconnect()
            self._client = None

        if was_alive:
            _mark_dead()
            logger.info("session_manager_disconnected")

    async def is_authorized(self) -> bool:
        if self._client is None:
            return False
        result: bool = await self._client.is_user_authorized()
        return result

    async def _writer_loop(self) -> None:
        """Periodically persist updated session state."""
        try:
            while True:
                await asyncio.sleep(self._WRITER_INTERVAL_SEC)
                await self._save_session()
        except asyncio.CancelledError:
            raise

    async def _save_session(self) -> None:
        if self._client is None:
            return
        session_str = self._client.session.save()
        blob = self._fernet.encrypt(session_str.encode())
        self._session_path.write_bytes(blob)
        with contextlib.suppress(OSError, PermissionError):
            self._session_path.chmod(0o600)


# Cross-process liveness marker. Used by docker compose healthcheck which
# imports this module in a SEPARATE process from the listener — module-level
# state would not propagate. Path lives on a tmpfs mount declared in
# infra/compose/docker-compose.yml (backend-listener.tmpfs) — wiped on every
# container start, so a SIGKILL'd predecessor's stale marker cannot fool the
# healthcheck during the restart window.
_ALIVE_MARKER_PATH = Path("/tmp/tlg-listener.alive")


def _mark_alive() -> None:
    """Touch the alive-marker file. Idempotent."""
    try:
        _ALIVE_MARKER_PATH.parent.mkdir(parents=True, exist_ok=True)
        _ALIVE_MARKER_PATH.touch()
    except OSError as exc:
        logger.warning("alive_marker_write_failed", path=str(_ALIVE_MARKER_PATH), exc=str(exc))


def _mark_dead() -> None:
    """Remove the alive-marker file. Idempotent (FileNotFoundError suppressed)."""
    with contextlib.suppress(FileNotFoundError):
        _ALIVE_MARKER_PATH.unlink()


def session_alive() -> bool:
    """Return True iff the alive-marker file exists.

    The marker is written by ``SessionManager.connect()`` and removed by
    ``disconnect()``. Lives at ``/tmp/tlg-listener.alive`` so a separate
    docker healthcheck process can observe it without sharing memory.
    The container mounts ``/tmp`` as tmpfs (see infra/compose/docker-compose.yml
    ``backend-listener.tmpfs``) — every container start wipes any stale marker
    left by a SIGKILL'd predecessor, so a graceful restart cannot report
    a false-positive HEALTHY before the new process re-touches the file.

    The path is module-level so tests can monkeypatch it to a temp location.
    """
    return _ALIVE_MARKER_PATH.exists()
