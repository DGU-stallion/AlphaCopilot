"""Auth helper routes (SSE ticket minting)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request, Security
from fastapi.security import HTTPAuthorizationCredentials

from quant.api.security import _mint_sse_ticket, _security, require_auth


def register_auth_routes(router: APIRouter) -> None:
    """Mount auth helper routes onto *router*."""

    @router.post("/auth/sse-ticket")
    async def mint_sse_ticket(
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        """Mint a single-use SSE authentication ticket."""
        await require_auth(request, cred)
        ticket = _mint_sse_ticket()
        return {"ticket": ticket}
