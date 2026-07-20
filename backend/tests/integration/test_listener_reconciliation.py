"""Integration: ``_reconcile_sources`` resolves chat_id for NULL rows.

Spins up Postgres via the session-wide ``postgres_container`` fixture, creates
the schema from ORM metadata (no Alembic needed — we only touch
``telegram_sources``), then exercises ``_reconcile_sources`` with a mocked
``TelegramClient.get_entity`` to verify two paths:

* Success path: NULL ``chat_id`` is back-filled and the source is returned
  in the ``resolved`` dict keyed by ``chat_id``.
* Private-channel path: ``ChannelPrivateError`` from ``get_entity`` flows
  through ``handle_telegram_exception`` and flips ``is_active=False``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from telethon.errors import ChannelPrivateError
from testcontainers.postgres import PostgresContainer

from listener.main import _reconcile_sources
from shared.db.session import Base
from shared.db.tables.telegram_source import TelegramSource
from tests.integration.conftest import _to_async_url

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture()
async def db_session_factory(
    postgres_container: PostgresContainer,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Async engine + sessionmaker bound to the testcontainers Postgres.

    Creates schema via ``Base.metadata.create_all`` (just ``telegram_sources``
    is exercised here, but other ORM tables come along for free). Drops the
    schema at teardown so successive tests start clean within one container
    lifetime.
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


async def test_reconcile_resolves_null_chat_id(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Row with ``chat_id=NULL`` gets updated from ``client.get_entity``."""

    async with db_session_factory() as s:
        src = TelegramSource(
            id=uuid4(),
            username="testchannel",
            title="Test Channel",
            source_type="channel",
            chat_id=None,
            is_active=True,
            priority=5,
        )
        s.add(src)
        await s.commit()
        src_id = src.id

    fake_client = MagicMock()
    fake_client.get_entity = AsyncMock(return_value=MagicMock(id=-100999888777))

    resolved = await _reconcile_sources(fake_client, db_session_factory)

    assert -100999888777 in resolved
    async with db_session_factory() as s:
        row = (
            await s.execute(select(TelegramSource).where(TelegramSource.id == src_id))
        ).scalar_one()
        assert row.chat_id == -100999888777


async def test_reconcile_channel_private_marks_inactive(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """``ChannelPrivateError`` → ``source.is_active=False``, removed from resolved."""

    async with db_session_factory() as s:
        src = TelegramSource(
            id=uuid4(),
            username="privatechannel",
            title="Private",
            source_type="channel",
            chat_id=None,
            is_active=True,
            priority=5,
        )
        s.add(src)
        await s.commit()
        src_id = src.id

    fake_client = MagicMock()
    fake_client.get_entity = AsyncMock(side_effect=ChannelPrivateError(request=None))

    resolved = await _reconcile_sources(fake_client, db_session_factory)

    assert resolved == {}
    async with db_session_factory() as s:
        row = (
            await s.execute(select(TelegramSource).where(TelegramSource.id == src_id))
        ).scalar_one()
        assert row.is_active is False


async def test_reconcile_valueerror_deactivates_and_continues(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Unresolvable username (``get_entity`` → ``ValueError``) deactivates that
    one source and reconciliation carries on with the next.

    Telethon raises a plain ``ValueError`` when it cannot resolve a username
    (dead / renamed / never existed). A single such seed must not crash the
    whole listener, so the dead source is flipped ``is_active=False`` and the
    loop continues — the *other*, live source still resolves.
    """

    async with db_session_factory() as s:
        dead = TelegramSource(
            id=uuid4(),
            username="deadchannel",
            title="Dead",
            source_type="channel",
            chat_id=None,
            is_active=True,
            priority=5,
        )
        alive = TelegramSource(
            id=uuid4(),
            username="alivechannel",
            title="Alive",
            source_type="channel",
            chat_id=None,
            is_active=True,
            priority=5,
        )
        s.add_all([dead, alive])
        await s.commit()
        dead_id, alive_id = dead.id, alive.id

    def _resolve(username: str) -> MagicMock:
        if username == "deadchannel":
            raise ValueError(f"No user has {username!r} as username")
        return MagicMock(id=-100111222333)

    fake_client = MagicMock()
    fake_client.get_entity = AsyncMock(side_effect=_resolve)

    # Must NOT raise: the ValueError from the dead source is contained.
    resolved = await _reconcile_sources(fake_client, db_session_factory)

    # The live source still resolved despite the dead one earlier in the loop.
    assert -100111222333 in resolved

    async with db_session_factory() as s:
        dead_row = (
            await s.execute(select(TelegramSource).where(TelegramSource.id == dead_id))
        ).scalar_one()
        alive_row = (
            await s.execute(select(TelegramSource).where(TelegramSource.id == alive_id))
        ).scalar_one()

    assert dead_row.is_active is False
    assert dead_row.chat_id is None
    assert alive_row.is_active is True
    assert alive_row.chat_id == -100111222333


async def test_reconcile_unknown_exception_propagates(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A non-Telethon, non-``ValueError`` error must NOT be swallowed.

    Guard against an over-broad ``except``: a ``RuntimeError`` (config bug,
    programming defect) has to keep propagating through the existing dispatcher
    rather than being silently reclassified as "unresolvable source". The
    source stays active — we did not decide it was dead.
    """

    async with db_session_factory() as s:
        src = TelegramSource(
            id=uuid4(),
            username="boomchannel",
            title="Boom",
            source_type="channel",
            chat_id=None,
            is_active=True,
            priority=5,
        )
        s.add(src)
        await s.commit()
        src_id = src.id

    fake_client = MagicMock()
    fake_client.get_entity = AsyncMock(side_effect=RuntimeError("unexpected defect"))

    with pytest.raises(RuntimeError):
        await _reconcile_sources(fake_client, db_session_factory)

    async with db_session_factory() as s:
        row = (
            await s.execute(select(TelegramSource).where(TelegramSource.id == src_id))
        ).scalar_one()
        assert row.is_active is True
