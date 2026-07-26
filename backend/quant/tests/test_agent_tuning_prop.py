# Feature: architecture-deepening, Property 7: AgentTuning injection respected by AgentLoop
"""Property test: AgentTuning injection respected by AgentLoop.

For ANY valid AgentTuning instance with arbitrary field values, an AgentLoop
constructed with that instance SHALL use exactly those field values — never
falling back to environment config or module-level accessors.

Validates: Requirements 5.3, 5.4, 5.7
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quant.agent.tuning import AgentTuning


# ---------------------------------------------------------------------------
# Strategies for valid AgentTuning field values
# ---------------------------------------------------------------------------

# token_threshold: positive int (realistic range)
st_token_threshold = st.integers(min_value=1_000, max_value=500_000)

# heartbeat_interval_s: positive float
st_heartbeat_interval = st.floats(
    min_value=0.1, max_value=60.0, allow_nan=False, allow_infinity=False
)

# reasoning_delta_min_interval_s: non-negative float
st_reasoning_delta = st.floats(
    min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False
)

# stream_retry_delay_s: non-negative float
st_stream_retry = st.floats(
    min_value=0.0, max_value=30.0, allow_nan=False, allow_infinity=False
)

# tool_timeout_seconds: positive float (0 means no timeout)
st_tool_timeout = st.floats(
    min_value=0.0, max_value=600.0, allow_nan=False, allow_infinity=False
)

# goal_max_continuations: non-negative int
st_goal_max_cont = st.integers(min_value=0, max_value=50)


@st.composite
def st_agent_tuning(draw):
    """Generate a random valid AgentTuning instance."""
    return AgentTuning(
        token_threshold=draw(st_token_threshold),
        heartbeat_interval_s=draw(st_heartbeat_interval),
        reasoning_delta_min_interval_s=draw(st_reasoning_delta),
        stream_retry_delay_s=draw(st_stream_retry),
        tool_timeout_seconds=draw(st_tool_timeout),
        goal_max_continuations=draw(st_goal_max_cont),
    )


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(tuning=st_agent_tuning())
def test_agent_loop_uses_injected_tuning_values(tuning: AgentTuning):
    """For any valid AgentTuning, AgentLoop._tuning holds exactly those values.

    **Validates: Requirements 5.3, 5.4, 5.7**
    """
    from quant.agent.loop import AgentLoop

    # Minimal stubs — AgentLoop requires registry and llm positional args.
    mock_registry = MagicMock()
    mock_registry.schema.return_value = []
    mock_llm = MagicMock()

    loop = AgentLoop(
        registry=mock_registry,
        llm=mock_llm,
        tuning=tuning,
    )

    # Core assertion: _tuning IS the exact object we injected
    assert loop._tuning is tuning

    # Field-level assertions — confirm no fallback or transformation occurred
    assert loop._tuning.token_threshold == tuning.token_threshold
    assert loop._tuning.heartbeat_interval_s == tuning.heartbeat_interval_s
    assert loop._tuning.reasoning_delta_min_interval_s == tuning.reasoning_delta_min_interval_s
    assert loop._tuning.stream_retry_delay_s == tuning.stream_retry_delay_s
    assert loop._tuning.tool_timeout_seconds == tuning.tool_timeout_seconds
    assert loop._tuning.goal_max_continuations == tuning.goal_max_continuations


@settings(max_examples=100)
@given(tuning=st_agent_tuning())
def test_agent_tuning_is_frozen(tuning: AgentTuning):
    """AgentTuning is immutable — no field can be reassigned after construction.

    **Validates: Requirements 5.3, 5.4, 5.7**
    """
    with pytest.raises(AttributeError):
        tuning.token_threshold = 999  # type: ignore[misc]

    with pytest.raises(AttributeError):
        tuning.heartbeat_interval_s = 0.1  # type: ignore[misc]
