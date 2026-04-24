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
    # DESC index — emitted via raw SQL since Alembic's op.create_index helper
    # is clunky for per-column ordering across dialects.
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
            "budget_signals IS NULL OR budget_signals IN ('mentioned','implied','none')",
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
