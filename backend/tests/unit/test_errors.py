"""Unit tests for telethon error helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from telethon.errors import (
    AuthKeyError,
    ChannelPrivateError,
    ChatAdminRequiredError,
    FloodWaitError,
)

from shared.telegram.errors import (
    handle_telegram_exception,
    retry_telethon,
    with_telethon_retries,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_with_telethon_retries_returns_on_first_success() -> None:
    """No retry if the first call succeeds."""
    op = AsyncMock(return_value="ok")
    async with with_telethon_retries(max_attempts=5, base_delay=0.01):
        result = await op()
    assert result == "ok"
    assert op.call_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_retry_telethon_recovers_after_transient_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Decorator retries until the wrapped coroutine returns."""
    monkeypatch.setattr("shared.telegram.errors.asyncio.sleep", AsyncMock())
    calls: list[int] = []

    @retry_telethon(max_attempts=5, base_delay=0.01)
    async def flaky() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("boom")
        return "ok"

    result = await flaky()
    assert result == "ok"
    assert len(calls) == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_retry_telethon_raises_after_max_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After max_attempts consecutive failures, the last exception propagates."""
    monkeypatch.setattr("shared.telegram.errors.asyncio.sleep", AsyncMock())

    @retry_telethon(max_attempts=3, base_delay=0.01)
    async def always_fails() -> None:
        raise OSError("network down")

    with pytest.raises(OSError, match="network down"):
        await always_fails()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_flood_wait_sleeps_with_10pct_buffer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FloodWaitError → sleep for seconds * 1.1 then return."""
    sleep_mock = AsyncMock()
    monkeypatch.setattr("shared.telegram.errors.asyncio.sleep", sleep_mock)
    db = MagicMock()
    exc = FloodWaitError(request=None)
    exc.seconds = 30

    await handle_telegram_exception(exc, source_id=uuid4(), db=db)

    sleep_mock.assert_awaited_once()
    args, _ = sleep_mock.call_args
    assert args[0] == pytest.approx(30 * 1.1, rel=1e-3)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_channel_private_marks_source_inactive() -> None:
    """ChannelPrivateError → UPDATE telegram_sources SET is_active=false + commit."""
    db = AsyncMock()
    source_id = uuid4()
    exc = ChannelPrivateError(request=None)

    await handle_telegram_exception(exc, source_id=source_id, db=db)

    db.execute.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_channel_private_no_source_id_skips_db() -> None:
    """source_id=None → skip DB update, still emit admin_notify log."""
    db = AsyncMock()
    exc = ChannelPrivateError(request=None)
    await handle_telegram_exception(exc, source_id=None, db=db)
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_chat_admin_required_marks_source_inactive() -> None:
    """ChatAdminRequiredError path: same UPDATE behaviour, different reason in log."""
    db = AsyncMock()
    source_id = uuid4()
    exc = ChatAdminRequiredError(request=None)
    await handle_telegram_exception(exc, source_id=source_id, db=db)
    db.execute.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_auth_key_error_raises_system_exit() -> None:
    """AuthKeyError → SystemExit(1) so the supervisor restarts."""
    db = AsyncMock()
    # Telethon's AuthKeyError(request, message) — base RPCError signature.
    exc = AuthKeyError(request=None, message="AUTH_KEY_INVALID")
    with pytest.raises(SystemExit) as ei:
        await handle_telegram_exception(exc, source_id=None, db=db)
    assert ei.value.code == 1
