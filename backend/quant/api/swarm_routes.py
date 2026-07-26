"""Swarm multi-agent HTTP routes."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials

from quant.api.helpers import _validate_path_param
from quant.api.security import _security, require_auth, _shell_tools_enabled_for_request

logger = logging.getLogger(__name__)

_swarm_runtime = None


def _get_swarm_runtime():
    """Lazy-init swarm runtime."""
    global _swarm_runtime
    if _swarm_runtime is None:
        try:
            from quant.swarm.runtime import SwarmRuntime
            _swarm_runtime = SwarmRuntime()
        except (ImportError, Exception) as exc:
            logger.debug("Swarm runtime unavailable: %s", exc)
            raise HTTPException(status_code=501, detail="Swarm runtime not available")
    return _swarm_runtime


def register_swarm_routes(router: APIRouter) -> None:
    """Mount swarm routes onto *router*."""

    @router.get("/swarm/runs")
    async def list_swarm_runs(
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        await require_auth(request, cred)
        rt = _get_swarm_runtime()
        return rt.list_runs()

    @router.post("/swarm/runs")
    async def start_swarm_run(
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        await require_auth(request, cred)
        body = await request.json()
        rt = _get_swarm_runtime()
        include_shell = _shell_tools_enabled_for_request(request)
        run = rt.start_run(
            preset_name=body["preset_name"],
            user_vars=body.get("user_vars", {}),
            include_shell_tools=include_shell,
        )
        return {
            "run_id": run.id,
            "status": run.status.value if hasattr(run.status, "value") else str(run.status),
            "preset_name": run.preset_name,
        }

    @router.get("/swarm/runs/{run_id}")
    async def get_swarm_run(
        run_id: str,
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        _validate_path_param(run_id, "run_id")
        await require_auth(request, cred)
        rt = _get_swarm_runtime()
        return rt.get_run(run_id)

    @router.get("/swarm/runs/{run_id}/events")
    async def swarm_run_events(
        run_id: str,
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        _validate_path_param(run_id, "run_id")
        await require_auth(request, cred)
        raise HTTPException(status_code=501, detail="SSE not implemented in minimal stub")

    @router.post("/swarm/runs/{run_id}/cancel")
    async def cancel_swarm_run(
        run_id: str,
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        _validate_path_param(run_id, "run_id")
        await require_auth(request, cred)
        rt = _get_swarm_runtime()
        rt.cancel_run(run_id)
        return {"status": "cancelled"}

    @router.post("/swarm/runs/{run_id}/retry")
    async def retry_swarm_run(
        run_id: str,
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        _validate_path_param(run_id, "run_id")
        await require_auth(request, cred)
        rt = _get_swarm_runtime()
        return rt.retry_run(run_id)
