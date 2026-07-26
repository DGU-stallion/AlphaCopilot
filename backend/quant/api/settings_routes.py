"""Settings HTTP routes."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from quant.api._compat import host_attr as _host_attr
from quant.api.helpers import ENV_PATH, _read_env_values, _write_env_values
from quant.api.security import _security, require_local_or_auth, require_settings_write_auth

logger = logging.getLogger(__name__)

# ============================================================================
# Re-exported symbols
# ============================================================================


def _baostock_installed() -> bool:
    """Return whether the baostock package is importable."""
    try:
        import baostock  # noqa: F401
        return True
    except ImportError:
        return False


def _baostock_supported() -> bool:
    """Return whether the current environment supports baostock."""
    return _baostock_installed()


def _load_llm_providers() -> list[dict]:
    """Load the list of configured LLM providers from env."""
    env_path = _host_attr("ENV_PATH", ENV_PATH)
    values = _read_env_values(env_path)
    provider = values.get("LANGCHAIN_PROVIDER", "openai")
    model = values.get("LANGCHAIN_MODEL_NAME", "")
    return [{"provider": provider, "model_name": model}]


# ============================================================================
# Registration
# ============================================================================


def register_settings_routes(router: APIRouter) -> None:
    """Mount settings routes onto *router*."""

    @router.get("/settings/llm")
    async def get_llm_settings(
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        await require_local_or_auth(request, cred)
        env_path = _host_attr("ENV_PATH", ENV_PATH)
        values = _read_env_values(env_path)
        return {
            "provider": values.get("LANGCHAIN_PROVIDER", "openai"),
            "model_name": values.get("LANGCHAIN_MODEL_NAME", "gpt-4o-mini"),
            "base_url": values.get("OPENAI_BASE_URL", ""),
            "temperature": float(values.get("AGENT_TEMPERATURE", "0")),
            "timeout_seconds": int(values.get("AGENT_TIMEOUT", "120")),
            "max_retries": int(values.get("AGENT_MAX_RETRIES", "2")),
        }

    @router.put("/settings/llm")
    async def update_llm_settings(
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        await require_settings_write_auth(request, cred)
        body = await request.json()
        env_path = _host_attr("ENV_PATH", ENV_PATH)
        updates = {}
        if "provider" in body:
            updates["LANGCHAIN_PROVIDER"] = body["provider"]
        if "model_name" in body:
            updates["LANGCHAIN_MODEL_NAME"] = body["model_name"]
        if "base_url" in body:
            updates["OPENAI_BASE_URL"] = body["base_url"]
        if "temperature" in body:
            updates["AGENT_TEMPERATURE"] = str(body["temperature"])
        if "timeout_seconds" in body:
            updates["AGENT_TIMEOUT"] = str(body["timeout_seconds"])
        if "max_retries" in body:
            updates["AGENT_MAX_RETRIES"] = str(body["max_retries"])
        if updates:
            _write_env_values(env_path, updates)
        return {"status": "ok"}

    @router.get("/settings/providers")
    async def get_providers(
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        await require_local_or_auth(request, cred)
        return _load_llm_providers()

    @router.get("/settings/data-sources")
    async def get_data_sources(
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        await require_local_or_auth(request, cred)
        return {"baostock_supported": _baostock_supported()}
