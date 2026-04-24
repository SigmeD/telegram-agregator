"""Admin endpoints for leads (FEATURE-09)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("")
async def list_leads() -> list[dict[str, Any]]:
    """Return paginated list of leads (stub).

    Raises:
        NotImplementedError: Stub implementation.
    """

    raise NotImplementedError("GET /leads is not implemented yet")


@router.get("/{lead_id}")
async def get_lead(lead_id: str) -> dict[str, Any]:
    """Return a single lead with full context (stub).

    Raises:
        NotImplementedError: Stub implementation.
    """

    _ = lead_id
    raise NotImplementedError("GET /leads/{id} is not implemented yet")
