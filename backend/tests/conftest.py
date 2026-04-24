"""Shared pytest fixtures.

Integration tests use ``testcontainers`` to spin up ephemeral Postgres and
Redis containers. Unit tests should avoid these fixtures so the fast suite
stays truly fast.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import TYPE_CHECKING

# Populate every required-by-Settings env var BEFORE any ``shared.config`` import
# happens downstream. Module-level ``create_app()`` / ``celery_app.app = ...``
# patterns otherwise fail in CI with a ValidationError.
# Real production values live in .env (local) or GitHub Secrets (CI deploy jobs).
_TEST_ENV_DEFAULTS: dict[str, str] = {
    "TELEGRAM_API_ID": "1",
    "TELEGRAM_API_HASH": "test-api-hash",
    "TELEGRAM_PHONE": "+10000000000",
    "TELETHON_SESSION_KEY": "test-fernet-key-32-bytes-long-xxx",
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "ANTHROPIC_API_KEY": "test-anthropic-key",
    "OPENAI_API_KEY": "test-openai-key",
    "PROMPT_VERSION": "v1",
    "NOTIFY_BOT_TOKEN": "test-bot-token",
    "NOTIFY_BOT_ADMIN_CHAT_ID": "0",
    "JWT_SECRET": "test-jwt-secret",
}
for _key, _val in _TEST_ENV_DEFAULTS.items():
    os.environ.setdefault(_key, _val)

import pytest  # noqa: E402  — env defaults above must run first

if TYPE_CHECKING:
    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    """Ephemeral Postgres 15 container for integration tests."""

    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:15-alpine") as container:
        yield container


@pytest.fixture(scope="session")
def redis_container() -> Iterator[RedisContainer]:
    """Ephemeral Redis 7 container for integration tests."""

    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as container:
        yield container


@pytest.fixture()
def anyio_backend() -> str:
    """Restrict async tests to asyncio (no trio)."""

    return "asyncio"
