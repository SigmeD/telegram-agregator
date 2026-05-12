"""Unit tests for listener.processing — NewMessage → RawMessage row + Celery."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from listener.processing import handle_message


def _fake_event(**overrides: Any) -> SimpleNamespace:
    """Minimal fake ``events.NewMessage`` payload for the handler."""
    sender = SimpleNamespace(username="alice", first_name="Alice", last_name=None)
    msg = SimpleNamespace(reply_to=None)
    base = SimpleNamespace(
        id=42,
        chat_id=-100123456789,
        sender_id=999,
        sender=sender,
        message=msg,
        raw_text="Looking for MVP developer",
        media=None,
        reply_to_msg_id=None,
        date=datetime(2026, 5, 12, 10, 0, tzinfo=UTC),
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def _fake_db_pool() -> tuple[MagicMock, AsyncMock]:
    """Return ``(db_pool_mock, session_ctx_mock)`` with ``async with`` wired up."""
    db_pool = MagicMock()
    session_ctx = AsyncMock()
    session_ctx.__aenter__.return_value = session_ctx
    session_ctx.__aexit__.return_value = None
    session_ctx.commit = AsyncMock()
    session_ctx.add = MagicMock()
    db_pool.session.return_value = session_ctx
    return db_pool, session_ctx


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_message_writes_row_and_enqueues_celery() -> None:
    """Happy path: row added + committed, then Celery task enqueued."""
    source = SimpleNamespace(id=uuid4())
    source_by_chat_id = {-100123456789: source}
    event = _fake_event()

    db_pool, session_ctx = _fake_db_pool()

    # Simulate Postgres ``gen_random_uuid()`` server default — the ORM normally
    # gets ``msg.id`` populated after commit, but in the mocked-DB world we
    # assign it at ``add()`` time so the value captured by Celery is non-None.
    def add_with_id_assignment(msg: Any) -> None:
        msg.id = uuid4()

    session_ctx.add = MagicMock(side_effect=add_with_id_assignment)

    celery_mock = MagicMock()
    with patch("listener.processing.filter_message", celery_mock):
        await handle_message(event, db_pool, source_by_chat_id)

    session_ctx.add.assert_called_once()
    added_msg = session_ctx.add.call_args.args[0]
    assert added_msg.source_id == source.id
    assert added_msg.telegram_message_id == 42
    assert added_msg.sender_username == "alice"
    assert added_msg.sender_name == "Alice"
    assert added_msg.message_text == "Looking for MVP developer"
    assert added_msg.processing_status == "pending"
    assert added_msg.has_media is False
    assert added_msg.media_type is None

    session_ctx.commit.assert_awaited_once()

    celery_mock.delay.assert_called_once()
    kwargs = celery_mock.delay.call_args.kwargs
    assert kwargs == {"raw_message_id": str(added_msg.id)}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_message_db_failure_is_swallowed() -> None:
    """If DB commit raises, ``logger.exception`` fires and handler returns cleanly."""
    source = SimpleNamespace(id=uuid4())
    source_by_chat_id = {-100123456789: source}
    event = _fake_event()

    db_pool = MagicMock()
    session_ctx = AsyncMock()
    session_ctx.__aenter__.return_value = session_ctx
    session_ctx.__aexit__.return_value = None
    session_ctx.commit = AsyncMock(side_effect=RuntimeError("db down"))
    session_ctx.add = MagicMock()
    db_pool.session.return_value = session_ctx

    celery_mock = MagicMock()
    with patch("listener.processing.filter_message", celery_mock):
        await handle_message(event, db_pool, source_by_chat_id)

    # Celery must NOT fire when DB commit failed — durability invariant.
    celery_mock.delay.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_message_unknown_chat_returns_early() -> None:
    """No source registered for ``chat_id`` → no DB session opened, no Celery."""
    event = _fake_event(chat_id=-555)
    db_pool = MagicMock()

    celery_mock = MagicMock()
    with patch("listener.processing.filter_message", celery_mock):
        await handle_message(event, db_pool, source_by_chat_id={})

    db_pool.session.assert_not_called()
    celery_mock.delay.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_message_preserves_null_message_text_for_media_only() -> None:
    """Media-only message (``raw_text=None``) stores NULL, not empty string."""
    source = SimpleNamespace(id=uuid4())
    source_by_chat_id = {-100123456789: source}

    media_obj = SimpleNamespace()  # ``type().__name__`` will be "SimpleNamespace"
    event = _fake_event(raw_text=None, media=media_obj)

    db_pool, session_ctx = _fake_db_pool()

    celery_mock = MagicMock()
    with patch("listener.processing.filter_message", celery_mock):
        await handle_message(event, db_pool, source_by_chat_id)

    added_msg = session_ctx.add.call_args.args[0]
    assert added_msg.message_text is None
    assert added_msg.has_media is True
    assert added_msg.media_type == "SimpleNamespace"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_message_extracts_thread_id_from_forum_topic() -> None:
    """Event with reply_to.forum_topic_id → thread_id populated from that field."""
    source = SimpleNamespace(id=uuid4())
    source_by_chat_id = {-100123456789: source}

    # forum_topic_id branch: event.message.reply_to.forum_topic_id is set
    reply_to = SimpleNamespace(forum_topic_id=42, reply_to_top_id=None)
    event = _fake_event(
        message=SimpleNamespace(reply_to=reply_to),
    )

    db_pool = MagicMock()
    session_ctx = AsyncMock()
    session_ctx.__aenter__.return_value = session_ctx
    session_ctx.__aexit__.return_value = None
    session_ctx.commit = AsyncMock()
    session_ctx.add = MagicMock(side_effect=lambda msg: setattr(msg, "id", uuid4()))
    db_pool.session.return_value = session_ctx

    with patch("listener.processing.filter_message", MagicMock()):
        await handle_message(event, db_pool, source_by_chat_id)

    added_msg = session_ctx.add.call_args.args[0]
    assert added_msg.thread_id == 42


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_message_extracts_thread_id_from_reply_to_top_id() -> None:
    """Event with reply_to.reply_to_top_id (no forum_topic_id) → thread_id from fallback."""
    source = SimpleNamespace(id=uuid4())
    source_by_chat_id = {-100123456789: source}

    # forum_topic_id absent (None), reply_to_top_id set
    reply_to = SimpleNamespace(forum_topic_id=None, reply_to_top_id=99)
    event = _fake_event(
        message=SimpleNamespace(reply_to=reply_to),
    )

    db_pool = MagicMock()
    session_ctx = AsyncMock()
    session_ctx.__aenter__.return_value = session_ctx
    session_ctx.__aexit__.return_value = None
    session_ctx.commit = AsyncMock()
    session_ctx.add = MagicMock(side_effect=lambda msg: setattr(msg, "id", uuid4()))
    db_pool.session.return_value = session_ctx

    with patch("listener.processing.filter_message", MagicMock()):
        await handle_message(event, db_pool, source_by_chat_id)

    added_msg = session_ctx.add.call_args.args[0]
    assert added_msg.thread_id == 99


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_message_logs_celery_failure_but_keeps_row() -> None:
    """If filter_message.delay() raises, exception is caught and logged;
    handler returns without re-raising. raw_message is already committed
    to DB before the enqueue attempt — DB durability invariant preserved."""
    source = SimpleNamespace(id=uuid4())
    source_by_chat_id = {-100123456789: source}
    event = _fake_event()

    db_pool = MagicMock()
    session_ctx = AsyncMock()
    session_ctx.__aenter__.return_value = session_ctx
    session_ctx.__aexit__.return_value = None
    session_ctx.commit = AsyncMock()
    session_ctx.add = MagicMock(side_effect=lambda msg: setattr(msg, "id", uuid4()))
    db_pool.session.return_value = session_ctx

    celery_mock = MagicMock()
    celery_mock.delay = MagicMock(side_effect=ConnectionRefusedError("redis down"))

    # Should NOT raise — exception is caught and logged.
    with patch("listener.processing.filter_message", celery_mock):
        await handle_message(event, db_pool, source_by_chat_id)

    # DB commit DID happen before the failed enqueue.
    session_ctx.commit.assert_awaited_once()
    # delay() was attempted.
    celery_mock.delay.assert_called_once()
