"""telegram_sources.chat_id becomes nullable; UNIQUE → partial unique index.

Seeded sources arrive with only ``username`` (the @handle); the numeric
``chat_id`` is resolved by the Telethon listener at first connect and
back-filled then. Postgres has no partial UNIQUE *constraint*, only
partial unique *indexes*, so we drop the original ``UNIQUE`` constraint
and replace it with a partial unique index that ignores NULL rows.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_telegram_sources_chat_id",
        "telegram_sources",
        type_="unique",
    )
    op.alter_column(
        "telegram_sources",
        "chat_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )
    op.create_index(
        "uq_telegram_sources_chat_id",
        "telegram_sources",
        ["chat_id"],
        unique=True,
        postgresql_where=sa.text("chat_id IS NOT NULL"),
    )


def downgrade() -> None:
    # Downgrade is only safe when no NULL chat_id rows exist; raise early
    # rather than crash midway with a NOT NULL violation that aborts the
    # whole migration transaction.
    bind = op.get_bind()
    null_count = bind.execute(
        sa.text("SELECT count(*) FROM telegram_sources WHERE chat_id IS NULL")
    ).scalar_one()
    if null_count:
        raise RuntimeError(
            f"Cannot downgrade 0002 → 0001: {null_count} telegram_sources rows "
            "have NULL chat_id. Resolve them (assign chat_id or DELETE) first."
        )
    op.drop_index("uq_telegram_sources_chat_id", table_name="telegram_sources")
    op.alter_column(
        "telegram_sources",
        "chat_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_telegram_sources_chat_id",
        "telegram_sources",
        ["chat_id"],
    )
