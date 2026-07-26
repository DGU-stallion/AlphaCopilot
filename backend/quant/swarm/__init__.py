"""Swarm multi-agent system — package entry point."""

from __future__ import annotations

from quant.swarm.models import (
    RunStatus,
    SwarmAgentSpec,
    SwarmEvent,
    SwarmRun,
    SwarmTask,
    TaskStatus,
    WorkerResult,
)
from quant.swarm.presets import build_run_from_preset, inspect_preset, list_presets, load_preset
from quant.swarm.runtime import SwarmRuntime
from quant.swarm.store import SwarmStore
from quant.swarm.worker import run_worker

__all__ = [
    "RunStatus",
    "SwarmAgentSpec",
    "SwarmEvent",
    "SwarmRun",
    "SwarmRuntime",
    "SwarmStore",
    "SwarmTask",
    "TaskStatus",
    "WorkerResult",
    "build_run_from_preset",
    "inspect_preset",
    "list_presets",
    "load_preset",
    "run_worker",
]
