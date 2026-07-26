"""Quant 模块路由适配层 — 供统一后端入口 include_router 使用。"""
from __future__ import annotations

import os
import logging
from fastapi import APIRouter

logger = logging.getLogger(__name__)

OPTIONAL_ROUTE_MODULES = {
    "swarm_routes": "QUANT_ENABLE_SWARM",
    "alpha_routes": "QUANT_ENABLE_ALPHA_ZOO",
    "scheduled_routes": "QUANT_ENABLE_SCHEDULER",
    "channels_routes": "QUANT_ENABLE_CHANNELS",
    "live_routes": "QUANT_ENABLE_LIVE_TRADING",
}


def create_quant_router() -> APIRouter:
    """Create quant router with fail-fast for core deps, feature-flagged optional deps."""
    router = APIRouter()

    # Core deps — fail loudly (no try/except)
    from quant.api.sessions_routes import register_sessions_routes
    from quant.api.runs_routes import register_runs_routes
    register_sessions_routes(router)
    register_runs_routes(router)

    # Always-on non-core routes
    from quant.api.settings_routes import register_settings_routes
    from quant.api.auth_routes import register_auth_routes
    from quant.api.system_routes import register_system_routes
    register_settings_routes(router)
    register_auth_routes(router)
    register_system_routes(router)

    # Optional deps — feature-flag gated
    for module_name, flag_var in OPTIONAL_ROUTE_MODULES.items():
        if os.environ.get(flag_var, "1") == "0":
            logger.info("Quant route group %s disabled by %s=0", module_name, flag_var)
            continue
        try:
            mod = __import__(f"quant.api.{module_name}", fromlist=["register"])
            register_fn = getattr(mod, f"register_{module_name}")
            register_fn(router)
        except (ImportError, ModuleNotFoundError) as e:
            logger.warning("Optional quant route group %s unavailable: %s", module_name, e)

    # NO catch-all fallback
    return router
