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
