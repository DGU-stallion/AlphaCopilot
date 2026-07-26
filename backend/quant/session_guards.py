"""Session-level HTTP guards for quant API routes.

Provides FastAPI dependencies for:
- 404: session not found
- 409: concurrent attempt in progress

Requirements validated: 5.6, 5.7
"""
from __future__ import annotations

from fastapi import HTTPException


def validate_session_exists(session_id: str) -> None:
    """Raise 404 if session does not exist.

    Called by session route handlers before processing.
    Attempts to load session from store; raises HTTPException(404) on miss.
    """
    try:
        from quant.session.store import SessionStore

        store = SessionStore()
        session = store.load(session_id)
        if session is None:
            raise HTTPException(404, f"Session '{session_id}' not found")
    except ImportError:
        # Store module not available — assume not found
        raise HTTPException(
            404, f"Session '{session_id}' not found (session store unavailable)"
        )


def validate_no_active_attempt(session_id: str) -> None:
    """Raise 409 if an attempt is already executing for this session.

    Prevents concurrent message sends to the same session.
    """
    try:
        from quant.session.service import SessionService

        svc = SessionService()
        if svc.has_active_attempt(session_id):
            raise HTTPException(
                409, f"Session '{session_id}' has an active attempt in progress"
            )
    except ImportError:
        # Service module not available — allow (no conflict detection possible)
        pass
