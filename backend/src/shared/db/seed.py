"""Idempotent loader for ``backend/seeds/*.yaml`` (FEATURE-02 + FEATURE-04).

Run as ``python -m shared.db.seed`` (or via ``make seed``). Loads the
starting set of Telegram sources and the keyword-trigger dictionary into
Postgres. Re-running is safe: existing rows are matched by their natural
key and updated; new rows are inserted.

Sources are matched by ``lower(username)`` since ``chat_id`` is unknown
until the listener resolves it on first connect (migration 0002).
Triggers use the ``(keyword, language)`` UNIQUE constraint with
``INSERT … ON CONFLICT DO UPDATE``.

The module reads ``DATABASE_URL`` from the environment directly so it
can be invoked without the full :class:`shared.config.Settings` schema
(which requires Telegram/LLM/notification secrets even for a one-off
data load). Tests supply their own ``AsyncSession`` and bypass the CLI
entry point entirely.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

SEEDS_DIR = Path(__file__).resolve().parents[3] / "seeds"
SOURCES_YAML = SEEDS_DIR / "sources.yaml"
TRIGGERS_YAML = SEEDS_DIR / "keyword_triggers.yaml"

_REQUIRED_SOURCE_FIELDS = ("title", "username", "source_type", "category", "priority")
_REQUIRED_TRIGGER_FIELDS = ("keyword", "trigger_type", "weight", "language")


def load_yaml(path: Path, top_key: str) -> list[dict[str, Any]]:
    """Parse a seed YAML file and return rows under ``top_key``.

    The YAML is expected to be a mapping with a single top-level key
    (e.g. ``sources:`` or ``triggers:``) whose value is a list of
    homogeneous dicts.
    """

    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict) or top_key not in data:
        raise ValueError(f"{path}: missing top-level key '{top_key}'")
    rows = data[top_key]
    if not isinstance(rows, list):
        raise ValueError(f"{path}: '{top_key}' must be a list")
    return rows


def _validate_row(row: dict[str, Any], required: tuple[str, ...], where: str) -> None:
    missing = [f for f in required if row.get(f) in (None, "")]
    if missing:
        raise ValueError(f"{where}: row missing required fields {missing}: {row!r}")


async def seed_sources(session: AsyncSession, rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Upsert rows into ``telegram_sources``, matched by ``lower(username)``.

    ``chat_id`` is left NULL on insert; the listener back-fills it. Rows
    without ``username`` are rejected — there is no other natural key
    we can use to make the seed idempotent.
    """

    inserted = 0
    updated = 0
    for row in rows:
        _validate_row(row, _REQUIRED_SOURCE_FIELDS, "sources.yaml")

        params = {
            "title": row["title"],
            "username": row["username"],
            "source_type": row["source_type"],
            "category": row.get("category"),
            "priority": int(row["priority"]),
            "is_active": bool(row.get("is_active", True)),
        }

        existing = await session.execute(
            text("SELECT id FROM telegram_sources WHERE lower(username) = lower(:username)"),
            {"username": params["username"]},
        )
        existing_id = existing.scalar_one_or_none()

        if existing_id is None:
            await session.execute(
                text(
                    "INSERT INTO telegram_sources "
                    "(title, username, source_type, category, priority, is_active) "
                    "VALUES (:title, :username, :source_type, :category, "
                    ":priority, :is_active)"
                ),
                params,
            )
            inserted += 1
        else:
            await session.execute(
                text(
                    "UPDATE telegram_sources SET "
                    "title = :title, source_type = :source_type, "
                    "category = :category, priority = :priority, "
                    "is_active = :is_active "
                    "WHERE id = :id"
                ),
                {**params, "id": existing_id},
            )
            updated += 1

    return {"inserted": inserted, "updated": updated}


async def seed_triggers(session: AsyncSession, rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Upsert rows into ``keyword_triggers`` via ON CONFLICT (keyword, language).

    ``xmax = 0`` distinguishes insert from update in PostgreSQL: a row
    just inserted has no transaction-end stamp, an updated row inherits
    one from the prior version. This avoids a separate SELECT round-trip.
    """

    inserted = 0
    updated = 0
    for row in rows:
        _validate_row(row, _REQUIRED_TRIGGER_FIELDS, "keyword_triggers.yaml")

        params = {
            "keyword": row["keyword"],
            "trigger_type": row["trigger_type"],
            "weight": int(row["weight"]),
            "language": row["language"],
            "is_active": bool(row.get("is_active", True)),
        }

        result = await session.execute(
            text(
                "INSERT INTO keyword_triggers "
                "(keyword, trigger_type, weight, language, is_active) "
                "VALUES (:keyword, :trigger_type, :weight, :language, :is_active) "
                "ON CONFLICT (keyword, language) DO UPDATE SET "
                "trigger_type = EXCLUDED.trigger_type, "
                "weight = EXCLUDED.weight, "
                "is_active = EXCLUDED.is_active "
                "RETURNING (xmax = 0) AS was_insert"
            ),
            params,
        )
        was_insert = result.scalar_one()
        if was_insert:
            inserted += 1
        else:
            updated += 1

    return {"inserted": inserted, "updated": updated}


async def seed_all(session: AsyncSession) -> dict[str, dict[str, int]]:
    """Run both seeders against ``session`` (caller commits)."""

    sources = await seed_sources(session, load_yaml(SOURCES_YAML, "sources"))
    triggers = await seed_triggers(session, load_yaml(TRIGGERS_YAML, "triggers"))
    return {"sources": sources, "triggers": triggers}


def _database_url_from_env() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL must be set in the environment to run seed.")
    return url


async def _cli() -> int:
    engine = create_async_engine(_database_url_from_env(), future=True)
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with sm() as session:
            counts = await seed_all(session)
            await session.commit()
    finally:
        await engine.dispose()

    print(
        f"sources: inserted={counts['sources']['inserted']} updated={counts['sources']['updated']}"
    )
    print(
        f"triggers: inserted={counts['triggers']['inserted']} "
        f"updated={counts['triggers']['updated']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_cli()))
