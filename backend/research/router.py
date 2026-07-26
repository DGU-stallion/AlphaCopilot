"""Research 模块路由集合 —— 供统一后端入口 include_router 使用。

所有路径不带 /api/ 前缀（由调用方设置 prefix="/api/research"）。
不包含中间件（CORS、认证）和应用级副作用（如 scheduler），这些由 app.py 或统一入口管理。
"""

from __future__ import annotations

from fastapi import APIRouter

from research.caches import ResearchCaches
from research.routes.chat import register_chat_routes
from research.routes.portfolio import register_portfolio_routes
from research.routes.market_data import register_market_data_routes
from research.routes.reports_news import register_reports_news_routes


def create_research_router(*, caches: ResearchCaches | None = None) -> APIRouter:
    """Assemble the complete research router from sub-modules."""
    router = APIRouter()
    _caches = caches or ResearchCaches()

    # Health check — kept inline in the assembler
    @router.get("/health")
    def health():
        return {"ok": True, "service": "vibe-research-api", "version": "0.1.3"}

    # Delegate to sub-modules
    register_chat_routes(router, caches=_caches)
    register_portfolio_routes(router, caches=_caches)
    register_market_data_routes(router, caches=_caches)
    register_reports_news_routes(router, caches=_caches)

    return router
