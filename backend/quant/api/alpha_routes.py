"""Alpha Zoo HTTP routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)


def register_alpha_routes(router: APIRouter) -> None:
    """Mount alpha zoo routes onto *router*."""

    @router.get("/alpha/factors")
    async def list_factors():
        """List registered alpha factors."""
        try:
            from quant.factors import registry
            return [{"name": f.name, "family": f.family} for f in registry.all_factors()]
        except (ImportError, Exception):
            return []
