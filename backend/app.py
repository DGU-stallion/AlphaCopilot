"""AlphaCopilot — 统一后端入口

将 research（投研数据）和 quant（量化 agent）两个模块挂载到同一 FastAPI 实例。

启动：
    cd backend && python -m uvicorn app:app --host 127.0.0.1 --port 8900
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create the unified AlphaCopilot FastAPI application."""
    app = FastAPI(title="AlphaCopilot API", version="0.1.0")

    # 1. CORS — 本地全开
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Auth middleware: VR_API_KEY env var, loopback bypass
    _api_key = os.environ.get("VR_API_KEY", "").strip()

    @app.middleware("http")
    async def _auth_middleware(request: Request, call_next):
        if (
            _api_key
            and request.method != "OPTIONS"
            and request.url.path.startswith("/api/")
            and request.url.path != "/api/health"
        ):
            # Loopback bypass: allow requests from localhost without auth
            client_host = request.client.host if request.client else ""
            if client_host in ("127.0.0.1", "::1"):
                pass  # allow without auth
            elif request.headers.get("authorization", "") != f"Bearer {_api_key}":
                return JSONResponse(
                    {"detail": "未授权：缺少或错误的 API Key（VR_API_KEY）"},
                    status_code=401,
                )
        return await call_next(request)

    # 3. Health endpoint
    @app.get("/api/health")
    def health():
        return {"ok": True, "service": "alphacopilot"}

    # 4. Research router
    from research.router import create_research_router
    app.include_router(create_research_router(), prefix="/api/research")

    # 5. Quant router — fail-fast, no fallback
    from quant.router import create_quant_router
    app.include_router(create_quant_router(), prefix="/api/quant")

    # 6. Lifecycle hooks
    @app.on_event("startup")
    async def _startup():
        # Start research portfolio scheduler
        try:
            import research.portfolio as pf
            pf.start_scheduler(1800)
        except Exception as exc:
            logger.warning("Portfolio scheduler failed to start: %s", exc)

        # Quant startup hooks
        try:
            from quant.api.scheduled_routes import _start_scheduled_research_executor
            _start_scheduled_research_executor()
        except (ImportError, ModuleNotFoundError) as exc:
            logger.warning("Quant startup hooks skipped (deps missing): %s", exc)

    @app.on_event("shutdown")
    async def _shutdown():
        try:
            from quant.api.scheduled_routes import _stop_scheduled_research_executor
            from quant.api.channels_routes import _stop_channel_runtime
            await _stop_channel_runtime()
            await _stop_scheduled_research_executor()
        except (ImportError, ModuleNotFoundError) as exc:
            logger.warning("Quant shutdown hooks skipped (deps missing): %s", exc)

    return app


app = create_app()
