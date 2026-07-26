#!/usr/bin/env python3
"""DEPRECATED standalone server. Route modules re-exported for compatibility.

The FastAPI application is no longer instantiated here. Use backend/app.py.
CLI entry via `vt serve` delegates to the unified app.
"""

from __future__ import annotations

import sys
import warnings

# ---------------------------------------------------------------------------
# When invoked directly as a script, print deprecation and exit immediately
# before attempting any package-relative imports.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(
        "⚠️  quant/api_server.py is deprecated. Use the unified entry point:\n"
        "    cd backend && python -m uvicorn app:app --port 8900\n",
        file=sys.stderr,
    )
    raise SystemExit(1)

# ---------------------------------------------------------------------------
# Re-exports for test compatibility — tests monkeypatch these attributes on
# the `api_server` module directly.
# TODO: remove once tests migrated
# ---------------------------------------------------------------------------

from quant.api.security import (  # noqa: F401, E402
    _API_KEY,
    _CORS_ORIGINS,
    _DEFAULT_CORS_ORIGINS,
    _DEFAULT_LOOPBACK_HOSTS,
    _EXTRA_LOOPBACK_HOSTS,
    _SAFE_BROWSER_METHODS,
    _apply_security_headers,
    _auth_credential_from_header_or_query,
    _configured_api_key,
    _consume_sse_ticket,
    _default_gateway_ips,
    _env_shell_tools_enabled,
    _host_without_port,
    _is_allowed_loopback_host,
    _is_local_client,
    _is_loopback_bind_host,
    _is_loopback_origin,
    _mint_sse_ticket,
    _origin_matches_request_host,
    _parse_cors_origins,
    _parse_extra_loopback_hosts,
    _redact_query_secrets,
    _reject_cross_site_browser_request,
    _reject_untrusted_loopback_host,
    _require_shutdown_authorization,
    _security,
    _shell_tools_enabled_for_request,
    _trusted_docker_loopback_ip,
    _validate_api_auth,
    install_access_log_redaction_filter,
    require_auth,
    require_event_stream_auth,
    require_local_or_auth,
    require_settings_write_auth,
)

from quant.api.models import (  # noqa: F401, E402
    Artifact,
    BacktestMetrics,
    RAGSelection,
    RunInfo,
    RunResponse,
)

from quant.api.helpers import (  # noqa: F401, E402
    AGENT_DIR,
    ENV_EXAMPLE_PATH,
    ENV_PATH,
    LEGACY_ENV_PATH,
    RUNS_DIR,
    SESSIONS_DIR,
    UPLOADS_DIR,
    _coerce_float,
    _coerce_int,
    _ensure_agent_env_file,
    _format_env_value,
    _FRONTEND_DIST,
    _is_configured_secret,
    _is_spa_html_route,
    _project_relative_path,
    _read_env_values,
    _SAFE_PATH_PARAM_RE,
    _spa_html_deep_link_fallback,
    _strip_env_value,
    _validate_path_param,
    _write_env_values,
)

from quant.api.state import (  # noqa: F401, E402
    _channel_bus,
    _channel_manager,
    _channel_runtime,
    _get_channel_runtime,
    _get_session_service,
    _session_service,
)

from quant.api.runs_routes import (  # noqa: F401, E402
    _load_json_file,
    _load_csv_to_dict,
    _build_response_from_run_dir,
)

from quant.api.sessions_routes import (  # noqa: F401, E402
    _goal_store,
    _live_action_frame_from_tool_result,
    _mandate_proposal_frame_from_tool_result,
)

from quant.api.system_routes import _terminate_current_process  # noqa: F401, E402

from quant.api.settings_routes import (  # noqa: F401, E402
    _baostock_supported,
    _baostock_installed,
    _load_llm_providers,
)

from quant.api.uploads_routes import (  # noqa: F401, E402
    MAX_UPLOAD_SIZE,
    _BLOCKED_UPLOAD_EXT,
    _BLOCKED_UPLOAD_NAMES,
    _SHADOW_ID_RE,
    _UPLOAD_CHUNK_SIZE,
)

from quant.api.channels_routes import (  # noqa: F401, E402
    ChannelPairingCommandRequest,
)

from quant.api.swarm_routes import _get_swarm_runtime  # noqa: F401, E402

from quant.api.live_routes import (  # noqa: F401, E402
    CommitMandateRequest,
    LiveHaltRequest,
    LiveAuthorizeRequest,
    LiveRunnerControlRequest,
    BrokerAuthState,
    MandateLimits,
    ActiveMandateState,
    RunnerLivenessState,
    LiveBrokerStatus,
    LiveStatusResponse,
    LiveRunnerUnavailable,
    _runner_tasks,
    _runner_factory,
    _emit_live_event,
    _fetch_broker_ceilings,
    _known_live_brokers,
    _oauth_token_present,
    _active_mandate_state,
    _runner_liveness_state,
    _live_broker_adapter,
    _build_live_runner,
    _drive_runner,
    _connector_verify_cache,
    _check_connector_status,
)

from quant.api.scheduled_routes import (  # noqa: F401, E402
    CreateScheduledRunRequest,
    ScheduledRunResponse,
    _dispatch_scheduled_research_job,
    _get_scheduled_research_executor,
    _get_scheduled_research_store,
    _scheduled_research_scheduler_enabled,
)

from quant.ui_services import build_run_analysis, load_run_context  # noqa: F401, E402

# ---------------------------------------------------------------------------
# The standalone `app = FastAPI(...)` has been removed.
# Use the unified entry point at backend/app.py instead.
# ---------------------------------------------------------------------------


# ============================================================================
# Deprecated serve_main — kept for backward compatibility with CLI wrappers
# TODO: remove once tests migrated
# ============================================================================


def serve_main(argv: list[str] | None = None) -> int:
    """DEPRECATED: Start the API server.

    Delegates to the unified app at backend/app.py.
    """
    warnings.warn(
        "quant/api_server.py:serve_main() is deprecated. "
        "Use the unified entry point: cd backend && python -m uvicorn app:app --port 8900",
        DeprecationWarning,
        stacklevel=2,
    )
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Vibe-Trading Server (DEPRECATED)")
    parser.add_argument("--port", type=int, default=8000, help="Listen port (default 8000)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument("--dev", action="store_true", help="(ignored)")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    install_access_log_redaction_filter()

    # Delegate to the unified app
    from app import create_app

    try:
        uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")
    except Exception:
        pass
    return 0
