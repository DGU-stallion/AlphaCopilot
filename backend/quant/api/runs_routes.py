"""Run management HTTP routes."""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials

from quant.api._compat import host_attr as _host_attr
from quant.api.helpers import RUNS_DIR, _validate_path_param
from quant.api.security import _security, require_auth

logger = logging.getLogger(__name__)


# ============================================================================
# File loading helpers (re-exported by api_server for test compat)
# ============================================================================


def _load_json_file(path: Path) -> Optional[Dict[str, Any]]:
    """Load a JSON file, returning None on failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_csv_to_dict(path: Path, max_rows: int = 500) -> List[Dict[str, Any]]:
    """Load a CSV file as a list of dicts (capped to max_rows)."""
    rows: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i >= max_rows:
                    break
                rows.append(dict(row))
    except OSError:
        pass
    return rows


def _build_response_from_run_dir(run_dir: Path) -> Dict[str, Any]:
    """Build a run response dict from the filesystem state."""
    result: Dict[str, Any] = {"run_id": run_dir.name, "run_directory": str(run_dir)}

    # Status
    status_file = run_dir / "status.json"
    status_data = _load_json_file(status_file)
    if status_data:
        result["status"] = status_data.get("status", "unknown")
        result["elapsed_seconds"] = status_data.get("elapsed_seconds", 0)
        result["reason"] = status_data.get("reason")
    else:
        result["status"] = "unknown"
        result["elapsed_seconds"] = 0

    # Metrics
    metrics_file = run_dir / "metrics.json"
    metrics = _load_json_file(metrics_file)
    if metrics:
        result["metrics"] = metrics

    # Run card
    run_card_file = run_dir / "run_card.json"
    run_card = _load_json_file(run_card_file)
    if run_card:
        result["run_card"] = run_card

    return result


# ============================================================================
# Registration
# ============================================================================


def register_runs_routes(router: APIRouter) -> None:
    """Mount run CRUD routes onto *router*."""

    @router.get("/runs")
    async def list_runs(
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        await require_auth(request, cred)
        runs_dir = _host_attr("RUNS_DIR", RUNS_DIR)
        if not runs_dir.exists():
            return []
        entries = []
        for d in sorted(runs_dir.iterdir(), reverse=True):
            if d.is_dir():
                entries.append({"run_id": d.name})
        return entries

    @router.get("/runs/{run_id}")
    async def get_run(
        run_id: str,
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        _validate_path_param(run_id, "run_id")
        await require_auth(request, cred)
        runs_dir = _host_attr("RUNS_DIR", RUNS_DIR)
        run_dir = runs_dir / run_id
        if not run_dir.exists():
            raise HTTPException(status_code=404, detail="Run not found")
        return _build_response_from_run_dir(run_dir)

    @router.get("/runs/{run_id}/code")
    async def get_run_code(
        run_id: str,
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        _validate_path_param(run_id, "run_id")
        await require_auth(request, cred)
        runs_dir = _host_attr("RUNS_DIR", RUNS_DIR)
        run_dir = runs_dir / run_id
        code_file = run_dir / "strategy.py"
        if not code_file.exists():
            raise HTTPException(status_code=404, detail="Code not found")
        return {"code": code_file.read_text(encoding="utf-8")}

    @router.get("/runs/{run_id}/pine")
    async def get_run_pine(
        run_id: str,
        request: Request,
        cred: Optional[HTTPAuthorizationCredentials] = Security(_security),
    ):
        _validate_path_param(run_id, "run_id")
        await require_auth(request, cred)
        runs_dir = _host_attr("RUNS_DIR", RUNS_DIR)
        run_dir = runs_dir / run_id
        pine_file = run_dir / "pinescript.pine"
        if not pine_file.exists():
            raise HTTPException(status_code=404, detail="PineScript not found")
        return {"pine": pine_file.read_text(encoding="utf-8")}
