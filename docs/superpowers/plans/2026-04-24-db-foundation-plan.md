# DB Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship 5 SQLAlchemy ORM models + migration `0001_initial` + integration tests against real Postgres, matching the schemas in ТЗ literally plus a small set of explicit deviations documented in ADR-0008.

**Architecture:** Each ORM model lives in its own module under `backend/src/shared/db/tables/` and is re-exported through `backend/src/shared/db/models.py` so Alembic autogenerate finds them. `Base.metadata` uses a project-wide `naming_convention` so constraint/index names are deterministic. The migration is authored by hand (not pure autogenerate) to emit `CHECK` constraints, partial indexes, and FK `ON DELETE RESTRICT`. Integration tests spin up Postgres 15 via the existing `testcontainers` fixture, apply the migration, and verify every CHECK/FK/UNIQUE/JSONB/TIMESTAMPTZ/partial-index behavior is enforced.

**Tech Stack:** Python 3.11+, SQLAlchemy 2.0 (async), Alembic 1.13, asyncpg, PostgreSQL 15, pytest 8, testcontainers 4.

**Spec:** [`docs/superpowers/specs/2026-04-24-db-foundation-design.md`](../specs/2026-04-24-db-foundation-design.md)

**Working directory:** All paths in this plan are relative to repo root (`D:\Projects\telegram-agregator`). Commands prefixed `(cd backend && …)` run from the `backend/` subdir where `pyproject.toml` and pytest config live.

**Branch:** `feature/db-foundation` (already checked out from `origin/develop`, spec already committed).

---

## Task 1: Naming convention on `Base.metadata`

**Files:**
- Modify: `backend/src/shared/db/session.py`
- Test: `backend/tests/unit/test_db_metadata.py`

- [ ] **Step 1.1: Write the failing unit test**

Create `backend/tests/unit/test_db_metadata.py`:

```python
"""Naming convention + metadata regression guards for shared.db.Base."""

from __future__ import annotations

import pytest

from shared.db.session import Base

pytestmark = pytest.mark.unit


def test_base_metadata_has_project_naming_convention() -> None:
    """Alembic autogenerate relies on stable constraint/index names.

    Changing these without bumping a migration breaks diff detection.
    """

    nc = Base.metadata.naming_convention
    assert nc["ix"] == "ix_%(column_0_label)s"
    assert nc["uq"] == "uq_%(table_name)s_%(column_0_name)s"
    assert nc["ck"] == "ck_%(table_name)s_%(constraint_name)s"
    assert (
        nc["fk"]
        == "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
    )
    assert nc["pk"] == "pk_%(table_name)s"
```

- [ ] **Step 1.2: Run test, see it fail**

Run: `(cd backend && pytest tests/unit/test_db_metadata.py -v)`
Expected: FAIL — `KeyError: 'ix'` (default `MetaData` has no `naming_convention`).

- [ ] **Step 1.3: Update `Base` to pass custom `MetaData`**

Replace the `class Base(DeclarativeBase):` block in `backend/src/shared/db/session.py` (line 24) with:

```python
from sqlalchemy import MetaData
# ... (keep existing imports)

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for all ORM models.

    The custom ``MetaData`` naming convention makes Alembic autogenerate
    produce deterministic constraint/index names — changing a name is a
    schema migration, not an accident.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
```

- [ ] **Step 1.4: Run test, see it pass**

Run: `(cd backend && pytest tests/unit/test_db_metadata.py -v)`
Expected: PASS (`test_base_metadata_has_project_naming_convention PASSED`).

- [ ] **Step 1.5: Lint**

Run: `(cd backend && ruff check src/shared/db/session.py tests/unit/test_db_metadata.py && black --check src/shared/db/session.py tests/unit/test_db_metadata.py)`
Expected: no findings.

- [ ] **Step 1.6: Commit**

```bash
git add backend/src/shared/db/session.py backend/tests/unit/test_db_metadata.py
git commit -m "feat(db): add naming convention to Base.metadata"
```

---

## Task 2: Create `tables/` package skeleton

**Files:**
- Create: `backend/src/shared/db/tables/__init__.py`
- Modify: `backend/src/shared/db/models.py`

- [ ] **Step 2.1: Extend the metadata unit test to assert the 5 tables are registered (RED)**

Append to `backend/tests/unit/test_db_metadata.py`:

```python
EXPECTED_TABLES: frozenset[str] = frozenset(
    {
        "telegram_sources",
        "raw_messages",
        "keyword_triggers",
        "lead_analysis",
        "sender_profiles",
    }
)


def test_base_metadata_registers_all_domain_tables() -> None:
    """All 5 domain tables are importable and registered on Base.metadata.

    Regression guard: if someone moves a model out of the ``tables/``
    package, Alembic autogenerate silently stops seeing it.
    """

    # Force import so mappers register.
    import shared.db.models  # noqa: F401

    assert EXPECTED_TABLES.issubset(Base.metadata.tables.keys())
```

- [ ] **Step 2.2: Run — expect fail (no tables registered)**

Run: `(cd backend && pytest tests/unit/test_db_metadata.py::test_base_metadata_registers_all_domain_tables -v)`
Expected: FAIL — `AssertionError` or `ModuleNotFoundError: shared.db.tables` (the package doesn't exist yet).

- [ ] **Step 2.3: Create the empty `tables/__init__.py`**

Create `backend/src/shared/db/tables/__init__.py`:

```python
"""Domain ORM tables.

One module per table. ``__all__`` below is the public surface; anything
not listed here is an implementation detail and must not be imported
from outside this package.
"""

from __future__ import annotations

__all__: list[str] = []
```

- [ ] **Step 2.4: Re-export from `models.py`**

Replace the entire contents of `backend/src/shared/db/models.py` with:

```python
"""Aggregated re-exports of all ORM models.

Alembic's ``env.py`` imports this module so autogenerate can see every
mapper registered on :class:`shared.db.session.Base`. Individual models
live under :mod:`shared.db.tables`; add new ones there and extend
``tables.__all__`` to expose them.
"""

from __future__ import annotations

from shared.db.session import Base
from shared.db.tables import *  # noqa: F401,F403 — side-effect import for mappers

__all__ = ["Base"]
```

- [ ] **Step 2.5: Re-run the test — STILL expected to fail (tables not defined yet)**

Run: `(cd backend && pytest tests/unit/test_db_metadata.py::test_base_metadata_registers_all_domain_tables -v)`
Expected: FAIL with `AssertionError` — assertion now works, but the 5 tables haven't been defined yet. That failure will be resolved by Tasks 3–7. Leave it red.

- [ ] **Step 2.6: Commit infrastructure**

```bash
git add backend/src/shared/db/tables/__init__.py backend/src/shared/db/models.py backend/tests/unit/test_db_metadata.py
git commit -m "feat(db): scaffold tables/ package, aggregate models"
```

---

## Task 3: `telegram_sources` model

**Files:**
- Create: `backend/src/shared/db/tables/telegram_source.py`
- Modify: `backend/src/shared/db/tables/__init__.py`

- [ ] **Step 3.1: RED — the metadata test from Task 2 is still failing. That's our "red" for this task.**

Run: `(cd backend && pytest tests/unit/test_db_metadata.py::test_base_metadata_registers_all_domain_tables -v)`
Expected: FAIL — `AssertionError` (table `telegram_sources` not in metadata).

- [ ] **Step 3.2: Implement the model**

Create `backend/src/shared/db/tables/telegram_source.py`:

```python
"""ORM model for the ``telegram_sources`` table — monitored chats/channels.

Schema matches ТЗ FEATURE-02 literally, with explicit ``priority``
bounds (documented in ADR-0008).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.session import Base


class TelegramSource(Base):
    """A chat, group, or channel we listen to."""

    __tablename__ = "telegram_sources"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('channel','group','supergroup')",
            name="source_type_valid",
        ),
        CheckConstraint(
            "priority BETWEEN 1 AND 10",
            name="priority_in_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_messages_processed: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    relevant_leads_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
```

- [ ] **Step 3.3: Expose it via `tables.__all__`**

Replace `backend/src/shared/db/tables/__init__.py` body:

```python
"""Domain ORM tables."""

from __future__ import annotations

from shared.db.tables.telegram_source import TelegramSource

__all__ = ["TelegramSource"]
```

- [ ] **Step 3.4: Run the metadata test — expect `telegram_sources` now in the set (other 4 still missing)**

Run: `(cd backend && pytest tests/unit/test_db_metadata.py -v)`
Expected: `test_base_metadata_registers_all_domain_tables` still FAILS (4 tables still missing), but the fail message now shows only `raw_messages, keyword_triggers, lead_analysis, sender_profiles` in the diff. `test_base_metadata_has_project_naming_convention` still PASSES.

- [ ] **Step 3.5: Lint**

Run: `(cd backend && ruff check src/shared/db/tables/telegram_source.py && black --check src/shared/db/tables/telegram_source.py && mypy src/shared/db/tables/telegram_source.py)`
Expected: no findings.

- [ ] **Step 3.6: Commit**

```bash
git add backend/src/shared/db/tables/telegram_source.py backend/src/shared/db/tables/__init__.py
git commit -m "feat(db): TelegramSource model"
```

---

## Task 4: `raw_messages` model

**Files:**
- Create: `backend/src/shared/db/tables/raw_message.py`
- Modify: `backend/src/shared/db/tables/__init__.py`

- [ ] **Step 4.1: RED — metadata test still failing on `raw_messages`**

Run: `(cd backend && pytest tests/unit/test_db_metadata.py::test_base_metadata_registers_all_domain_tables -v)`
Expected: FAIL — `raw_messages` still missing.

- [ ] **Step 4.2: Implement the model**

Create `backend/src/shared/db/tables/raw_message.py`:

```python
"""ORM model for the ``raw_messages`` table — every message we observe.

Schema matches ТЗ FEATURE-03. FK to ``telegram_sources`` uses
``ON DELETE RESTRICT`` so listener data stays intact for re-training.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.session import Base


class RawMessage(Base):
    """A raw Telegram message captured by the listener.

    ``processing_status`` tracks the downstream pipeline:
    ``pending`` → ``filtered_out`` | ``analyzing`` → ``lead`` | ``not_lead`` | ``error``.
    """

    __tablename__ = "raw_messages"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "telegram_message_id",
            name="uq_raw_messages_source_id_telegram_message_id",
        ),
        CheckConstraint(
            "processing_status IN ("
            "'pending','filtered_out','analyzing','lead','not_lead','error'"
            ")",
            name="processing_status_valid",
        ),
        Index(
            "ix_raw_messages_processing_status",
            "processing_status",
        ),
        Index(
            "ix_raw_messages_sent_at_desc",
            "sent_at",
        ),
        Index(
            "ix_raw_messages_source_id_sent_at",
            "source_id",
            "sent_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("telegram_sources.id", ondelete="RESTRICT"),
        nullable=False,
    )
    telegram_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sender_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sender_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sender_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    message_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_media: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    media_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reply_to_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    thread_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processing_status: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="pending"
    )
```

> Note: `ix_raw_messages_sent_at_desc` is declared as a plain index on `sent_at`. Alembic autogenerate will emit it as-is. The `DESC` ordering is applied in the migration file by hand (Task 9), since SQLAlchemy `Index(..., Column.desc())` requires a reference to the Column object that complicates things here and the DESC sort only matters for `ORDER BY` queries, not INSERT/UPDATE paths.

- [ ] **Step 4.3: Re-export**

Replace `backend/src/shared/db/tables/__init__.py`:

```python
"""Domain ORM tables."""

from __future__ import annotations

from shared.db.tables.raw_message import RawMessage
from shared.db.tables.telegram_source import TelegramSource

__all__ = ["RawMessage", "TelegramSource"]
```

- [ ] **Step 4.4: Run metadata test**

Run: `(cd backend && pytest tests/unit/test_db_metadata.py -v)`
Expected: still FAIL on `test_base_metadata_registers_all_domain_tables` — 3 tables missing (keyword_triggers, lead_analysis, sender_profiles).

- [ ] **Step 4.5: Lint**

Run: `(cd backend && ruff check src/shared/db/tables/raw_message.py && black --check src/shared/db/tables/raw_message.py && mypy src/shared/db/tables/raw_message.py)`
Expected: no findings.

- [ ] **Step 4.6: Commit**

```bash
git add backend/src/shared/db/tables/raw_message.py backend/src/shared/db/tables/__init__.py
git commit -m "feat(db): RawMessage model with FK RESTRICT + composite UNIQUE"
```

---

## Task 5: `keyword_triggers` model

**Files:**
- Create: `backend/src/shared/db/tables/keyword_trigger.py`
- Modify: `backend/src/shared/db/tables/__init__.py`

- [ ] **Step 5.1: RED — metadata test still failing on `keyword_triggers`**

Run: `(cd backend && pytest tests/unit/test_db_metadata.py::test_base_metadata_registers_all_domain_tables -v)`
Expected: FAIL — 3 tables missing.

- [ ] **Step 5.2: Implement the model**

Create `backend/src/shared/db/tables/keyword_trigger.py`:

```python
"""ORM model for the ``keyword_triggers`` dictionary (FEATURE-04).

The keyword filter is data-driven: adding/removing a trigger is a DB
change, not a code change (see BR-014). ``(keyword, language)`` is
UNIQUE — duplicate triggers would double-count in score sums.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.session import Base


class KeywordTrigger(Base):
    """A single trigger phrase used by the keyword filter."""

    __tablename__ = "keyword_triggers"
    __table_args__ = (
        UniqueConstraint(
            "keyword",
            "language",
            name="uq_keyword_triggers_keyword_language",
        ),
        CheckConstraint(
            "trigger_type IN ('direct_request','pain_signal','lifecycle_event','negative')",
            name="trigger_type_valid",
        ),
        # Partial index on active triggers — the listener queries `WHERE is_active = true`
        # every time it rebuilds its in-memory dictionary. Declared here so Alembic
        # autogenerate picks it up; the `postgresql_where` kwarg emits the WHERE clause.
        Index(
            "ix_keyword_triggers_active_type",
            "is_active",
            "trigger_type",
            postgresql_where=text("is_active = true"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    keyword: Mapped[str] = mapped_column(String(200), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    language: Mapped[str] = mapped_column(String(10), nullable=False, server_default="ru")
```

- [ ] **Step 5.3: Re-export**

Replace `backend/src/shared/db/tables/__init__.py`:

```python
"""Domain ORM tables."""

from __future__ import annotations

from shared.db.tables.keyword_trigger import KeywordTrigger
from shared.db.tables.raw_message import RawMessage
from shared.db.tables.telegram_source import TelegramSource

__all__ = ["KeywordTrigger", "RawMessage", "TelegramSource"]
```

- [ ] **Step 5.4: Run metadata test**

Run: `(cd backend && pytest tests/unit/test_db_metadata.py -v)`
Expected: still FAIL — 2 tables missing (lead_analysis, sender_profiles).

- [ ] **Step 5.5: Lint**

Run: `(cd backend && ruff check src/shared/db/tables/keyword_trigger.py && black --check src/shared/db/tables/keyword_trigger.py && mypy src/shared/db/tables/keyword_trigger.py)`

- [ ] **Step 5.6: Commit**

```bash
git add backend/src/shared/db/tables/keyword_trigger.py backend/src/shared/db/tables/__init__.py
git commit -m "feat(db): KeywordTrigger model with partial active index"
```

---

## Task 6: `lead_analysis` model

**Files:**
- Create: `backend/src/shared/db/tables/lead_analysis.py`
- Modify: `backend/src/shared/db/tables/__init__.py`

- [ ] **Step 6.1: RED — 2 tables still missing**

Run: `(cd backend && pytest tests/unit/test_db_metadata.py::test_base_metadata_registers_all_domain_tables -v)`

- [ ] **Step 6.2: Implement the model**

Create `backend/src/shared/db/tables/lead_analysis.py`:

```python
"""ORM model for the ``lead_analysis`` table (FEATURE-05).

One row per LLM call. Stored denormalised on purpose — we want the
exact prompt/model trace for each analysis, immutable for audit.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.session import Base


class LeadAnalysis(Base):
    """Structured LLM verdict on a single ``raw_messages`` row."""

    __tablename__ = "lead_analysis"
    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_in_unit",
        ),
        CheckConstraint(
            "lead_type IS NULL OR lead_type IN ("
            "'direct_request','pain_signal','lifecycle_event','not_a_lead'"
            ")",
            name="lead_type_valid",
        ),
        CheckConstraint(
            "stage IS NULL OR stage IN ('idea','pre_mvp','mvp','growth','unknown')",
            name="stage_valid",
        ),
        CheckConstraint(
            "urgency IS NULL OR urgency IN ('high','medium','low')",
            name="urgency_valid",
        ),
        CheckConstraint(
            "budget_signals IS NULL OR budget_signals IN ('mentioned','implied','none')",
            name="budget_signals_valid",
        ),
        CheckConstraint(
            "vertical IS NULL OR vertical IN ("
            "'fintech','saas','marketplace','edtech','other','unknown'"
            ")",
            name="vertical_valid",
        ),
        CheckConstraint(
            "recommended_action IS NULL OR recommended_action IN ("
            "'contact_now','contact_soon','monitor','ignore'"
            ")",
            name="recommended_action_valid",
        ),
        Index("ix_lead_analysis_raw_message_id", "raw_message_id"),
        # Partial index — most dashboard queries ask "latest real leads".
        Index(
            "ix_lead_analysis_is_lead_analyzed_at",
            "analyzed_at",
            postgresql_where=text("is_lead = true"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    raw_message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_messages.id", ondelete="RESTRICT"),
        nullable=False,
    )
    is_lead: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    lead_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    urgency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    budget_signals: Mapped[str | None] = mapped_column(String(20), nullable=True)
    vertical: Mapped[str | None] = mapped_column(String(50), nullable=True)
    extracted_needs: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(String(50), nullable=True)
    recommended_approach: Mapped[str | None] = mapped_column(Text, nullable=True)
    red_flags: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

- [ ] **Step 6.3: Re-export**

Replace `backend/src/shared/db/tables/__init__.py`:

```python
"""Domain ORM tables."""

from __future__ import annotations

from shared.db.tables.keyword_trigger import KeywordTrigger
from shared.db.tables.lead_analysis import LeadAnalysis
from shared.db.tables.raw_message import RawMessage
from shared.db.tables.telegram_source import TelegramSource

__all__ = ["KeywordTrigger", "LeadAnalysis", "RawMessage", "TelegramSource"]
```

- [ ] **Step 6.4: Run metadata test**

Run: `(cd backend && pytest tests/unit/test_db_metadata.py -v)`
Expected: still FAIL — 1 table missing (sender_profiles).

- [ ] **Step 6.5: Lint**

Run: `(cd backend && ruff check src/shared/db/tables/lead_analysis.py && black --check src/shared/db/tables/lead_analysis.py && mypy src/shared/db/tables/lead_analysis.py)`

- [ ] **Step 6.6: Commit**

```bash
git add backend/src/shared/db/tables/lead_analysis.py backend/src/shared/db/tables/__init__.py
git commit -m "feat(db): LeadAnalysis model with 7 CHECKs + partial is_lead index"
```

---

## Task 7: `sender_profiles` model

**Files:**
- Create: `backend/src/shared/db/tables/sender_profile.py`
- Modify: `backend/src/shared/db/tables/__init__.py`

- [ ] **Step 7.1: RED — 1 table still missing**

Run: `(cd backend && pytest tests/unit/test_db_metadata.py::test_base_metadata_registers_all_domain_tables -v)`

- [ ] **Step 7.2: Implement the model**

Create `backend/src/shared/db/tables/sender_profile.py`:

```python
"""ORM model for the ``sender_profiles`` table (FEATURE-07).

Not linked by FK to ``raw_messages`` on purpose — senders may appear
before we have any of their messages, and we sometimes delete a
message without wanting to drop the enriched profile.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.session import Base


class SenderProfile(Base):
    """Enriched author profile (bio, socials, founder-status)."""

    __tablename__ = "sender_profiles"
    __table_args__ = (
        CheckConstraint(
            "enrichment_status IN ('pending','in_progress','done','failed','skipped')",
            name="enrichment_status_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    twitter_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_founder_profile: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    company_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    company_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enrichment_status: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="pending"
    )
```

- [ ] **Step 7.3: Re-export**

Replace `backend/src/shared/db/tables/__init__.py`:

```python
"""Domain ORM tables."""

from __future__ import annotations

from shared.db.tables.keyword_trigger import KeywordTrigger
from shared.db.tables.lead_analysis import LeadAnalysis
from shared.db.tables.raw_message import RawMessage
from shared.db.tables.sender_profile import SenderProfile
from shared.db.tables.telegram_source import TelegramSource

__all__ = [
    "KeywordTrigger",
    "LeadAnalysis",
    "RawMessage",
    "SenderProfile",
    "TelegramSource",
]
```

- [ ] **Step 7.4: Run metadata test — now expect GREEN**

Run: `(cd backend && pytest tests/unit/test_db_metadata.py -v)`
Expected: both tests PASS — all 5 tables registered, naming convention intact.

- [ ] **Step 7.5: Lint**

Run: `(cd backend && ruff check src/shared/db && black --check src/shared/db && mypy src/shared/db)`
Expected: no findings across the whole `db/` package.

- [ ] **Step 7.6: Commit**

```bash
git add backend/src/shared/db/tables/sender_profile.py backend/src/shared/db/tables/__init__.py
git commit -m "feat(db): SenderProfile model — completes domain schema"
```

---

## Task 8: Integration conftest — async URL + applied-migrations fixture

**Files:**
- Create: `backend/tests/integration/conftest.py`

`backend/tests/conftest.py` already exposes `postgres_container` (session-scoped `PostgresContainer("postgres:15-alpine")`). We add a narrower conftest inside `tests/integration/` to expose (a) an async URL form and (b) a fixture that has already run `alembic upgrade head` on a clean database.

- [ ] **Step 8.1: Write the fixture file**

Create `backend/tests/integration/conftest.py`:

```python
"""Integration-only fixtures: async DB URL and a migrated Postgres."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

# Points to backend/migrations/alembic.ini.
_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "migrations" / "alembic.ini"


def _to_async_url(sync_url: str) -> str:
    """Convert a ``postgresql+psycopg2://…`` URL to ``postgresql+asyncpg://…``."""

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
    Use ``db_session`` (below) for auto-rollback per test.
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
async def db_session(db_engine: AsyncEngine) -> AsyncIterator:
    """A per-test session that rolls back at the end — no cleanup needed."""

    async_sm = async_sessionmaker(db_engine, expire_on_commit=False)
    async with async_sm() as session:
        try:
            yield session
        finally:
            await session.rollback()
```

- [ ] **Step 8.2: Ensure the integration package has an `__init__.py` (no-op if already there)**

Run: `ls backend/tests/integration/`
Expected output includes `__init__.py`. If not: create empty `backend/tests/integration/__init__.py`.

- [ ] **Step 8.3: Lint**

Run: `(cd backend && ruff check tests/integration/conftest.py && black --check tests/integration/conftest.py)`

- [ ] **Step 8.4: Commit**

```bash
git add backend/tests/integration/conftest.py
# Also add integration/__init__.py if this task created it.
git commit -m "test(db): integration conftest — async URL + migrated-db fixture"
```

---

## Task 9: Handwritten migration `0001_initial`

**Files:**
- Create: `backend/migrations/versions/0001_initial.py`

We write the migration by hand (not autogenerate) because:

1. We want full control over CHECK constraint emission (named, PG-portable).
2. Partial indexes require exact `postgresql_where` syntax.
3. Alembic autogenerate tends to re-order operations; hand-writing makes review simpler on a greenfield migration.

- [ ] **Step 9.1: RED — apply-migration test first**

Create `backend/tests/integration/test_migration_0001.py`:

```python
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
```

- [ ] **Step 9.2: Run — expect FAIL (file does not exist yet → alembic complains)**

Run: `(cd backend && pytest tests/integration/test_migration_0001.py -v)`
Expected: FAIL — `alembic.util.exc.CommandError: Can't locate revision …` or similar (no migration files in `versions/`).

- [ ] **Step 9.3: Write the migration file**

Create `backend/migrations/versions/0001_initial.py`:

```python
"""Initial schema: telegram_sources, raw_messages, keyword_triggers, lead_analysis, sender_profiles.

Revision ID: 0001
Revises:
Create Date: 2026-04-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- telegram_sources ----------------------------------------------------
    op.create_table(
        "telegram_sources",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("priority", sa.Integer(), server_default="5", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "total_messages_processed", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("relevant_leads_count", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint(
            "source_type IN ('channel','group','supergroup')",
            name="ck_telegram_sources_source_type_valid",
        ),
        sa.CheckConstraint(
            "priority BETWEEN 1 AND 10",
            name="ck_telegram_sources_priority_in_range",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_telegram_sources"),
        sa.UniqueConstraint("chat_id", name="uq_telegram_sources_chat_id"),
    )

    # ---- raw_messages --------------------------------------------------------
    op.create_table(
        "raw_messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("sender_id", sa.BigInteger(), nullable=True),
        sa.Column("sender_username", sa.String(length=100), nullable=True),
        sa.Column("sender_name", sa.String(length=500), nullable=True),
        sa.Column("message_text", sa.Text(), nullable=True),
        sa.Column("has_media", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("media_type", sa.String(length=50), nullable=True),
        sa.Column("reply_to_message_id", sa.BigInteger(), nullable=True),
        sa.Column("thread_id", sa.BigInteger(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "processing_status",
            sa.String(length=50),
            server_default="pending",
            nullable=False,
        ),
        sa.CheckConstraint(
            "processing_status IN "
            "('pending','filtered_out','analyzing','lead','not_lead','error')",
            name="ck_raw_messages_processing_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["telegram_sources.id"],
            name="fk_raw_messages_source_id_telegram_sources",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_raw_messages"),
        sa.UniqueConstraint(
            "source_id",
            "telegram_message_id",
            name="uq_raw_messages_source_id_telegram_message_id",
        ),
    )
    op.create_index(
        "ix_raw_messages_processing_status",
        "raw_messages",
        ["processing_status"],
    )
    # DESC index — emitted via raw SQL since Alembic's op.create_index syntax
    # for column-order-ascending is clumsy across dialects.
    op.execute("CREATE INDEX ix_raw_messages_sent_at_desc ON raw_messages (sent_at DESC)")
    op.create_index(
        "ix_raw_messages_source_id_sent_at",
        "raw_messages",
        ["source_id", "sent_at"],
    )

    # ---- keyword_triggers ----------------------------------------------------
    op.create_table(
        "keyword_triggers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("keyword", sa.String(length=200), nullable=False),
        sa.Column("trigger_type", sa.String(length=50), nullable=False),
        sa.Column("weight", sa.Integer(), server_default="1", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("language", sa.String(length=10), server_default="ru", nullable=False),
        sa.CheckConstraint(
            "trigger_type IN ('direct_request','pain_signal','lifecycle_event','negative')",
            name="ck_keyword_triggers_trigger_type_valid",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_keyword_triggers"),
        sa.UniqueConstraint(
            "keyword", "language", name="uq_keyword_triggers_keyword_language"
        ),
    )
    op.create_index(
        "ix_keyword_triggers_active_type",
        "keyword_triggers",
        ["is_active", "trigger_type"],
        postgresql_where=sa.text("is_active = true"),
    )

    # ---- lead_analysis -------------------------------------------------------
    op.create_table(
        "lead_analysis",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("raw_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_lead", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=True),
        sa.Column("lead_type", sa.String(length=50), nullable=True),
        sa.Column("stage", sa.String(length=50), nullable=True),
        sa.Column("urgency", sa.String(length=20), nullable=True),
        sa.Column("budget_signals", sa.String(length=20), nullable=True),
        sa.Column("vertical", sa.String(length=50), nullable=True),
        sa.Column("extracted_needs", sa.Text(), nullable=True),
        sa.Column("recommended_action", sa.String(length=50), nullable=True),
        sa.Column("recommended_approach", sa.Text(), nullable=True),
        sa.Column(
            "red_flags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("llm_model", sa.String(length=100), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column(
            "analyzed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_lead_analysis_confidence_in_unit",
        ),
        sa.CheckConstraint(
            "lead_type IS NULL OR lead_type IN "
            "('direct_request','pain_signal','lifecycle_event','not_a_lead')",
            name="ck_lead_analysis_lead_type_valid",
        ),
        sa.CheckConstraint(
            "stage IS NULL OR stage IN ('idea','pre_mvp','mvp','growth','unknown')",
            name="ck_lead_analysis_stage_valid",
        ),
        sa.CheckConstraint(
            "urgency IS NULL OR urgency IN ('high','medium','low')",
            name="ck_lead_analysis_urgency_valid",
        ),
        sa.CheckConstraint(
            "budget_signals IS NULL OR budget_signals IN "
            "('mentioned','implied','none')",
            name="ck_lead_analysis_budget_signals_valid",
        ),
        sa.CheckConstraint(
            "vertical IS NULL OR vertical IN "
            "('fintech','saas','marketplace','edtech','other','unknown')",
            name="ck_lead_analysis_vertical_valid",
        ),
        sa.CheckConstraint(
            "recommended_action IS NULL OR recommended_action IN "
            "('contact_now','contact_soon','monitor','ignore')",
            name="ck_lead_analysis_recommended_action_valid",
        ),
        sa.ForeignKeyConstraint(
            ["raw_message_id"],
            ["raw_messages.id"],
            name="fk_lead_analysis_raw_message_id_raw_messages",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_lead_analysis"),
    )
    op.create_index(
        "ix_lead_analysis_raw_message_id",
        "lead_analysis",
        ["raw_message_id"],
    )
    op.create_index(
        "ix_lead_analysis_is_lead_analyzed_at",
        "lead_analysis",
        ["analyzed_at"],
        postgresql_where=sa.text("is_lead = true"),
    )

    # ---- sender_profiles -----------------------------------------------------
    op.create_table(
        "sender_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=True),
        sa.Column("full_name", sa.String(length=500), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("linkedin_url", sa.String(length=500), nullable=True),
        sa.Column("website_url", sa.String(length=500), nullable=True),
        sa.Column("twitter_url", sa.String(length=500), nullable=True),
        sa.Column(
            "is_founder_profile",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("company_name", sa.String(length=500), nullable=True),
        sa.Column("company_stage", sa.String(length=50), nullable=True),
        sa.Column("enriched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "enrichment_status",
            sa.String(length=50),
            server_default="pending",
            nullable=False,
        ),
        sa.CheckConstraint(
            "enrichment_status IN "
            "('pending','in_progress','done','failed','skipped')",
            name="ck_sender_profiles_enrichment_status_valid",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sender_profiles"),
        sa.UniqueConstraint(
            "telegram_user_id", name="uq_sender_profiles_telegram_user_id"
        ),
    )


def downgrade() -> None:
    # Drop in reverse FK order.
    op.drop_table("sender_profiles")
    op.drop_index("ix_lead_analysis_is_lead_analyzed_at", table_name="lead_analysis")
    op.drop_index("ix_lead_analysis_raw_message_id", table_name="lead_analysis")
    op.drop_table("lead_analysis")
    op.drop_index("ix_keyword_triggers_active_type", table_name="keyword_triggers")
    op.drop_table("keyword_triggers")
    op.drop_index("ix_raw_messages_source_id_sent_at", table_name="raw_messages")
    op.execute("DROP INDEX IF EXISTS ix_raw_messages_sent_at_desc")
    op.drop_index("ix_raw_messages_processing_status", table_name="raw_messages")
    op.drop_table("raw_messages")
    op.drop_table("telegram_sources")
```

- [ ] **Step 9.4: Run — expect PASS on table creation test**

Run: `(cd backend && pytest tests/integration/test_migration_0001.py::test_migration_creates_all_expected_tables -v)`
Expected: PASS.

- [ ] **Step 9.5: Lint (migrations dir is under `migrations/**` in ruff's per-file-ignores → only style errors)**

Run: `(cd backend && ruff check migrations/versions/0001_initial.py)`
Expected: no findings.

- [ ] **Step 9.6: Commit**

```bash
git add backend/migrations/versions/0001_initial.py backend/tests/integration/test_migration_0001.py
git commit -m "feat(db): migration 0001_initial — 5 tables, CHECKs, partial indexes"
```

---

## Task 10: Integration tests — CHECK constraints

Add tests one cluster at a time, commit per cluster. Each test uses the `db_session` fixture (rolls back, no cleanup needed).

**Files:**
- Modify: `backend/tests/integration/test_migration_0001.py`

- [ ] **Step 10.1: Write CHECK-constraint tests**

Append to `backend/tests/integration/test_migration_0001.py`:

```python
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


async def _insert_source(
    session: AsyncSession, *, source_type: str = "channel", priority: int = 5
) -> None:
    await session.execute(
        text(
            "INSERT INTO telegram_sources (chat_id, title, source_type, priority) "
            "VALUES (:chat_id, :title, :st, :p)"
        ),
        {"chat_id": 1, "title": "t", "st": source_type, "p": priority},
    )


@pytest.mark.parametrize("source_type", ["channel", "group", "supergroup"])
async def test_source_type_accepts_valid_values(
    db_session: AsyncSession, source_type: str
) -> None:
    await _insert_source(db_session, source_type=source_type)


async def test_source_type_rejects_invalid_value(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        await _insert_source(db_session, source_type="bogus")
        await db_session.flush()


@pytest.mark.parametrize("priority", [1, 5, 10])
async def test_priority_accepts_in_range(db_session: AsyncSession, priority: int) -> None:
    await _insert_source(db_session, priority=priority)


@pytest.mark.parametrize("priority", [0, 11, -1, 100])
async def test_priority_rejects_out_of_range(
    db_session: AsyncSession, priority: int
) -> None:
    with pytest.raises(IntegrityError):
        await _insert_source(db_session, priority=priority)
        await db_session.flush()


@pytest.mark.parametrize(
    "status",
    ["pending", "filtered_out", "analyzing", "lead", "not_lead", "error"],
)
async def test_processing_status_accepts_valid(
    db_session: AsyncSession, status: str
) -> None:
    await _insert_source(db_session)
    await db_session.flush()
    await db_session.execute(
        text(
            "INSERT INTO raw_messages "
            "(source_id, telegram_message_id, sent_at, processing_status) "
            "SELECT id, 1, now(), :st FROM telegram_sources"
        ),
        {"st": status},
    )


async def test_processing_status_rejects_invalid(db_session: AsyncSession) -> None:
    await _insert_source(db_session)
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO raw_messages "
                "(source_id, telegram_message_id, sent_at, processing_status) "
                "SELECT id, 1, now(), 'nope' FROM telegram_sources"
            )
        )
        await db_session.flush()


@pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
async def test_confidence_accepts_unit_interval(
    db_session: AsyncSession, confidence: float
) -> None:
    await _insert_source(db_session)
    await db_session.flush()
    await db_session.execute(
        text(
            "INSERT INTO raw_messages (source_id, telegram_message_id, sent_at) "
            "SELECT id, 1, now() FROM telegram_sources RETURNING id"
        )
    )
    await db_session.execute(
        text(
            "INSERT INTO lead_analysis (raw_message_id, is_lead, confidence) "
            "SELECT id, true, :c FROM raw_messages"
        ),
        {"c": confidence},
    )


@pytest.mark.parametrize("confidence", [-0.01, 1.01, 2.0])
async def test_confidence_rejects_outside_unit_interval(
    db_session: AsyncSession, confidence: float
) -> None:
    await _insert_source(db_session)
    await db_session.flush()
    await db_session.execute(
        text(
            "INSERT INTO raw_messages (source_id, telegram_message_id, sent_at) "
            "SELECT id, 1, now() FROM telegram_sources"
        )
    )
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO lead_analysis (raw_message_id, is_lead, confidence) "
                "SELECT id, true, :c FROM raw_messages"
            ),
            {"c": confidence},
        )
        await db_session.flush()
```

- [ ] **Step 10.2: Run**

Run: `(cd backend && pytest tests/integration/test_migration_0001.py -v -k "source_type or priority or processing_status or confidence")`
Expected: all PASS.

- [ ] **Step 10.3: Commit**

```bash
git add backend/tests/integration/test_migration_0001.py
git commit -m "test(db): CHECK constraints — source_type, priority, processing_status, confidence"
```

---

## Task 11: Integration tests — FK RESTRICT + UNIQUE

**Files:**
- Modify: `backend/tests/integration/test_migration_0001.py`

- [ ] **Step 11.1: Append FK + UNIQUE tests**

Append to `backend/tests/integration/test_migration_0001.py`:

```python
async def test_fk_restrict_prevents_source_delete_with_messages(
    db_session: AsyncSession,
) -> None:
    await _insert_source(db_session)
    await db_session.flush()
    await db_session.execute(
        text(
            "INSERT INTO raw_messages (source_id, telegram_message_id, sent_at) "
            "SELECT id, 1, now() FROM telegram_sources"
        )
    )
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
    await db_session.execute(
        text(
            "INSERT INTO raw_messages (source_id, telegram_message_id, sent_at) "
            "SELECT id, 777, now() FROM telegram_sources"
        )
    )
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO raw_messages (source_id, telegram_message_id, sent_at) "
                "SELECT id, 777, now() FROM telegram_sources"
            )
        )
        await db_session.flush()


async def test_unique_sender_profiles_telegram_user_id(db_session: AsyncSession) -> None:
    await db_session.execute(
        text(
            "INSERT INTO sender_profiles (telegram_user_id) VALUES (123)"
        )
    )
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO sender_profiles (telegram_user_id) VALUES (123)"
            )
        )
        await db_session.flush()


async def test_unique_keyword_triggers_keyword_language(db_session: AsyncSession) -> None:
    await db_session.execute(
        text(
            "INSERT INTO keyword_triggers (keyword, trigger_type, language) "
            "VALUES ('нужен CTO', 'direct_request', 'ru')"
        )
    )
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO keyword_triggers (keyword, trigger_type, language) "
                "VALUES ('нужен CTO', 'pain_signal', 'ru')"
            )
        )
        await db_session.flush()
```

- [ ] **Step 11.2: Run**

Run: `(cd backend && pytest tests/integration/test_migration_0001.py -v -k "fk_restrict or unique_")`
Expected: all 5 PASS.

- [ ] **Step 11.3: Commit**

```bash
git add backend/tests/integration/test_migration_0001.py
git commit -m "test(db): FK RESTRICT + UNIQUE constraints"
```

---

## Task 12: Integration tests — JSONB roundtrip + TIMESTAMPTZ

**Files:**
- Modify: `backend/tests/integration/test_migration_0001.py`

- [ ] **Step 12.1: Append JSONB and tz tests**

Append:

```python
from datetime import datetime, timezone, timedelta


async def test_red_flags_jsonb_roundtrip(db_session: AsyncSession) -> None:
    await _insert_source(db_session)
    await db_session.flush()
    await db_session.execute(
        text(
            "INSERT INTO raw_messages (source_id, telegram_message_id, sent_at) "
            "SELECT id, 1, now() FROM telegram_sources"
        )
    )
    await db_session.flush()
    await db_session.execute(
        text(
            "INSERT INTO lead_analysis (raw_message_id, is_lead, red_flags) "
            "SELECT id, true, :rf::jsonb FROM raw_messages"
        ),
        {"rf": '["spam", "recruiter"]'},
    )
    result = await db_session.execute(text("SELECT red_flags FROM lead_analysis"))
    row = result.one()
    assert row[0] == ["spam", "recruiter"]


async def test_red_flags_default_empty_list(db_session: AsyncSession) -> None:
    await _insert_source(db_session)
    await db_session.flush()
    await db_session.execute(
        text(
            "INSERT INTO raw_messages (source_id, telegram_message_id, sent_at) "
            "SELECT id, 1, now() FROM telegram_sources"
        )
    )
    await db_session.flush()
    await db_session.execute(
        text(
            "INSERT INTO lead_analysis (raw_message_id, is_lead) "
            "SELECT id, true FROM raw_messages"
        )
    )
    row = (await db_session.execute(text("SELECT red_flags FROM lead_analysis"))).one()
    assert row[0] == []


async def test_timestamptz_round_trip_preserves_utc(db_session: AsyncSession) -> None:
    """Inserting a tz-aware datetime in Yekaterinburg TZ should read back as UTC."""

    yekb = timezone(timedelta(hours=5))
    local = datetime(2026, 4, 24, 15, 30, 0, tzinfo=yekb)

    await _insert_source(db_session)
    await db_session.flush()
    await db_session.execute(
        text(
            "INSERT INTO raw_messages (source_id, telegram_message_id, sent_at) "
            "SELECT id, 1, :ts FROM telegram_sources"
        ),
        {"ts": local},
    )
    await db_session.flush()
    row = (await db_session.execute(text("SELECT sent_at FROM raw_messages"))).one()
    stored: datetime = row[0]
    assert stored.tzinfo is not None
    # Driver returns UTC; semantic instant must match.
    assert stored == local
    assert stored.utcoffset() == timedelta(0)
```

- [ ] **Step 12.2: Run**

Run: `(cd backend && pytest tests/integration/test_migration_0001.py -v -k "red_flags or timestamptz")`
Expected: all 3 PASS.

- [ ] **Step 12.3: Commit**

```bash
git add backend/tests/integration/test_migration_0001.py
git commit -m "test(db): JSONB roundtrip + TIMESTAMPTZ preserves instant"
```

---

## Task 13: Integration tests — downgrade round-trip + partial-index sanity

**Files:**
- Create: `backend/tests/integration/test_migration_roundtrip.py`

This test can't share the session-scoped `migrated_db_url` fixture (because downgrading mid-session would break every other test). We use the raw `postgres_container` + a private `alembic.Config` to exercise the round-trip on a fresh state.

- [ ] **Step 13.1: Write the round-trip test**

Create `backend/tests/integration/test_migration_roundtrip.py`:

```python
"""Standalone round-trip: upgrade → check → downgrade → check empty."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from testcontainers.postgres import PostgresContainer

pytestmark = pytest.mark.integration

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "migrations" / "alembic.ini"


def test_migration_upgrade_then_downgrade_leaves_no_domain_tables() -> None:
    with PostgresContainer("postgres:15-alpine") as pg:
        sync_url = pg.get_connection_url()
        async_url = sync_url.replace("+psycopg2", "+asyncpg").replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        cfg = Config(str(_ALEMBIC_INI))
        cfg.set_main_option("sqlalchemy.url", async_url)

        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")

        # Post-downgrade: only alembic_version may remain (and typically that's gone too).
        engine = create_engine(sync_url, future=True)
        with engine.connect() as conn:
            tables = {
                r[0]
                for r in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                ).all()
            }
        engine.dispose()
        domain = {
            "telegram_sources",
            "raw_messages",
            "keyword_triggers",
            "lead_analysis",
            "sender_profiles",
        }
        assert not (domain & tables), f"leftover domain tables: {domain & tables}"


def test_partial_indexes_registered_with_predicate() -> None:
    """Verify the two partial indexes exist WITH the expected WHERE clause."""

    with PostgresContainer("postgres:15-alpine") as pg:
        sync_url = pg.get_connection_url()
        async_url = sync_url.replace("+psycopg2", "+asyncpg").replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        cfg = Config(str(_ALEMBIC_INI))
        cfg.set_main_option("sqlalchemy.url", async_url)
        command.upgrade(cfg, "head")

        engine = create_engine(sync_url, future=True)
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE indexname IN "
                    "('ix_keyword_triggers_active_type', "
                    " 'ix_lead_analysis_is_lead_analyzed_at')"
                )
            ).all()
        engine.dispose()

        by_name = {r[0]: r[1] for r in rows}
        assert "WHERE" in by_name["ix_keyword_triggers_active_type"].upper()
        assert "WHERE" in by_name["ix_lead_analysis_is_lead_analyzed_at"].upper()
```

- [ ] **Step 13.2: Run**

Run: `(cd backend && pytest tests/integration/test_migration_roundtrip.py -v)`
Expected: 2 PASS. Slower (~20s) because it spins up a fresh container.

- [ ] **Step 13.3: Commit**

```bash
git add backend/tests/integration/test_migration_roundtrip.py
git commit -m "test(db): migration round-trip + partial-index WHERE clause"
```

---

## Task 14: Full test sweep + coverage check

- [ ] **Step 14.1: Run the whole backend test suite**

Run: `(cd backend && pytest -v)`
Expected: all tests PASS. Count new tests vs baseline (should be +1 metadata test file, +14 integration tests across 2 files).

- [ ] **Step 14.2: Full lint**

Run: `(cd backend && ruff check src tests migrations && black --check src tests migrations && mypy src)`
Expected: no findings.

- [ ] **Step 14.3: Evidence gate — capture the pass count**

Take the last line of pytest output that looks like `==== X passed in Y.Ys ====`. Save it for the verification-before-completion gate in Task 16. Do NOT claim green without this observed output.

---

## Task 15: ADR-0008 — DB conventions

**Files:**
- Create: `docs/adr/0008-db-conventions.md`

- [ ] **Step 15.1: Write the ADR**

Check existing ADR filename style first:

Run: `ls docs/adr/`
Use whichever numbering/naming scheme is already in use. If existing ADRs are `0001-*.md` four-digit-padded, use `0008-db-conventions.md`. Otherwise match the existing style exactly.

Create the file with:

```markdown
# ADR-0008: Database conventions (initial schema)

## Status

Accepted — 2026-04-24

## Context

The first migration (`0001_initial`) lands 5 tables from ТЗ: `telegram_sources`,
`raw_messages`, `keyword_triggers`, `lead_analysis`, `sender_profiles`. Several
low-level choices (timestamps, constrained strings, FK behavior, UUID generation)
aren't explicit in ТЗ and deserve a written answer so Sprint 2 and later don't
re-litigate them.

## Decisions

1. **Timestamps are always `TIMESTAMPTZ`** (`DateTime(timezone=True)` in SQLAlchemy).
   Stored as UTC by Postgres, returned as UTC-aware datetimes. Telegram API emits
   UTC; naive timestamps would silently drift if the DB host TZ ever changes.
2. **UUID primary keys via `gen_random_uuid()`** (built into Postgres 13+).
   Server-side generation so raw SQL inserts don't need Python-side UUIDs.
3. **Constrained strings use `VARCHAR(N)` + named CHECK constraints**, not
   `CREATE TYPE ... AS ENUM`. Rationale: `ALTER TYPE ADD VALUE` can't run inside a
   transaction and values can't be removed; the project's constrained domains
   (`vertical`, `lead_type`, `enrichment_status`) will grow. `ALTER TABLE
   DROP/ADD CONSTRAINT` is fully transactional and symmetric.
4. **FK `ON DELETE RESTRICT` everywhere.** The raw-message log is training data
   — we won't CASCADE-delete it because a source was turned off. To remove a
   source, set `is_active=false`.
5. **Alembic naming convention** is set on `Base.metadata` (see
   `shared.db.session.NAMING_CONVENTION`). Constraint/index names are then
   deterministic across autogenerate runs.
6. **Deviations from ТЗ** recorded explicitly in the spec
   (`docs/superpowers/specs/2026-04-24-db-foundation-design.md#deliberate-deviations-from-тз`):
   `priority BETWEEN 1 AND 10`, `confidence IN [0, 1]`, `UNIQUE(keyword, language)`
   on triggers, and 5 values (not just `'pending'`) for `enrichment_status`.

## Consequences

- Changing a constraint/index name is now a migration, not a silent rename.
- Any new constrained-string column must ship with a CHECK in the same migration.
- Future migrations must consider whether `RESTRICT` still fits — if we ever want
  cascading deletes for a specific relationship (say, an archive table), it goes
  in explicitly with a rationale.

## Alternatives considered

- **Postgres ENUM types** — rejected for `ALTER TYPE` limitations (see Decision 3).
- **Soft-delete (`deleted_at`) on sources instead of `is_active`** — deferred;
  `is_active` is cheaper to query and matches ТЗ wording. Can add `deleted_at`
  later without breaking code.
- **Server-side timestamps via `CURRENT_TIMESTAMP`** — functionally equivalent
  to `func.now()` in SQLAlchemy; the latter is idiomatic and matches autogenerate
  output so we get no diff noise.

## References

- Spec: `docs/superpowers/specs/2026-04-24-db-foundation-design.md`
- Migration: `backend/migrations/versions/0001_initial.py`
- ТЗ: `TZ_Telegram_Lead_Aggregator.md` (FEATURE-02, 03, 04, 05, 07)
- Business rules: `BUSINESS_RULES.md` (BR-014)
```

- [ ] **Step 15.2: Commit**

```bash
git add docs/adr/0008-db-conventions.md
git commit -m "docs(adr): 0008 — DB conventions for initial schema"
```

---

## Task 16: CHANGELOG + CLAUDE.md update

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `CLAUDE.md`

- [ ] **Step 16.1: Update CHANGELOG `[Unreleased]` block**

Run: `head -30 CHANGELOG.md` to see current shape.
Add under the `[Unreleased]` / `### Added` section:

```
- Initial DB schema: 5 ORM models (`telegram_sources`, `raw_messages`, `keyword_triggers`, `lead_analysis`, `sender_profiles`), migration `0001_initial`, integration tests against Postgres 15.
- ADR-0008 documenting DB conventions (TIMESTAMPTZ, CHECK vs ENUM, FK RESTRICT, UUID `gen_random_uuid`).
```

- [ ] **Step 16.2: Update CLAUDE.md — move items from "Не сделано" to "Сделано"**

In `CLAUDE.md`, in the "Current state" section:

**Add** to the **Сделано** block:
```
- [x] SQLAlchemy-модели (5 таблиц) написаны, миграция `0001_initial` + 14+ integration тестов
- [x] ADR-0008 — DB conventions (TIMESTAMPTZ, CHECK, FK RESTRICT)
```

**Remove** from the **Не сделано** block:
```
- [ ] SQLAlchemy-модели написаны (`backend/src/shared/db/models.py` — сейчас stub)
- [ ] Первая миграция `0001_initial.py` для FEATURE-01..03 (telegram_sources, raw_messages, keyword_triggers)
```

**Add** to the **Не сделано** block (the next natural task):
```
- [ ] Seed-скрипт: 30+ источников + начальный словарь keyword-триггеров (`make seed`)
```

- [ ] **Step 16.3: Commit**

```bash
git add CHANGELOG.md CLAUDE.md
git commit -m "docs: update CHANGELOG + CLAUDE.md — DB foundation shipped"
```

---

## Task 17: Code review + verification gate

- [ ] **Step 17.1: Invoke code review skill**

Invoke `superpowers:requesting-code-review` on the whole diff of `feature/db-foundation` vs `origin/develop`.

Run: `git log origin/develop..HEAD --oneline` to confirm the commit list:

Expected commits:
```
docs(spec): DB foundation — 5 tables, …
feat(db): add naming convention to Base.metadata
feat(db): scaffold tables/ package, …
feat(db): TelegramSource model
feat(db): RawMessage model with FK RESTRICT …
feat(db): KeywordTrigger model with partial active index
feat(db): LeadAnalysis model with 7 CHECKs …
feat(db): SenderProfile model — completes domain schema
test(db): integration conftest — async URL + migrated-db fixture
feat(db): migration 0001_initial — 5 tables, CHECKs, partial indexes
test(db): CHECK constraints — source_type, priority, …
test(db): FK RESTRICT + UNIQUE constraints
test(db): JSONB roundtrip + TIMESTAMPTZ preserves instant
test(db): migration round-trip + partial-index WHERE clause
docs(adr): 0008 — DB conventions for initial schema
docs: update CHANGELOG + CLAUDE.md — DB foundation shipped
```

Run `git diff origin/develop..HEAD --stat` and skim. If the code reviewer raises blocking issues, invoke `superpowers:receiving-code-review` and address them in one or more additional commits.

- [ ] **Step 17.2: Invoke verification-before-completion**

Invoke `superpowers:verification-before-completion`.

Re-run the full test sweep + lint:

Run:
```bash
(cd backend && pytest -v)
(cd backend && ruff check src tests migrations)
(cd backend && black --check src tests migrations)
(cd backend && mypy src)
```
Expected: all PASS, no lint findings. Capture the pytest pass-count line.

- [ ] **Step 17.3: Only if all green — invoke finishing-a-development-branch**

Invoke `superpowers:finishing-a-development-branch`. Present options to the user:
- Push `feature/db-foundation` to `origin` and open a PR → `develop`
- Or, if user wants to inspect locally first — hold and wait

Do NOT push without explicit user approval (CLAUDE.md rule).

---

## Self-Review

**Spec coverage** (cross-check each spec section to a task):

| Spec section | Tasks covering it |
|---|---|
| `telegram_sources` | Task 3 + migration 9 + integration 10/11 |
| `raw_messages` | Task 4 + 9 + 10/11/12 |
| `keyword_triggers` | Task 5 + 9 + 11 |
| `lead_analysis` | Task 6 + 9 + 10/12 |
| `sender_profiles` | Task 7 + 9 + 11 |
| Naming convention | Task 1 |
| TIMESTAMPTZ | Task 12 |
| CHECK constraints | Task 10 |
| FK RESTRICT | Task 11 |
| JSONB | Task 12 |
| Partial indexes | Task 9 + 13 |
| UNIQUE | Task 11 |
| Migration round-trip | Task 13 |
| ADR-0008 | Task 15 |
| CHANGELOG + CLAUDE.md | Task 16 |
| Code review + verification | Task 17 |

**Placeholder scan:** no TBDs, all code inlined, all commands exact.

**Type consistency:** model class names used in plan — `TelegramSource`, `RawMessage`, `KeywordTrigger`, `LeadAnalysis`, `SenderProfile` — match everywhere. Constraint names follow `ck_<table>_<constraint>` everywhere. Index names match between model and migration (double-checked).

**Scope:** one feature (DB foundation), one migration, one PR. Out-of-scope items explicitly listed.
