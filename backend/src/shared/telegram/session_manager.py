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
        if not await self._client.is_user_authorized():
            raise AuthKeyError(request=None, message="SESSION_NOT_AUTHORIZED")

        self._writer_task = asyncio.create_task(self._writer_loop())
        _mark_alive()
        logger.info("session_manager_connected", path=str(self._session_path))
        return self._client

    async def disconnect(self) -> None:
        """Cancel writer task, save final state, close MTProto."""
        if self._writer_task is not None:
            self._writer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._writer_task
            self._writer_task = None

        if self._client is not None:
            await self._save_session()
            await self._client.disconnect()
            self._client = None
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


_alive_flag: dict[str, bool] = {"value": False}


def _mark_alive() -> None:
    _alive_flag["value"] = True


def session_alive() -> bool:
    """Module-level liveness check used by docker healthcheck.

    Returns True only if a SessionManager instance has connect'ed at least
    once in this process. Real Telethon ping is Phase 2.
    """
    return _alive_flag["value"]
