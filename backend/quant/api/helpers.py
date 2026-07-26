"""Path constants, dotenv I/O, SPA deep-link middleware, and path-parameter validation."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict

from fastapi import HTTPException, Request, status
from fastapi.responses import FileResponse

from quant.api._compat import host_attr as _host_attr


# ============================================================================
# Path constants
# ============================================================================

# helpers.py lives at backend/quant/api/helpers.py — AGENT_DIR is backend/quant/
_AGENT_DIR = Path(__file__).resolve().parent.parent  # quant/

RUNS_DIR = _AGENT_DIR / "runs"
SESSIONS_DIR = _AGENT_DIR / "sessions"
UPLOADS_DIR = _AGENT_DIR / "uploads"
AGENT_DIR = _AGENT_DIR
# User-writable config path — not inside the installed package directory.
ENV_PATH = Path.home() / ".vibe-trading" / ".env"
LEGACY_ENV_PATH = AGENT_DIR / ".env"
ENV_EXAMPLE_PATH = AGENT_DIR / ".env.example"


# ============================================================================
# SPA deep-link fallback
# ============================================================================

_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "dist"
_SPA_HTML_EXACT_PATHS: frozenset[str] = frozenset({"/correlation"})
_SPA_HTML_PATH_REGEX: tuple[re.Pattern[str], ...] = (
    re.compile(r"^/runs/[^/]+/?$"),
)


def _is_spa_html_route(path: str) -> bool:
    """Return True when *path* corresponds to a frontend SPA page."""
    if path in _SPA_HTML_EXACT_PATHS:
        return True
    return any(pattern.match(path) for pattern in _SPA_HTML_PATH_REGEX)


async def _spa_html_deep_link_fallback(request: Request, call_next):
    """Serve ``frontend/dist/index.html`` for SPA deep-link paths."""
    if request.method == "GET":
        accept = request.headers.get("accept", "")
        if "text/html" in accept and _is_spa_html_route(request.url.path):
            index = _FRONTEND_DIST / "index.html"
            if index.exists():
                return FileResponse(str(index))
    return await call_next(request)


# ============================================================================
# Dotenv helpers
# ============================================================================


def _ensure_agent_env_file() -> Path:
    """Ensure the agent env file exists (create parent dirs with 0o700)."""
    env_path = _host_attr("ENV_PATH", ENV_PATH)
    if not env_path.exists():
        env_path.parent.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            os.chmod(env_path.parent, 0o700)
        env_path.write_text("# Created by Vibe-Trading Web UI settings.\n", encoding="utf-8")
        if os.name != "nt":
            os.chmod(env_path, 0o600)
    return env_path


def _strip_env_value(value: str) -> str:
    """Remove basic dotenv quotes and inline comments."""
    value = value.strip()
    # Handle quoted values — preserve hash inside quotes
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        quote_char = value[0]
        inner = value[1:-1]
        # Check if there's a trailing comment after the close-quote
        # e.g. "secret" # comment  or 'secret' # comment
        # Actually we already stripped outer quotes, just return inner
        return inner

    # For quoted-then-comment patterns: "value" # comment
    if len(value) >= 2 and value[0] in {"'", '"'}:
        quote_char = value[0]
        end_quote = value.find(quote_char, 1)
        if end_quote > 0:
            inner = value[1:end_quote]
            return inner

    # Unquoted: strip inline comment
    if " #" in value:
        value = value.split(" #", 1)[0].rstrip()
    return value.strip()


def _read_env_values(path: Path) -> Dict[str, str]:
    """Read active KEY=value entries from a dotenv file."""
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = _strip_env_value(value)
    return values


def _project_relative_path(path: Path) -> str:
    """Return a project-relative display path."""
    try:
        return path.resolve().relative_to(AGENT_DIR.parent.resolve()).as_posix()
    except ValueError:
        return path.name


def _format_env_value(value: str) -> str:
    """Format a dotenv value without allowing multiline injection."""
    if "\n" in value or "\r" in value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Environment values cannot contain newlines",
        )
    value = value.strip()
    if not value:
        return ""
    if any(ch.isspace() for ch in value) or "#" in value:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def _write_env_values(path: Path, updates: Dict[str, str]) -> None:
    """Upsert active dotenv values while preserving comments and ordering."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(path.parent, 0o700)

    if not path.exists():
        path.write_text("", encoding="utf-8")
        if os.name != "nt":
            os.chmod(path, 0o600)

    lines = path.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()

    # Find LAST active (non-commented) occurrence of each key to update
    last_active_index: Dict[str, int] = {}
    for index, raw in enumerate(lines):
        stripped = raw.lstrip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            last_active_index[key] = index

    # Update last active line for each key
    for key, index in last_active_index.items():
        lines[index] = f"{key}={_format_env_value(updates[key])}"
        seen.add(key)

    # Append missing keys
    missing = [key for key in updates if key not in seen]
    if missing:
        if lines and lines[-1].strip():
            lines.append("")
        for key in missing:
            lines.append(f"{key}={_format_env_value(updates[key])}")

    content = "\n".join(lines) + "\n"
    path.write_text(content, encoding="utf-8")
    if os.name != "nt":
        os.chmod(path, 0o600)


def _is_configured_secret(value: str, placeholders: set[str] | None = None) -> bool:
    """Return True when a secret is set and not a documented placeholder."""
    normalized = value.strip().strip('"').strip("'")
    if not normalized:
        return False
    if placeholders:
        return normalized.lower() not in {p.lower() for p in placeholders}
    return True


def _coerce_float(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ============================================================================
# Path-parameter validation
# ============================================================================

_SAFE_PATH_PARAM_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _validate_path_param(value: str, kind: str) -> None:
    """Reject path parameters that could escape the parent directory."""
    if not _SAFE_PATH_PARAM_RE.fullmatch(value or ""):
        raise HTTPException(status_code=400, detail=f"invalid {kind}")
