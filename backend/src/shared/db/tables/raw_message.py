"""ORM model for the ``raw_messages`` table — every message we observe.

Schema matches TZ FEATURE-03. FK to ``telegram_sources`` uses
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
            "processing_status IN ('pending','filtered_out','analyzing','lead','not_lead','error')",
            name="processing_status_valid",
        ),
        Index("ix_raw_messages_processing_status", "processing_status"),
        Index("ix_raw_messages_sent_at_desc", "sent_at"),
        Index("ix_raw_messages_source_id_sent_at", "source_id", "sent_at"),
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
