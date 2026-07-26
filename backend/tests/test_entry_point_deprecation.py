"""Tests for deprecated standalone entry points.

Validates Requirements 1.4, 1.5: Running research/app.py or quant/api_server.py
directly should print a deprecation message and exit with code 1.
"""

import subprocess
import sys
from pathlib import Path

_BACKEND = Path(__file__).parents[1]


def test_research_app_deprecated():
    """Running research/app.py directly should print deprecation and exit 1."""
    r = subprocess.run(
        [sys.executable, "research/app.py"],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=str(_BACKEND),
    )
    assert r.returncode == 1
    output = (r.stdout + r.stderr).lower()
    assert "deprecated" in output


def test_quant_api_server_deprecated():
    """Running quant/api_server.py directly should print deprecation and exit 1."""
    r = subprocess.run(
        [sys.executable, "quant/api_server.py"],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=str(_BACKEND),
    )
    assert r.returncode == 1
    output = (r.stdout + r.stderr).lower()
    assert "deprecated" in output
