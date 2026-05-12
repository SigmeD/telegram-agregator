"""Unit tests for SessionManager: Fernet encryption + StringSession lifecycle."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet, InvalidToken
from telethon.sessions import StringSession

from shared.telegram.session_manager import SessionManager


@pytest.fixture(autouse=True)
def reset_alive_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure _alive_flag starts False for each test (module-level state)."""
    from shared.telegram import session_manager

    monkeypatch.setitem(session_manager._alive_flag, "value", False)


@pytest.fixture
def fernet_key() -> bytes:
    return Fernet.generate_key()


@pytest.fixture
def valid_session_blob(tmp_path: Path, fernet_key: bytes) -> Path:
    """Write a Fernet-encrypted empty StringSession to a tmp file."""
    string_session = StringSession().save()
    blob = Fernet(fernet_key).encrypt(string_session.encode())
    path = tmp_path / "tlg_aggregator.session.enc"
    path.write_bytes(blob)
    return path


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_manager_connect_with_valid_blob(
    valid_session_blob: Path, fernet_key: bytes
) -> None:
    """Happy path: valid blob decrypts → StringSession → TelegramClient.connect()."""
    mgr = SessionManager(
        session_path=valid_session_blob,
        session_key=fernet_key,
        api_id=12345,
        api_hash="dummy",
    )

    fake_client = AsyncMock()
    fake_client.connect = AsyncMock()
    fake_client.is_user_authorized = AsyncMock(return_value=True)
    fake_client.session = MagicMock()
    fake_client.session.save = MagicMock(return_value="updated_session_str")

    with patch("shared.telegram.session_manager.TelegramClient", return_value=fake_client):
        client = await mgr.connect()

    assert client is fake_client
    fake_client.connect.assert_awaited_once()
    fake_client.is_user_authorized.assert_awaited_once()

    # Cleanup: cancel the writer task spawned by connect() so it doesn't leak.
    await mgr.disconnect()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_manager_connect_wrong_key_raises_invalid_token(
    valid_session_blob: Path,
) -> None:
    """Wrong Fernet key → cryptography.fernet.InvalidToken propagates."""
    wrong_key = Fernet.generate_key()
    mgr = SessionManager(
        session_path=valid_session_blob,
        session_key=wrong_key,
        api_id=12345,
        api_hash="dummy",
    )
    with pytest.raises(InvalidToken):
        await mgr.connect()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_manager_connect_unauthorized_disconnects_client(
    valid_session_blob: Path, fernet_key: bytes
) -> None:
    """is_user_authorized() == False → AuthKeyError + client.disconnect() called."""
    from telethon.errors import AuthKeyError

    mgr = SessionManager(
        session_path=valid_session_blob,
        session_key=fernet_key,
        api_id=12345,
        api_hash="dummy",
    )

    fake_client = AsyncMock()
    fake_client.connect = AsyncMock()
    fake_client.is_user_authorized = AsyncMock(return_value=False)
    fake_client.disconnect = AsyncMock()

    with (
        patch("shared.telegram.session_manager.TelegramClient", return_value=fake_client),
        pytest.raises(AuthKeyError),
    ):
        await mgr.connect()

    fake_client.disconnect.assert_awaited_once()
    assert mgr._client is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_manager_writer_loop_saves_periodically(
    valid_session_blob: Path, fernet_key: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_writer_loop calls _save_session every WRITER_INTERVAL_SEC seconds."""
    # Capture the real asyncio.sleep before monkeypatching so this test body
    # can still yield control to the event loop after the module-local
    # sleep has been replaced.
    real_sleep = asyncio.sleep

    # side_effect must yield control to the event loop so the writer loop
    # doesn't hot-spin (Telethon doesn't depend on sleep duration here; we
    # only care it was called).
    async def _yield_immediately(_seconds: float) -> None:
        await real_sleep(0)

    sleep_mock = AsyncMock(side_effect=_yield_immediately)
    monkeypatch.setattr("shared.telegram.session_manager.asyncio.sleep", sleep_mock)

    mgr = SessionManager(
        session_path=valid_session_blob,
        session_key=fernet_key,
        api_id=1,
        api_hash="x",
    )

    save_mock = AsyncMock()
    mgr._save_session = save_mock  # type: ignore[method-assign]

    task = asyncio.create_task(mgr._writer_loop())
    # Yield several times so the writer loop has a chance to tick.
    for _ in range(5):
        await real_sleep(0)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert save_mock.await_count >= 1

    # Verify the loop actually sleeps for the configured interval.
    assert sleep_mock.await_count >= 1
    sleep_calls_for_interval = [
        c
        for c in sleep_mock.call_args_list
        if c.args and c.args[0] == SessionManager._WRITER_INTERVAL_SEC
    ]
    assert len(sleep_calls_for_interval) >= 1, (
        f"Expected at least one asyncio.sleep({SessionManager._WRITER_INTERVAL_SEC}); "
        f"got calls: {sleep_mock.call_args_list}"
    )
