"""Tool timeout/liveness regression tests."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from typing import Any

from quant.agent.loop import AgentLoop

from conftest import make_test_tuning


class _SlowRegistry:
    class _Tool:
        is_readonly = True

    def get(self, tool_name: str) -> object:
        return self._Tool()

    def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        time.sleep(1.0)
        return '{"status":"ok"}'


class _SlowWriteRegistry:
    class _Tool:
        is_readonly = False

    def __init__(self) -> None:
        self.completed = False

    def get(self, tool_name: str) -> object:
        return self._Tool()

    def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        time.sleep(0.08)
        self.completed = True
        return '{"status":"ok"}'


def test_tool_timeout_returns_error_and_stops_heartbeats() -> None:
    """A hung tool should become a bounded diagnostic instead of heartbeating forever."""
    _tuning = make_test_tuning(heartbeat_interval_s=0.01, tool_timeout_seconds=0.05)
    events: list[tuple[str, dict[str, Any]]] = []
    agent = AgentLoop(
        registry=_SlowRegistry(),  # type: ignore[arg-type]
        llm=SimpleNamespace(),
        tuning=_tuning,
        event_callback=lambda event_type, data: events.append((event_type, data)),
        max_iterations=1,
    )

    result, elapsed_ms = agent._invoke_tool("slow_tool", {})
    event_count_at_return = len(events)
    time.sleep(0.08)

    payload = json.loads(result)
    assert payload["status"] == "error"
    assert payload["error_code"] == "tool_timeout"
    assert payload["tool"] == "slow_tool"
    assert elapsed_ms >= 40
    assert len(events) == event_count_at_return


def test_write_tool_timeout_warns_but_does_not_return_before_completion() -> None:
    """Write tools must not report failure while their side effect continues."""
    _tuning = make_test_tuning(heartbeat_interval_s=0.01, tool_timeout_seconds=0.02)
    events: list[tuple[str, dict[str, Any]]] = []
    registry = _SlowWriteRegistry()
    agent = AgentLoop(
        registry=registry,  # type: ignore[arg-type]
        llm=SimpleNamespace(),
        tuning=_tuning,
        event_callback=lambda event_type, data: events.append((event_type, data)),
        max_iterations=1,
    )

    result, elapsed_ms = agent._invoke_tool("place_order", {})

    assert json.loads(result) == {"status": "ok"}
    assert registry.completed is True
    assert elapsed_ms >= 70
    assert any(
        event_type == "tool_progress" and data.get("stage") == "timeout_warning"
        for event_type, data in events
    )
