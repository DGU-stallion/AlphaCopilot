"""Shared fixtures for all tests.

Import resolution relies on the installed package (pip install -e .).
"""

from __future__ import annotations

import pytest


def make_test_tuning(**overrides):
    """Create an AgentTuning with test-safe defaults. Call at test runtime, not import time.

    Accepts keyword overrides for individual fields.
    """
    from quant.agent.tuning import AgentTuning
    defaults = dict(
        token_threshold=100_000,
        heartbeat_interval_s=0.5,
        reasoning_delta_min_interval_s=0.1,
        stream_retry_delay_s=0.0,
        tool_timeout_seconds=30.0,
        goal_max_continuations=5,
    )
    defaults.update(overrides)
    return AgentTuning(**defaults)


@pytest.fixture(autouse=True)
def _reset_env_config():
    """Clear the cached EnvConfig before each test so monkeypatch.setenv works."""
    from quant.config.accessor import reset_env_config
    reset_env_config()
    yield
    reset_env_config()
