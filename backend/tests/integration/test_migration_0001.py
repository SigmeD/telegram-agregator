"""Integration tests for migration 0001 — constraints, FK, UNIQUE, JSONB, TZ."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

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
                "SELECT table_name FROM information_schema.tables " "WHERE table_schema = 'public'"
            )
        )
        tables = {row[0] for row in result.all()}
    assert EXPECTED_TABLES.issubset(tables)


# --- helpers ----------------------------------------------------------------


async def _insert_source(
    session: AsyncSession,
    *,
    chat_id: int = 1,
    source_type: str = "channel",
    priority: int = 5,
) -> None:
    await session.execute(
        text(
            "INSERT INTO telegram_sources (chat_id, title, source_type, priority) "
            "VALUES (:chat_id, :title, :st, :p)"
        ),
        {"chat_id": chat_id, "title": "t", "st": source_type, "p": priority},
    )


async def _insert_raw_message(
    session: AsyncSession,
    *,
    telegram_message_id: int = 1,
    processing_status: str = "pending",
    sent_at: datetime | None = None,
) -> None:
    await session.execute(
        text(
            "INSERT INTO raw_messages "
            "(source_id, telegram_message_id, sent_at, processing_status) "
            "SELECT id, :tmid, COALESCE(:sa, now()), :st FROM telegram_sources LIMIT 1"
        ),
        {
            "tmid": telegram_message_id,
            "sa": sent_at,
            "st": processing_status,
        },
    )


# --- CHECK constraints ------------------------------------------------------


@pytest.mark.parametrize("source_type", ["channel", "group", "supergroup"])
async def test_source_type_accepts_valid_values(db_session: AsyncSession, source_type: str) -> None:
    await _insert_source(db_session, source_type=source_type)


async def test_source_type_rejects_invalid_value(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        await _insert_source(db_session, source_type="bogus")
        await db_session.flush()


@pytest.mark.parametrize("priority", [1, 5, 10])
async def test_priority_accepts_in_range(db_session: AsyncSession, priority: int) -> None:
    await _insert_source(db_session, priority=priority)


@pytest.mark.parametrize("priority", [0, 11, -1, 100])
async def test_priority_rejects_out_of_range(db_session: AsyncSession, priority: int) -> None:
    with pytest.raises(IntegrityError):
        await _insert_source(db_session, priority=priority)
        await db_session.flush()


@pytest.mark.parametrize(
    "status",
    ["pending", "filtered_out", "analyzing", "lead", "not_lead", "error"],
)
async def test_processing_status_accepts_valid(db_session: AsyncSession, status: str) -> None:
    await _insert_source(db_session)
    await db_session.flush()
    await _insert_raw_message(db_session, processing_status=status)


async def test_processing_status_rejects_invalid(db_session: AsyncSession) -> None:
    await _insert_source(db_session)
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await _insert_raw_message(db_session, processing_status="nope")
        await db_session.flush()


@pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
async def test_confidence_accepts_unit_interval(
    db_session: AsyncSession, confidence: float
) -> None:
    await _insert_source(db_session)
    await db_session.flush()
    await _insert_raw_message(db_session)
    await db_session.flush()
    await db_session.execute(
        text(
            "INSERT INTO lead_analysis (raw_message_id, is_lead, confidence) "
            "SELECT id, true, :c FROM raw_messages LIMIT 1"
        ),
        {"c": confidence},
    )


@pytest.mark.parametrize("confidence", [-0.01, 1.01, 2.0])
async def test_confidence_rejects_outside_unit_interval(
    db_session: AsyncSession, confidence: float
) -> None:
    await _insert_source(db_session)
    await db_session.flush()
    await _insert_raw_message(db_session)
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO lead_analysis (raw_message_id, is_lead, confidence) "
                "SELECT id, true, :c FROM raw_messages LIMIT 1"
            ),
            {"c": confidence},
        )
        await db_session.flush()


# --- FK RESTRICT + UNIQUE ---------------------------------------------------


async def test_fk_restrict_prevents_source_delete_with_messages(
    db_session: AsyncSession,
) -> None:
    await _insert_source(db_session)
    await db_session.flush()
    await _insert_raw_message(db_session)
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await db_session.execute(text("DELETE FROM telegram_sources"))
        await db_session.flush()


async def test_unique_source_chat_id(db_session: AsyncSession) -> None:
    await db_session.execute(
        text(
            "INSERT INTO telegram_sources (chat_id, title, source_type) "
            "VALUES (42, 'a', 'channel')"
        )
    )
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO telegram_sources (chat_id, title, source_type) "
                "VALUES (42, 'b', 'group')"
            )
        )
        await db_session.flush()


async def test_unique_raw_messages_source_and_telegram_id(
    db_session: AsyncSession,
) -> None:
    await _insert_source(db_session)
    await db_session.flush()
    await _insert_raw_message(db_session, telegram_message_id=777)
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await _insert_raw_message(db_session, telegram_message_id=777)
        await db_session.flush()


async def test_unique_sender_profiles_telegram_user_id(db_session: AsyncSession) -> None:
    await db_session.execute(text("INSERT INTO sender_profiles (telegram_user_id) VALUES (123)"))
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("INSERT INTO sender_profiles (telegram_user_id) VALUES (123)")
        )
        await db_session.flush()


async def test_unique_keyword_triggers_keyword_language(db_session: AsyncSession) -> None:
    await db_session.execute(
        text(
            "INSERT INTO keyword_triggers (keyword, trigger_type, language) "
            "VALUES ('need CTO', 'direct_request', 'ru')"
        )
    )
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO keyword_triggers (keyword, trigger_type, language) "
                "VALUES ('need CTO', 'pain_signal', 'ru')"
            )
        )
        await db_session.flush()


# --- JSONB + TIMESTAMPTZ ----------------------------------------------------


async def test_red_flags_jsonb_roundtrip(db_session: AsyncSession) -> None:
    await _insert_source(db_session)
    await db_session.flush()
    await _insert_raw_message(db_session)
    await db_session.flush()
    await db_session.execute(
        text(
            "INSERT INTO lead_analysis (raw_message_id, is_lead, red_flags) "
            "SELECT id, true, CAST(:rf AS jsonb) FROM raw_messages LIMIT 1"
        ),
        {"rf": '["spam", "recruiter"]'},
    )
    row = (await db_session.execute(text("SELECT red_flags FROM lead_analysis"))).one()
    assert row[0] == ["spam", "recruiter"]


async def test_red_flags_default_empty_list(db_session: AsyncSession) -> None:
    await _insert_source(db_session)
    await db_session.flush()
    await _insert_raw_message(db_session)
    await db_session.flush()
    await db_session.execute(
        text(
            "INSERT INTO lead_analysis (raw_message_id, is_lead) "
            "SELECT id, true FROM raw_messages LIMIT 1"
        )
    )
    row = (await db_session.execute(text("SELECT red_flags FROM lead_analysis"))).one()
    assert row[0] == []


async def test_timestamptz_round_trip_preserves_instant(db_session: AsyncSession) -> None:
    """A tz-aware datetime in Yekaterinburg must round-trip to the same instant."""

    yekb = timezone(timedelta(hours=5))
    local = datetime(2026, 4, 24, 15, 30, 0, tzinfo=yekb)

    await _insert_source(db_session)
    await db_session.flush()
    await _insert_raw_message(db_session, sent_at=local)
    await db_session.flush()

    row = (await db_session.execute(text("SELECT sent_at FROM raw_messages"))).one()
    stored: datetime = row[0]
    assert stored.tzinfo is not None
    assert stored == local  # same instant in time
    assert stored.utcoffset() == timedelta(0)  # driver returns UTC
