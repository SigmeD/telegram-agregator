"""Standalone round-trip: upgrade -> check -> downgrade -> check empty.

Uses its own ephemeral Postgres container so it can downgrade without
disturbing the session-wide ``migrated_db_url`` used by other tests.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "migrations" / "alembic.ini"

_DOMAIN_TABLES = frozenset(
    {
        "telegram_sources",
        "raw_messages",
        "keyword_triggers",
        "lead_analysis",
        "sender_profiles",
    }
)


def _async_url(sync_url: str) -> str:
    return sync_url.replace("+psycopg2", "+asyncpg").replace(
        "postgresql://", "postgresql+asyncpg://"
    )


async def test_migration_upgrade_then_downgrade_leaves_no_domain_tables() -> None:
    with PostgresContainer("postgres:15-alpine") as pg:
        url = _async_url(pg.get_connection_url())
        cfg = Config(str(_ALEMBIC_INI))
        cfg.set_main_option("sqlalchemy.url", url)

        # alembic's env.py calls asyncio.run(), which can't nest inside a
        # running loop — run it on a worker thread.
        await asyncio.to_thread(command.upgrade, cfg, "head")
        await asyncio.to_thread(command.downgrade, cfg, "base")

        engine = create_async_engine(url, future=True)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                )
                tables = {r[0] for r in result.all()}
        finally:
            await engine.dispose()
        leftover = _DOMAIN_TABLES & tables
        assert not leftover, f"leftover domain tables after downgrade: {leftover}"


async def test_partial_indexes_registered_with_predicate() -> None:
    """Both partial indexes must exist WITH a WHERE clause in pg_indexes."""

    with PostgresContainer("postgres:15-alpine") as pg:
        url = _async_url(pg.get_connection_url())
        cfg = Config(str(_ALEMBIC_INI))
        cfg.set_main_option("sqlalchemy.url", url)
        await asyncio.to_thread(command.upgrade, cfg, "head")

        engine = create_async_engine(url, future=True)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(
                    text(
                        "SELECT indexname, indexdef FROM pg_indexes "
                        "WHERE indexname IN ("
                        "'ix_keyword_triggers_active_type', "
                        "'ix_lead_analysis_is_lead_analyzed_at')"
                    )
                )
                by_name = {r[0]: r[1] for r in result.all()}
        finally:
            await engine.dispose()

        assert set(by_name) == {
            "ix_keyword_triggers_active_type",
            "ix_lead_analysis_is_lead_analyzed_at",
        }
        assert "WHERE" in by_name["ix_keyword_triggers_active_type"].upper()
        assert "WHERE" in by_name["ix_lead_analysis_is_lead_analyzed_at"].upper()
