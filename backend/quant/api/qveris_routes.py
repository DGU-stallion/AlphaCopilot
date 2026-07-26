"""QVeris data marketplace routes."""

from __future__ import annotations

from fastapi import APIRouter

qveris_router = APIRouter(prefix="/qveris", tags=["qveris"])


@qveris_router.get("/datasets")
async def list_datasets():
    """List available QVeris datasets."""
    return []
