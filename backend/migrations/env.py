"""Alembic environment (async, SQLAlchemy 2.x)."""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from shared.db.models import Base

# Alembic Config object provides access to values in alembic.ini.
config = context.config

# DATABASE_URL resolution order:
#   1. ``sqlalchemy.url`` already set on the Config (e.g. tests calling
#      ``cfg.set_main_option("sqlalchemy.url", ...)``)
#   2. ``DATABASE_URL`` environment variable (CLI / prod)
# We intentionally avoid importing ``shared.config.Settings`` here because
# Alembic only needs a DB URL, whereas the full Settings schema requires
# Telegram/LLM/notification secrets that aren't available in every
# migration context (e.g. integration tests, one-off schema dumps).
if not config.get_main_option("sqlalchemy.url"):
    env_url = os.environ.get("DATABASE_URL")
    if not env_url:
        raise RuntimeError(
            "DATABASE_URL must be provided via environment variable or "
            "alembic Config.set_main_option('sqlalchemy.url', ...) before "
            "running migrations."
        )
    config.set_main_option("sqlalchemy.url", env_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (emits SQL)."""

    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations against an async engine."""

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Async online migrations entry-point."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
