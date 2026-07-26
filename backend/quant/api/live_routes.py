"""Live trading HTTP routes."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from quant.api.security import _security, require_auth

logger = logging.getLogger(__name__)

# ============================================================================
# Models (re-exported by api_server for test compat)
# ============================================================================


class CommitMandateRequest(BaseModel):
    broker: str
    session_id: str


class LiveHaltRequest(BaseModel):
    broker: Optional[str] = None


class LiveAuthorizeRequest(BaseModel):
    broker: str


class LiveRunnerControlRequest(BaseModel):
    broker: str
    session_id: str


class BrokerAuthState(BaseModel):
    broker: str
    authenticated: bool = False


class MandateLimits(BaseModel):
    max_position_pct: float = 5.0
    max_daily_loss_pct: float = 2.0


class ActiveMandateState(BaseModel):
    broker: str = ""
    expired: bool = True


class RunnerLivenessState(BaseModel):
    broker: str = ""
    alive: bool = False


class LiveBrokerStatus(BaseModel):
    broker: str
    connected: bool = False
    authenticated: bool = False


class LiveStatusResponse(BaseModel):
    brokers: list = Field(default_factory=list)


class LiveRunnerUnavailable(BaseModel):
    detail: str = "Live runner unavailable"


# ============================================================================
# Shared state (re-exported by api_server for test compat)
# ============================================================================

_runner_tasks: Dict[str, asyncio.Task] = {}
_connector_verify_cache: Dict[str, Any] = {}


def _runner_factory(broker: str) -> Any:
    """Default runner factory — overridden by tests."""
    raise HTTPException(status_code=501, detail="Live runner factory not configured")


def _emit_live_event(event_type: str, payload: dict) -> None:
    """Emit a live-trading event (stub)."""
    logger.debug("live_event: %s %s", event_type, payload)


def _fetch_broker_ceilings(broker: str) -> dict:
    """Fetch position ceilings for a broker (stub)."""
    return {}


def _known_live_brokers() -> list[str]:
    """Return list of known live broker names."""
    return []


def _oauth_token_present(broker: str) -> bool:
    """Check whether an OAuth token is available for the broker."""
    return False


def _active_mandate_state(broker: str) -> ActiveMandateState:
    """Return active mandate state for a broker."""
    return ActiveMandateState(broker=broker, expired=True)


def _runner_liveness_state(broker: str) -> RunnerLivenessState:
    """Return runner liveness state."""
    return RunnerLivenessState(broker=broker, alive=broker in _runner_tasks)


def _live_broker_adapter(broker: str) -> Any:
    """Return the live broker adapter (stub)."""
    return None


def _build_live_runner(broker: str) -> Any:
    """Build a live runner instance."""
    return _runner_factory(broker)


async def _drive_runner(broker: str) -> None:
    """Drive the runner loop for a broker."""
    runner = _build_live_runner(broker)
    if hasattr(runner, "run_loop"):
        await runner.run_loop()


def _check_connector_status(broker: str) -> dict:
    """Check connector status for a broker."""
    return {"broker": broker, "connected": False}


# ============================================================================
# Registration
# ============================================================================


def register_live_routes(router: APIRouter) -> None:
    """Mount live trading routes onto *router*."""

    @router.get("/live/status")
    async def live_status(
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        await require_auth(request, cred)
        return LiveStatusResponse(brokers=_known_live_brokers())

    @router.post("/live/runner/start")
    async def start_runner(
        body: LiveRunnerControlRequest,
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        await require_auth(request, cred)
        broker = body.broker
        if broker in _runner_tasks and not _runner_tasks[broker].done():
            return {"status": "already_running", "broker": broker}

        task = asyncio.create_task(_drive_runner(broker))
        _runner_tasks[broker] = task
        return {"status": "started", "broker": broker}

    @router.post("/live/runner/stop")
    async def stop_runner(
        body: LiveRunnerControlRequest,
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        await require_auth(request, cred)
        broker = body.broker
        task = _runner_tasks.pop(broker, None)
        if task and not task.done():
            task.cancel()
        return {"status": "stopped", "broker": broker}
