"""Interactive Telegram session bootstrap CLI (FEATURE-01).

Run on the VPS once, **interactively**:
    docker compose ... --profile bootstrap run --rm bootstrap

Generates a fresh ``StringSession`` via Telethon, Fernet-encrypts it with
``TELETHON_SESSION_KEY``, and writes the result to
``/var/lib/tlg/sessions/tlg_aggregator.session.enc`` on the
``tlg-session-data`` named volume.

Idempotent: existing file -> prompt to overwrite (default: no, exit 0).
"""

from __future__ import annotations

import asyncio
import contextlib
import getpass
import sys
from pathlib import Path

import structlog
from cryptography.fernet import Fernet
from telethon import TelegramClient
from telethon.sessions import StringSession

from shared.config import get_settings

logger = structlog.get_logger(__name__)

DEFAULT_OUTPUT_PATH = Path("/var/lib/tlg/sessions/tlg_aggregator.session.enc")

# Alias builtins so tests can ``monkeypatch.setattr(bootstrap, "input", ...)``
# scoped to this module only, without globally replacing ``builtins.input``.
input = input  # intentional builtin shadow


async def run_bootstrap(*, output_path: Path = DEFAULT_OUTPUT_PATH) -> None:
    """Generate a fresh Telethon session and write it as a Fernet-encrypted blob."""
    settings = get_settings()
    key = settings.TELETHON_SESSION_KEY.get_secret_value().encode()

    if output_path.exists():
        choice = input(f"File exists at {output_path}. Overwrite? y/N: ").strip().lower()
        if choice != "y":
            print("Aborted. Existing file kept.")
            return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    client = TelegramClient(
        StringSession(),
        settings.TELEGRAM_API_ID,
        settings.TELEGRAM_API_HASH.get_secret_value(),
        device_model="tlg-aggregator-bootstrap",
        system_version="Linux",
        app_version="0.1.0",
    )

    def _code_cb() -> str:
        return input("Enter SMS code: ").strip()

    def _password_cb() -> str | None:
        return getpass.getpass("Enter 2FA password (or empty): ").strip() or None

    try:
        await client.start(
            phone=lambda: settings.TELEGRAM_PHONE,
            code_callback=_code_cb,
            password=_password_cb,
        )
        session_str: str = client.session.save()
        blob = Fernet(key).encrypt(session_str.encode())
        output_path.write_bytes(blob)
        with contextlib.suppress(OSError, PermissionError):
            output_path.chmod(0o600)
    finally:
        await client.disconnect()

    size = output_path.stat().st_size
    print(f"Session saved to {output_path}. Size: {size} bytes.")
    logger.info("bootstrap_complete", path=str(output_path), size=size)


def main() -> None:
    """Synchronous CLI entry-point."""
    try:
        asyncio.run(run_bootstrap())
    except KeyboardInterrupt:
        print("\nAborted by user.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
