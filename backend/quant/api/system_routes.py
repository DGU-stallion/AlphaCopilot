"""System and utility HTTP routes."""

from __future__ import annotations

import os
import signal
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials

from quant.api.security import (
    _security,
    _reject_cross_site_browser_request,
    _require_shutdown_authorization,
    require_auth,
)


# ---------------------------------------------------------------------------
# Process termination
# ---------------------------------------------------------------------------


def _terminate_current_process() -> None:
    """Stop the current API process after the response has been sent."""
    time.sleep(0.25)
    os.kill(os.getpid(), signal.SIGTERM)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_system_routes(router: APIRouter) -> None:
    """Mount the system routes onto *router*."""

    @router.get("/health")
    async def health_check():
        """Liveness probe."""
        return {
            "status": "healthy",
            "service": "Vibe-Trading API",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @router.get("/correlation")
    async def get_correlation_matrix(
        codes: str = Query(..., description="Comma-separated asset codes"),
        days: int = Query(90, ge=7, le=365),
        method: str = Query("pearson"),
    ):
        """Compute cross-asset correlation matrix."""
        from quant.backtest.correlation import compute_correlation_matrix

        code_list = [c.strip() for c in codes.split(",") if c.strip()]
        if len(code_list) < 2:
            raise HTTPException(status_code=400, detail="At least 2 asset codes required")
        if len(code_list) > 20:
            raise HTTPException(status_code=400, detail="Maximum 20 assets per request")
        if method not in ("pearson", "spearman"):
            raise HTTPException(status_code=400, detail="method must be 'pearson' or 'spearman'")

        try:
            result = compute_correlation_matrix(codes=code_list, days=days, method=method)
            return result
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Correlation computation failed: {exc}")

    @router.post("/system/shutdown")
    async def shutdown_local_api(
        background_tasks: BackgroundTasks,
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        """Shut down the local API server."""
        _require_shutdown_authorization(request=request, cred=cred)
        client_host = request.client.host if request.client else ""
        if client_host not in {"127.0.0.1", "::1", "localhost"}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Local access only")

        import sys as _sys
        host = _sys.modules.get("api_server")
        terminate_fn = getattr(host, "_terminate_current_process", _terminate_current_process) if host else _terminate_current_process
        background_tasks.add_task(terminate_fn)
        return {
            "status": "shutting-down",
            "service": "Vibe-Trading API",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @router.get("/skills")
    async def list_skills():
        """List registered skills."""
        try:
            from quant.agent.skills import SkillsLoader
            loader = SkillsLoader()
            return [{"name": s.name, "description": s.description} for s in loader.skills]
        except (ImportError, Exception):
            return []

    @router.get("/api")
    async def api_info():
        """Service metadata."""
        return {
            "service": "Vibe-Trading API",
            "version": "0.1.0",
            "docs": "/docs",
            "health": "/health",
        }
