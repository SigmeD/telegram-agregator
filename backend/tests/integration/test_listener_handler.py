"""Integration: ``handle_message`` end-to-end against a real Postgres.

Drives :func:`listener.processing.handle_message` with a synthetic Telethon
``NewMessage`` event and verifies two things against the live database:

* Test #1 — a ``raw_messages`` row is persisted with every field populated
  correctly from the event.
* Test #2 — the downstream Celery task (``worker.tasks.filter_keywords.
  filter_message``, re-exported via ``listener.processing``) is invoked
  exactly once with the new ``raw_message_id`` as a kwarg, *after* commit.

Mirrors the fixture pattern from ``test_listener_reconciliation.py``:
schema is created from ORM metadata (no Alembic needed) and dropped at
teardown so successive tests inside one container lifetime stay clean.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from listener.processing import handle_message
from shared.db.session import Base
from shared.db.tables.raw_message import RawMessage
from shared.db.tables.telegram_source import TelegramSource
from tests.integration.conftest import _to_async_url

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture()
async def db_session_factory(
    postgres_container: PostgresContainer,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Async engine + sessionmaker bound to the testcontainers Postgres.

    Creates the full ORM schema (``Base.metadata.create_all``) so
    ``raw_messages`` and its FK to ``telegram_sources`` are both present.
    Drops at teardown — clean slate between tests within the same container.
    """

    url = _to_async_url(postgres_container.get_connection_url())
    engine = create_async_engine(url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_sm = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield async_sm
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


async def test_handle_message_persists_row_with_correct_fields(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Full event → DB row, all fields populated from the event."""

    async with db_session_factory() as s:
        src = TelegramSource(
            id=uuid4(),
            username="founders",
            title="Founders",
            source_type="group",
            chat_id=-100111222333,
            is_active=True,
            priority=8,
        )
        s.add(src)
        await s.commit()
        src_id = src.id

    sender = SimpleNamespace(username="bob", first_name="Bob", last_name="X")
    event = SimpleNamespace(
        id=777,
        chat_id=-100111222333,
        sender_id=42,
        sender=sender,
        message=SimpleNamespace(reply_to=None),
        raw_text="Need help building MVP",
        media=None,
        reply_to_msg_id=None,
        date=datetime(2026, 5, 12, 11, 30, tzinfo=UTC),
    )

    class _Pool:
        def session(self) -> AsyncSession:
            return db_session_factory()

    source_by_chat_id = {-100111222333: SimpleNamespace(id=src_id)}

    with patch("listener.processing.filter_message", MagicMock()):
        await handle_message(event, _Pool(), source_by_chat_id)

    async with db_session_factory() as s:
        rows = (await s.execute(select(RawMessage))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.source_id == src_id
    assert row.telegram_message_id == 777
    assert row.sender_id == 42
    assert row.sender_username == "bob"
    assert row.sender_name == "Bob X"
    assert row.message_text == "Need help building MVP"
    assert row.has_media is False
    assert row.media_type is None
    assert row.reply_to_message_id is None
    assert row.thread_id is None
    assert row.processing_status == "pending"


async def test_handle_message_calls_celery_after_commit(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Celery ``.delay()`` is called once after DB commit, with ``raw_message_id`` kwarg."""

    async with db_session_factory() as s:
        src = TelegramSource(
            id=uuid4(),
            username="c",
            title="C",
            source_type="channel",
            chat_id=-1,
            is_active=True,
            priority=5,
        )
        s.add(src)
        await s.commit()
        src_id = src.id

    event = SimpleNamespace(
        id=1,
        chat_id=-1,
        sender_id=None,
        sender=None,
        message=SimpleNamespace(reply_to=None),
        raw_text="hi",
        media=None,
        reply_to_msg_id=None,
        date=datetime.now(UTC),
    )

    class _Pool:
        def session(self) -> AsyncSession:
            return db_session_factory()

    celery_mock = MagicMock()
    with patch("listener.processing.filter_message", celery_mock):
        await handle_message(event, _Pool(), {-1: SimpleNamespace(id=src_id)})

    celery_mock.delay.assert_called_once()
    call_kwargs = celery_mock.delay.call_args.kwargs
    assert "raw_message_id" in call_kwargs
    # Verify the kwarg is a UUID string and matches the actually-persisted row.
    async with db_session_factory() as s:
        rows = (await s.execute(select(RawMessage))).scalars().all()
    assert len(rows) == 1
    assert call_kwargs["raw_message_id"] == str(rows[0].id)
