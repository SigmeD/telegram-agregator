"""Admin endpoints for keyword triggers (FEATURE-04)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/triggers", tags=["triggers"])


@router.get("")
async def list_triggers() -> list[dict[str, Any]]:
    """Return all keyword triggers (stub).

    Raises:
        NotImplementedError: Stub implementation.
    """

    raise NotImplementedError("GET /triggers is not implemented yet")


@router.post("")
async def create_trigger(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a new keyword trigger (stub).

    Raises:
        NotImplementedError: Stub implementation.
    """

    _ = payload
    raise NotImplementedError("POST /triggers is not implemented yet")
