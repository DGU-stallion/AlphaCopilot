"""Scheduled research job HTTP routes."""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from quant.api.security import _security, require_auth

logger = logging.getLogger(__name__)

# ============================================================================
# Models
# ============================================================================


class CreateScheduledRunRequest(BaseModel):
    """Request to schedule a research run."""
    name: str = Field(..., description="Job name")
    cron: str = Field(..., description="Cron expression")
    query: str = Field(..., description="Research query")
    enabled: bool = Field(True)


class ScheduledRunResponse(BaseModel):
    """Scheduled run response."""
    job_id: str
    name: str
    cron: str
    query: str
    enabled: bool


# ============================================================================
# Executor lifecycle
# ============================================================================

_executor = None
_store = None


def _get_scheduled_research_store():
    """Lazy-init scheduled research store."""
    global _store
    if _store is None:
        try:
            from quant.core.scheduled_research import ScheduledResearchJobStore
            _store = ScheduledResearchJobStore()
        except (ImportError, Exception):
            pass
    return _store


def _get_scheduled_research_executor():
    """Lazy-init scheduled research executor."""
    global _executor
    if _executor is None:
        try:
            from quant.core.scheduled_research import ScheduledResearchExecutor
            _executor = ScheduledResearchExecutor()
        except (ImportError, Exception):
            pass
    return _executor


def _scheduled_research_scheduler_enabled() -> bool:
    """Return whether the scheduler is enabled."""
    try:
        from quant.config.accessor import get_env_config
        return get_env_config().agent_tuning.vibe_trading_enable_scheduler
    except (ImportError, AttributeError):
        return False


def _dispatch_scheduled_research_job(job_id: str) -> None:
    """Dispatch a scheduled research job for execution."""
    executor = _get_scheduled_research_executor()
    if executor:
        executor.dispatch(job_id)


def _start_scheduled_research_executor() -> None:
    """Start the scheduled research executor (called on app startup)."""
    if _scheduled_research_scheduler_enabled():
        executor = _get_scheduled_research_executor()
        if executor:
            executor.start()


async def _stop_scheduled_research_executor() -> None:
    """Stop the scheduled research executor (called on app shutdown)."""
    global _executor
    if _executor is not None:
        try:
            _executor.stop()
        except Exception:
            pass
        _executor = None


# ============================================================================
# Registration
# ============================================================================


def register_scheduled_routes(router: APIRouter) -> None:
    """Mount scheduled research routes onto *router*."""

    @router.get("/scheduled/jobs")
    async def list_jobs(
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        await require_auth(request, cred)
        store = _get_scheduled_research_store()
        if not store:
            return []
        return store.list_jobs()

    @router.post("/scheduled/jobs")
    async def create_job(
        body: CreateScheduledRunRequest,
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        await require_auth(request, cred)
        store = _get_scheduled_research_store()
        if not store:
            raise HTTPException(status_code=501, detail="Scheduler not available")
        job = store.create_job(
            name=body.name,
            cron=body.cron,
            query=body.query,
            enabled=body.enabled,
        )
        return job
