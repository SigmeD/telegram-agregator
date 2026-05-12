"""Unit tests for shared.telegram.bootstrap CLI."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from telethon.sessions import StringSession

from shared.telegram import bootstrap


@pytest.fixture
def env_setup(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Populate Settings env (with a real Fernet key) and clear get_settings cache."""
    from shared import config

    key = Fernet.generate_key().decode()
    env = {
        "TELEGRAM_API_ID": "12345",
        "TELEGRAM_API_HASH": "dummy_hash",
        "TELEGRAM_PHONE": "+10000000000",
        "TELETHON_SESSION_KEY": key,
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    # conftest pre-populates a non-Fernet TELETHON_SESSION_KEY; the cached
    # Settings instance must be discarded so the bootstrap picks up our key.
    config.get_settings.cache_clear()
    yield env
    config.get_settings.cache_clear()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bootstrap_writes_encrypted_blob_to_target_path(
    env_setup: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bootstrap creates Fernet-encrypted blob at target_path."""
    target = tmp_path / "tlg.session.enc"

    fake_client = AsyncMock()
    fake_client.start = AsyncMock()
    fake_client.disconnect = AsyncMock()
    fake_client.session = MagicMock()
    fake_client.session.save = MagicMock(return_value=StringSession().save())

    monkeypatch.setattr(bootstrap, "input", lambda prompt="": "y")

    with patch.object(bootstrap, "TelegramClient", return_value=fake_client):
        await bootstrap.run_bootstrap(output_path=target)

    assert target.exists()
    decrypted = Fernet(env_setup["TELETHON_SESSION_KEY"].encode()).decrypt(target.read_bytes())
    StringSession(decrypted.decode())  # no error → valid


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bootstrap_skips_when_file_exists_and_user_declines(
    env_setup: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Existing file + 'N' answer → exit silently without overwriting."""
    target = tmp_path / "existing.enc"
    target.write_bytes(b"OLD_BLOB")

    monkeypatch.setattr(bootstrap, "input", lambda prompt="": "")  # default N

    with patch.object(bootstrap, "TelegramClient") as tc_mock:
        await bootstrap.run_bootstrap(output_path=target)
    tc_mock.assert_not_called()
    assert target.read_bytes() == b"OLD_BLOB"
