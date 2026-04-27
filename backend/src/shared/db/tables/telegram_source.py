"""ORM model for the ``telegram_sources`` table — monitored chats/channels.

Schema matches TZ FEATURE-02 literally, with explicit ``priority``
bounds (documented in ADR-0008). ``chat_id`` is nullable: seeded rows
arrive with only ``username``, and the listener back-fills ``chat_id``
on first connect (migration 0002).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    func,
    text,
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
        # Partial unique index: enforces UNIQUE on chat_id only for
        # back-filled (non-NULL) rows. Postgres doesn't support partial
        # UNIQUE *constraints*, only partial unique *indexes*.
        Index(
            "uq_telegram_sources_chat_id",
            "chat_id",
            unique=True,
            postgresql_where=text("chat_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_messages_processed: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    relevant_leads_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
