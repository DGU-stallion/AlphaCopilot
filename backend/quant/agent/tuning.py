# quant/agent/tuning.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentTuning:
    """Immutable tuning parameters for the AgentLoop.

    All values are read once at construction. Tests inject custom instances
    rather than monkeypatching module globals.
    """

    token_threshold: int
    heartbeat_interval_s: float
    reasoning_delta_min_interval_s: float
    stream_retry_delay_s: float
    tool_timeout_seconds: float
    goal_max_continuations: int

    @classmethod
    def from_env_config(cls) -> AgentTuning:
        """Construct from the current environment configuration."""
        from quant.config.accessor import get_env_config

        cfg = get_env_config().agent_tuning
        return cls(
            token_threshold=cfg.token_threshold,
            heartbeat_interval_s=cfg.vt_heartbeat_interval_s,
            reasoning_delta_min_interval_s=cfg.vt_reasoning_delta_min_interval_s,
            stream_retry_delay_s=cfg.vt_stream_retry_delay_s,
            tool_timeout_seconds=cfg.vibe_trading_tool_timeout_seconds,
            goal_max_continuations=cfg.vibe_trading_goal_max_continuations,
        )
