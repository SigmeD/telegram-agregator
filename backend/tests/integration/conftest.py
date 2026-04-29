"""Integration-only fixtures: async DB URL and a migrated Postgres."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

# Points to backend/migrations/alembic.ini.
_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "migrations" / "alembic.ini"


def _to_async_url(sync_url: str) -> str:
    """Convert a ``postgresql+psycopg2://...`` URL to ``postgresql+asyncpg://...``."""

    return sync_url.replace("+psycopg2", "+asyncpg").replace(
        "postgresql://", "postgresql+asyncpg://"
    )


@pytest.fixture(scope="session")
def async_db_url(postgres_container: PostgresContainer) -> str:
    """Async Postgres DSN bound to the session-wide container."""

    return _to_async_url(postgres_container.get_connection_url())


@pytest.fixture(scope="session")
def migrated_db_url(async_db_url: str) -> Iterator[str]:
    """Apply ``alembic upgrade head`` once per session. Downgrade at teardown.

    Tests should treat this DB as shared state: clean up their own rows.
    Use ``db_session`` below for per-test auto-rollback.
    """

    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", async_db_url)
    command.upgrade(cfg, "head")
    try:
        yield async_db_url
    finally:
        command.downgrade(cfg, "base")


@pytest_asyncio.fixture()
async def db_engine(migrated_db_url: str) -> AsyncIterator[AsyncEngine]:
    """Async SQLAlchemy engine bound to the migrated database."""

    engine = create_async_engine(migrated_db_url, future=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture()
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Per-test session that rolls back at teardown — no cleanup needed."""

    async_sm = async_sessionmaker(db_engine, expire_on_commit=False)
    async with async_sm() as session:
        try:
            yield session
        finally:
            await session.rollback()
