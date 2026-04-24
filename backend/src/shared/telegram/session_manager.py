"""Telethon session lifecycle manager (FEATURE-01 / FEATURE-10).

Responsibilities:
* Load encrypted ``.session`` blob, decrypt with ``TELETHON_SESSION_KEY``.
* Instantiate ``telethon.TelegramClient`` with safe defaults (flood-sleep
  threshold, device metadata, proxy hook).
* Expose ``connect`` / ``disconnect`` / ``is_authorized`` helpers for listener
  bootstrap and health-checks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telethon import TelegramClient


class SessionManager:
    """Manage a single Telethon user-session."""

    def __init__(self, *, session_name: str = "tlg_aggregator") -> None:
        self._session_name = session_name
        self._client: TelegramClient | None = None

    async def connect(self) -> "TelegramClient":
        """Connect to Telegram and return an authorised client.

        Raises:
            NotImplementedError: Stub implementation.
        """

        raise NotImplementedError("SessionManager.connect is not implemented yet")

    async def disconnect(self) -> None:
        """Flush state and close the underlying MTProto connection."""

        raise NotImplementedError("SessionManager.disconnect is not implemented yet")

    async def is_authorized(self) -> bool:
        """Return ``True`` if the session is usable without re-login."""

        raise NotImplementedError("SessionManager.is_authorized is not implemented yet")
