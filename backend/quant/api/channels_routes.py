"""IM channels HTTP routes."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from quant.api.security import _security, require_auth
from quant.api.state import _get_channel_runtime

logger = logging.getLogger(__name__)


# ============================================================================
# Models (re-exported by api_server)
# ============================================================================


class ChannelPairingCommandRequest(BaseModel):
    """Request to pair a channel."""
    platform: str = Field(..., description="Platform name")
    session_id: str = Field(..., description="Session to pair")


# ============================================================================
# Lifecycle hooks (called from app.py)
# ============================================================================


async def _start_channel_runtime() -> None:
    """Start channel runtime adapters."""
    try:
        rt = _get_channel_runtime()
        if rt and hasattr(rt, "start"):
            await rt.start()
    except Exception as exc:
        logger.warning("Channel runtime start failed: %s", exc)


async def _stop_channel_runtime() -> None:
    """Stop channel runtime adapters."""
    try:
        rt = _get_channel_runtime()
        if rt and hasattr(rt, "stop"):
            await rt.stop()
    except Exception:
        pass


# ============================================================================
# Registration
# ============================================================================


def register_channels_routes(router: APIRouter) -> None:
    """Mount channel routes onto *router*."""

    @router.get("/channels")
    async def list_channels(
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        await require_auth(request, cred)
        try:
            rt = _get_channel_runtime()
            return rt.list_channels() if hasattr(rt, "list_channels") else []
        except HTTPException:
            return []

    @router.post("/channels/pair")
    async def pair_channel(
        body: ChannelPairingCommandRequest,
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        await require_auth(request, cred)
        rt = _get_channel_runtime()
        return rt.pair(platform=body.platform, session_id=body.session_id)
