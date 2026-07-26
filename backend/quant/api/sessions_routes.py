"""Session management HTTP routes."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from quant.api._compat import host_attr as _host_attr
from quant.api.helpers import SESSIONS_DIR, _validate_path_param
from quant.api.security import _security, require_auth, require_event_stream_auth

logger = logging.getLogger(__name__)

# ============================================================================
# Shared state (test-monkeypatch compatible)
# ============================================================================

_goal_store = None


def _get_goal_store():
    """Lazy-init goal store."""
    global _goal_store
    if _goal_store is None:
        try:
            from quant.goal import GoalStore
            _goal_store = GoalStore()
        except ImportError:
            pass
    return _goal_store


# ============================================================================
# Frame helpers (re-exported by api_server for test compat)
# ============================================================================


def _live_action_frame_from_tool_result(tool_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract a live-action UI frame from a tool-call result."""
    if not isinstance(tool_result, dict):
        return None
    action_type = tool_result.get("action_type")
    if not action_type:
        return None
    return {
        "type": "live_action",
        "action_type": action_type,
        "payload": tool_result.get("payload"),
    }


def _mandate_proposal_frame_from_tool_result(tool_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract a mandate-proposal UI frame from a tool-call result."""
    if not isinstance(tool_result, dict):
        return None
    if "mandate" not in tool_result:
        return None
    return {
        "type": "mandate_proposal",
        "mandate": tool_result["mandate"],
    }


# ============================================================================
# Registration
# ============================================================================


def register_sessions_routes(router: APIRouter) -> None:
    """Mount session CRUD and messaging routes onto *router*."""

    @router.get("/sessions")
    async def list_sessions(
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        await require_auth(request, cred)
        from quant.api.state import _get_session_service
        svc = _get_session_service()
        if not svc:
            raise HTTPException(status_code=501, detail="Session runtime not enabled")
        return svc.list_sessions()

    @router.post("/sessions", status_code=201)
    async def create_session(
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        await require_auth(request, cred)
        from quant.api.state import _get_session_service
        svc = _get_session_service()
        if not svc:
            raise HTTPException(status_code=501, detail="Session runtime not enabled")
        body = await request.json() if await request.body() else {}
        return svc.create_session(title=body.get("title"))

    @router.get("/sessions/{session_id}")
    async def get_session(
        session_id: str,
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        _validate_path_param(session_id, "session_id")
        await require_auth(request, cred)
        from quant.api.state import _get_session_service
        svc = _get_session_service()
        if not svc:
            raise HTTPException(status_code=501, detail="Session runtime not enabled")
        try:
            result = svc.get_session(session_id)
        except (ValueError, KeyError, FileNotFoundError):
            raise HTTPException(status_code=404, detail="Session not found")
        if result is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return result

    @router.delete("/sessions/{session_id}")
    async def delete_session(
        session_id: str,
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        _validate_path_param(session_id, "session_id")
        await require_auth(request, cred)
        from quant.api.state import _get_session_service
        svc = _get_session_service()
        if not svc:
            raise HTTPException(status_code=501, detail="Session runtime not enabled")
        svc.delete_session(session_id)
        return {"status": "deleted"}

    @router.patch("/sessions/{session_id}")
    async def update_session(
        session_id: str,
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        _validate_path_param(session_id, "session_id")
        await require_auth(request, cred)
        body = await request.json()
        from quant.api.state import _get_session_service
        svc = _get_session_service()
        if not svc:
            raise HTTPException(status_code=501, detail="Session runtime not enabled")
        return svc.update_session(session_id, **body)

    @router.post("/sessions/{session_id}/messages")
    async def send_message(
        session_id: str,
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        _validate_path_param(session_id, "session_id")
        await require_auth(request, cred)
        body = await request.json()
        content = body.get("content", "")
        # Reject empty or whitespace-only messages
        if not content or not content.strip():
            raise HTTPException(status_code=400, detail="Message content cannot be empty")
        from quant.api.state import _get_session_service
        svc = _get_session_service()
        if not svc:
            raise HTTPException(status_code=501, detail="Session runtime not enabled")
        from quant.api.security import _shell_tools_enabled_for_request
        include_shell = _shell_tools_enabled_for_request(request)
        try:
            return await svc.send_message(
                session_id=session_id,
                content=content,
                include_shell_tools=include_shell,
            )
        except (ValueError, KeyError, FileNotFoundError):
            raise HTTPException(status_code=404, detail="Session not found")

    @router.get("/sessions/{session_id}/messages")
    async def get_messages(
        session_id: str,
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        _validate_path_param(session_id, "session_id")
        await require_auth(request, cred)
        from quant.api.state import _get_session_service
        svc = _get_session_service()
        if not svc:
            raise HTTPException(status_code=501, detail="Session runtime not enabled")
        return svc.get_messages(session_id)

    @router.post("/sessions/{session_id}/cancel")
    async def cancel_session(
        session_id: str,
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        _validate_path_param(session_id, "session_id")
        await require_auth(request, cred)
        from quant.api.state import _get_session_service
        svc = _get_session_service()
        if not svc:
            raise HTTPException(status_code=501, detail="Session runtime not enabled")
        svc.cancel_session(session_id)
        return {"status": "cancelled"}

    @router.get("/sessions/{session_id}/events")
    async def session_events(
        session_id: str,
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        _validate_path_param(session_id, "session_id")
        await require_event_stream_auth(request, cred=cred)
        from quant.api.state import _get_session_service
        svc = _get_session_service()
        if not svc:
            raise HTTPException(status_code=501, detail="Session runtime not enabled")
        raise HTTPException(status_code=501, detail="SSE not implemented in minimal stub")

    # --- Goal endpoints ---

    @router.post("/sessions/{session_id}/goal")
    async def set_goal(
        session_id: str,
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        _validate_path_param(session_id, "session_id")
        await require_auth(request, cred)
        body = await request.json()
        store = _get_goal_store()
        if not store:
            raise HTTPException(status_code=501, detail="Goal store not available")
        goal = store.replace_goal(
            session_id=session_id,
            objective=body["objective"],
            criteria=body.get("criteria", []),
        )
        snapshot = store.get_goal_snapshot(goal.goal_id)
        return {"snapshot": snapshot}

    @router.get("/sessions/{session_id}/goal")
    async def get_goal(
        session_id: str,
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        _validate_path_param(session_id, "session_id")
        await require_auth(request, cred)
        store = _get_goal_store()
        if not store:
            raise HTTPException(status_code=501, detail="Goal store not available")
        snapshot = store.get_current_snapshot(session_id)
        return {"snapshot": snapshot}

    @router.post("/sessions/{session_id}/goal/evidence")
    async def add_goal_evidence(
        session_id: str,
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        _validate_path_param(session_id, "session_id")
        await require_auth(request, cred)
        body = await request.json()
        store = _get_goal_store()
        if not store:
            raise HTTPException(status_code=501, detail="Goal store not available")
        from quant.goal import EvidenceInput
        store.append_evidence(
            session_id=session_id,
            goal_id=body["goal_id"],
            expected_goal_id=body.get("expected_goal_id"),
            evidence=EvidenceInput(text=body["text"]),
        )
        snapshot = store.get_goal_snapshot(body["goal_id"])
        return {"snapshot": snapshot}
