"""Async SQLAlchemy engine and session factory.

This module intentionally stays thin: concrete ORM models live in
:mod:`shared.db.models`. Services obtain a session via
:func:`get_sessionmaker` and manage lifecycle themselves (FastAPI uses a
dependency, Celery uses a context manager, listener opens one per batch).
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from shared.config import get_settings

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


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Return a cached async engine bound to ``DATABASE_URL``."""

    settings = get_settings()
    return create_async_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        future=True,
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return a cached ``async_sessionmaker`` for the configured engine."""

    return async_sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
        class_=AsyncSession,
    )
