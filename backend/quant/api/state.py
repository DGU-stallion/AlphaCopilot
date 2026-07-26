"""Lazy-init service singletons shared by session, channel, and live routes."""

from __future__ import annotations

import logging

from quant.api._compat import host_attr as _host_attr, set_host_attr as _set_host_attr
from quant.api.helpers import RUNS_DIR, SESSIONS_DIR

logger = logging.getLogger(__name__)

# ============================================================================
# Global singletons
# ============================================================================

_session_service = None
_channel_runtime = None
_channel_bus = None
_channel_manager = None


# ============================================================================
# Lazy initializers
# ============================================================================


def _get_session_service():
    """Lazy-init session service when ENABLE_SESSION_RUNTIME=true."""
    global _session_service

    import sys as _sys
    _host = _sys.modules.get("api_server")
    if _host is not None and hasattr(_host, "_session_service"):
        host_val = getattr(_host, "_session_service")
        if host_val is not None:
            return host_val
    elif _session_service is not None:
        return _session_service

    try:
        from quant.config.accessor import get_env_config
        if not get_env_config().api.enable_session_runtime:
            return None
    except (ImportError, AttributeError):
        return None

    try:
        import asyncio

        from quant.session.events import EventBus
        from quant.session.service import SessionService
        from quant.session.store import SessionStore

        # Honor monkeypatched SESSIONS_DIR / RUNS_DIR on api_server.
        sessions_dir = _host_attr("SESSIONS_DIR", SESSIONS_DIR)
        runs_dir = _host_attr("RUNS_DIR", RUNS_DIR)

        store = SessionStore(base_dir=sessions_dir)
        event_bus = EventBus()

        try:
            loop = asyncio.get_event_loop()
            event_bus.set_loop(loop)
        except RuntimeError:
            pass

        _session_service = SessionService(
            store=store,
            event_bus=event_bus,
            runs_dir=runs_dir,
        )
        _set_host_attr("_session_service", _session_service)
        return _session_service
    except (ImportError, Exception) as exc:
        logger.debug("Session service unavailable: %s", exc)
        return None


def _get_channel_runtime():
    """Lazy-init IM channel runtime without starting platform adapters."""
    global _channel_runtime, _channel_bus, _channel_manager

    import sys as _sys
    _host = _sys.modules.get("api_server")
    if _host is not None and hasattr(_host, "_channel_runtime"):
        host_rt = getattr(_host, "_channel_runtime")
        if host_rt is not None:
            return host_rt
    elif _channel_runtime is not None:
        return _channel_runtime

    try:
        from fastapi import HTTPException
        from quant.channels.bus.queue import MessageBus
        from quant.channels.config import load_channels_config
        from quant.channels.manager import ChannelManager
        from quant.channels.runtime import ChannelRuntime

        svc = _get_session_service()
        if not svc:
            raise HTTPException(status_code=501, detail="Session runtime not enabled")

        _channel_bus = MessageBus()
        config = load_channels_config()
        _channel_manager = ChannelManager(config, _channel_bus, session_service=svc)
        _channel_runtime = ChannelRuntime(
            bus=_channel_bus,
            session_service=svc,
            manager=_channel_manager,
            reply_timeout_s=config["reply_timeout_s"],
        )
        _set_host_attr("_channel_runtime", _channel_runtime)
        _set_host_attr("_channel_bus", _channel_bus)
        _set_host_attr("_channel_manager", _channel_manager)
        return _channel_runtime
    except (ImportError, Exception) as exc:
        logger.debug("Channel runtime unavailable: %s", exc)
        from fastapi import HTTPException
        raise HTTPException(status_code=501, detail="Channel runtime not available")
