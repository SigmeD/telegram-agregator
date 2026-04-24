"""Shared pytest fixtures.

Integration tests use ``testcontainers`` to spin up ephemeral Postgres and
Redis containers. Unit tests should avoid these fixtures so the fast suite
stays truly fast.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer


@pytest.fixture(scope="session")
def postgres_container() -> Iterator["PostgresContainer"]:
    """Ephemeral Postgres 15 container for integration tests."""

    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:15-alpine") as container:
        yield container


@pytest.fixture(scope="session")
def redis_container() -> Iterator["RedisContainer"]:
    """Ephemeral Redis 7 container for integration tests."""

    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as container:
        yield container


@pytest.fixture()
def anyio_backend() -> str:
    """Restrict async tests to asyncio (no trio)."""

    return "asyncio"
