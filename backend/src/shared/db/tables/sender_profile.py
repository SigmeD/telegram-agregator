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
