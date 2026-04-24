"""Integration tests for migration 0001 — round-trip + table creation."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


EXPECTED_TABLES = {
    "telegram_sources",
    "raw_messages",
    "keyword_triggers",
    "lead_analysis",
    "sender_profiles",
    "alembic_version",
}


async def test_migration_creates_all_expected_tables(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
        )
        tables = {row[0] for row in result.all()}
    assert EXPECTED_TABLES.issubset(tables)
