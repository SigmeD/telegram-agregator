"""Integration tests for shared.db.seed + migration 0002 (chat_id nullable)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.seed import (
    SOURCES_YAML,
    TRIGGERS_YAML,
    load_yaml,
    seed_sources,
    seed_triggers,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# ---- migration 0002: chat_id nullable + partial unique --------------------


async def test_chat_id_now_nullable(db_session: AsyncSession) -> None:
    await db_session.execute(
        text(
            "INSERT INTO telegram_sources (title, source_type) "
            "VALUES ('pending source', 'channel')"
        )
    )
    await db_session.flush()
    row = (
        await db_session.execute(
            text("SELECT chat_id FROM telegram_sources WHERE title = 'pending source'")
        )
    ).one()
    assert row[0] is None


async def test_partial_unique_allows_multiple_null_chat_ids(
    db_session: AsyncSession,
) -> None:
    """NULL ≠ NULL under the partial unique index, so two NULLs coexist."""

    await db_session.execute(
        text(
            "INSERT INTO telegram_sources (title, source_type) "
            "VALUES ('a', 'channel'), ('b', 'group')"
        )
    )
    await db_session.flush()
    count = (
        await db_session.execute(
            text("SELECT count(*) FROM telegram_sources WHERE chat_id IS NULL")
        )
    ).scalar_one()
    assert count == 2


async def test_partial_unique_still_rejects_duplicate_non_null_chat_id(
    db_session: AsyncSession,
) -> None:
    await db_session.execute(
        text(
            "INSERT INTO telegram_sources (chat_id, title, source_type) "
            "VALUES (-1001234, 'a', 'channel')"
        )
    )
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO telegram_sources (chat_id, title, source_type) "
                "VALUES (-1001234, 'b', 'group')"
            )
        )
        await db_session.flush()


async def test_partial_unique_index_has_where_clause(
    db_session: AsyncSession,
) -> None:
    row = (
        await db_session.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE indexname = 'uq_telegram_sources_chat_id'"
            )
        )
    ).one()
    assert "WHERE" in row[0].upper()
    assert "IS NOT NULL" in row[0].upper()


# ---- seed_sources ---------------------------------------------------------


_SOURCE_FIXTURE: list[dict[str, Any]] = [
    {
        "title": "Test Founders Chat",
        "username": "testfounders",
        "source_type": "supergroup",
        "category": "founders_chat",
        "priority": 9,
        "is_active": True,
    },
    {
        "title": "Test VC News",
        "username": "testvc",
        "source_type": "channel",
        "category": "vc_news",
        "priority": 6,
        "is_active": True,
    },
]


async def test_seed_sources_inserts_all_on_empty_db(db_session: AsyncSession) -> None:
    counts = await seed_sources(db_session, _SOURCE_FIXTURE)
    await db_session.flush()

    assert counts == {"inserted": 2, "updated": 0}
    rows = (
        await db_session.execute(
            text(
                "SELECT username, priority, chat_id FROM telegram_sources "
                "ORDER BY username"
            )
        )
    ).all()
    assert [(r[0], r[1], r[2]) for r in rows] == [
        ("testfounders", 9, None),
        ("testvc", 6, None),
    ]


async def test_seed_sources_idempotent(db_session: AsyncSession) -> None:
    first = await seed_sources(db_session, _SOURCE_FIXTURE)
    await db_session.flush()
    second = await seed_sources(db_session, _SOURCE_FIXTURE)
    await db_session.flush()

    assert first == {"inserted": 2, "updated": 0}
    assert second == {"inserted": 0, "updated": 2}
    total = (
        await db_session.execute(text("SELECT count(*) FROM telegram_sources"))
    ).scalar_one()
    assert total == 2


async def test_seed_sources_updates_existing_fields(db_session: AsyncSession) -> None:
    await seed_sources(db_session, _SOURCE_FIXTURE)
    await db_session.flush()

    bumped = [{**_SOURCE_FIXTURE[0], "priority": 3, "title": "Renamed"}]
    counts = await seed_sources(db_session, bumped)
    await db_session.flush()
    assert counts == {"inserted": 0, "updated": 1}

    row = (
        await db_session.execute(
            text(
                "SELECT title, priority FROM telegram_sources "
                "WHERE username = 'testfounders'"
            )
        )
    ).one()
    assert row == ("Renamed", 3)


async def test_seed_sources_username_match_is_case_insensitive(
    db_session: AsyncSession,
) -> None:
    await seed_sources(db_session, _SOURCE_FIXTURE)
    await db_session.flush()

    same_row_diff_case = [{**_SOURCE_FIXTURE[0], "username": "TestFounders"}]
    counts = await seed_sources(db_session, same_row_diff_case)
    await db_session.flush()

    assert counts == {"inserted": 0, "updated": 1}
    total = (
        await db_session.execute(text("SELECT count(*) FROM telegram_sources"))
    ).scalar_one()
    assert total == 2


async def test_seed_sources_rejects_row_without_username(
    db_session: AsyncSession,
) -> None:
    bad = [{"title": "no handle", "source_type": "channel", "priority": 5}]
    with pytest.raises(ValueError, match="username"):
        await seed_sources(db_session, bad)


async def test_seed_sources_rejects_invalid_priority(db_session: AsyncSession) -> None:
    bad = [{**_SOURCE_FIXTURE[0], "priority": 99}]
    with pytest.raises(IntegrityError):
        await seed_sources(db_session, bad)
        await db_session.flush()


# ---- seed_triggers --------------------------------------------------------


_TRIGGER_FIXTURE: list[dict[str, Any]] = [
    {
        "keyword": "ищу разработчика тест",
        "trigger_type": "direct_request",
        "weight": 10,
        "language": "ru",
        "is_active": True,
    },
    {
        "keyword": "need CTO test",
        "trigger_type": "direct_request",
        "weight": 10,
        "language": "en",
        "is_active": True,
    },
]


async def test_seed_triggers_inserts_all_on_empty_db(db_session: AsyncSession) -> None:
    counts = await seed_triggers(db_session, _TRIGGER_FIXTURE)
    await db_session.flush()

    assert counts == {"inserted": 2, "updated": 0}
    total = (
        await db_session.execute(text("SELECT count(*) FROM keyword_triggers"))
    ).scalar_one()
    assert total == 2


async def test_seed_triggers_idempotent(db_session: AsyncSession) -> None:
    first = await seed_triggers(db_session, _TRIGGER_FIXTURE)
    await db_session.flush()
    second = await seed_triggers(db_session, _TRIGGER_FIXTURE)
    await db_session.flush()

    assert first == {"inserted": 2, "updated": 0}
    assert second == {"inserted": 0, "updated": 2}


async def test_seed_triggers_updates_weight_and_type(db_session: AsyncSession) -> None:
    await seed_triggers(db_session, _TRIGGER_FIXTURE)
    await db_session.flush()

    bumped = [
        {**_TRIGGER_FIXTURE[0], "weight": 7, "trigger_type": "pain_signal"}
    ]
    counts = await seed_triggers(db_session, bumped)
    await db_session.flush()
    assert counts == {"inserted": 0, "updated": 1}

    row = (
        await db_session.execute(
            text(
                "SELECT trigger_type, weight FROM keyword_triggers "
                "WHERE keyword = 'ищу разработчика тест' AND language = 'ru'"
            )
        )
    ).one()
    assert row == ("pain_signal", 7)


async def test_seed_triggers_distinct_languages_are_separate_rows(
    db_session: AsyncSession,
) -> None:
    rows = [
        {**_TRIGGER_FIXTURE[0], "language": "ru"},
        {**_TRIGGER_FIXTURE[0], "language": "en"},
    ]
    counts = await seed_triggers(db_session, rows)
    await db_session.flush()
    assert counts == {"inserted": 2, "updated": 0}


async def test_seed_triggers_rejects_invalid_trigger_type(
    db_session: AsyncSession,
) -> None:
    bad = [{**_TRIGGER_FIXTURE[0], "trigger_type": "bogus"}]
    with pytest.raises(IntegrityError):
        await seed_triggers(db_session, bad)
        await db_session.flush()


# ---- real seed YAMLs (smoke) ----------------------------------------------


async def test_real_yaml_sources_load_and_apply(db_session: AsyncSession) -> None:
    rows = load_yaml(SOURCES_YAML, "sources")
    assert len(rows) >= 30, f"TZ requires 30+ sources, got {len(rows)}"

    counts = await seed_sources(db_session, rows)
    await db_session.flush()
    assert counts["inserted"] == len(rows)

    total = (
        await db_session.execute(text("SELECT count(*) FROM telegram_sources"))
    ).scalar_one()
    assert total == len(rows)


async def test_real_yaml_triggers_load_and_apply(db_session: AsyncSession) -> None:
    rows = load_yaml(TRIGGERS_YAML, "triggers")
    assert len(rows) >= 25, f"keyword dictionary too thin: {len(rows)}"

    counts = await seed_triggers(db_session, rows)
    await db_session.flush()
    assert counts["inserted"] == len(rows)
