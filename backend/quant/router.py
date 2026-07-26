"""Quant 模块路由适配层 — 供统一后端入口 include_router 使用。"""
from __future__ import annotations

import sys
import logging
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def create_quant_router() -> APIRouter:
    """Create quant module router, with graceful fallback on missing deps."""
    router = APIRouter()

    # Fix sys.path for quant internal imports
    _quant_dir = str(Path(__file__).resolve().parent)
    if _quant_dir not in sys.path:
        sys.path.insert(0, _quant_dir)

    _missing_deps: list[str] = []

    # Try to register each route group, catch import failures
    try:
        from src.api.sessions_routes import register_sessions_routes
        register_sessions_routes(router)
    except (ImportError, ModuleNotFoundError) as e:
        _missing_deps.append(f"sessions: {e}")

    try:
        from src.api.runs_routes import register_runs_routes
        register_runs_routes(router)
    except (ImportError, ModuleNotFoundError) as e:
        _missing_deps.append(f"runs: {e}")

    try:
        from src.api.swarm_routes import register_swarm_routes
        register_swarm_routes(router)
    except (ImportError, ModuleNotFoundError) as e:
        _missing_deps.append(f"swarm: {e}")

    try:
        from src.api.alpha_routes import register_alpha_routes
        register_alpha_routes(router)
    except (ImportError, ModuleNotFoundError) as e:
        _missing_deps.append(f"alpha: {e}")

    try:
        from src.api.settings_routes import register_settings_routes
        register_settings_routes(router)
    except (ImportError, ModuleNotFoundError) as e:
        _missing_deps.append(f"settings: {e}")

    try:
        from src.api.auth_routes import register_auth_routes
        register_auth_routes(router)
    except (ImportError, ModuleNotFoundError) as e:
        _missing_deps.append(f"auth: {e}")

    # Correlation (from backtest module)
    try:
        from backtest.correlation import compute_correlation_matrix  # noqa: F401
        from src.api.system_routes import register_system_routes
        register_system_routes(router)
    except (ImportError, ModuleNotFoundError, AttributeError) as e:
        _missing_deps.append(f"correlation: {e}")

    # EXCLUDED: live-trading routes, channels routes (per design ADR-0003)

    # Session-level guards (Requirements 5.6, 5.7)
    # Register specific 404/409 routes when real sessions module is unavailable.
    _sessions_missing = any("sessions" in dep for dep in _missing_deps)
    if _sessions_missing:
        from quant.session_guards import validate_session_exists, validate_no_active_attempt

        @router.get("/sessions/{session_id}")
        async def _session_404_guard(session_id: str) -> JSONResponse:
            """Guard: return 404 for non-existent session."""
            validate_session_exists(session_id)
            return JSONResponse({"detail": "Session service unavailable"}, status_code=503)

        @router.post("/sessions/{session_id}/messages")
        async def _session_message_guard(session_id: str) -> JSONResponse:
            """Guard: 404 for non-existent session, 409 for concurrent attempt."""
            validate_session_exists(session_id)
            validate_no_active_attempt(session_id)
            return JSONResponse({"detail": "Session service unavailable"}, status_code=503)

    # If deps are missing, register a catch-all fallback
    if _missing_deps:
        logger.warning("Quant router: some deps unavailable: %s", _missing_deps)

        @router.api_route(
            "/{path:path}",
            methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        )
        async def _quant_fallback(request: Request, path: str) -> JSONResponse:
            return JSONResponse(
                {"detail": "Quant module partially unavailable", "missing": _missing_deps},
                status_code=503,
            )

    return router
