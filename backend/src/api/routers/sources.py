"""Admin endpoints for Telegram sources (FEATURE-02)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("")
async def list_sources() -> list[dict[str, Any]]:
    """Return all configured Telegram sources (stub).

    Raises:
        NotImplementedError: Stub implementation.
    """

    raise NotImplementedError("GET /sources is not implemented yet")


@router.post("")
async def create_source(payload: dict[str, Any]) -> dict[str, Any]:
    """Subscribe the user-session to a new chat / channel (stub).

    Raises:
        NotImplementedError: Stub implementation.
    """

    _ = payload
    raise NotImplementedError("POST /sources is not implemented yet")
