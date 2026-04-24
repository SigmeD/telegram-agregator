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
