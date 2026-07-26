# Feature: architecture-deepening, Properties 3-6: Quant Router correctness
"""Property tests for quant router fail-fast and deterministic behavior.

Property 3: Core dependency fail-fast
Property 4: No catch-all route regardless of optional dep availability
Property 5: Feature flag prevents import attempt
Property 6: Deterministic route set for a given configuration
"""
from __future__ import annotations

import builtins
import os
import sys
from types import ModuleType
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quant.router import OPTIONAL_ROUTE_MODULES

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CORE_MODULES = [
    "quant.api.sessions_routes",
    "quant.api.runs_routes",
]

_ALWAYS_ON_MODULES = [
    "quant.api.settings_routes",
    "quant.api.auth_routes",
    "quant.api.system_routes",
]

_OPTIONAL_FULL_PATHS = [
    f"quant.api.{name}" for name in OPTIONAL_ROUTE_MODULES.keys()
]

_real_import = builtins.__import__


def _make_route_module(module_name: str) -> ModuleType:
    """Create a fake module with a register_<name>_routes(router) function."""
    short_name = module_name.rsplit(".", 1)[-1]
    register_fn_name = f"register_{short_name}"

    mod = ModuleType(module_name)

    def _register(router):
        @router.get(f"/mock-{short_name}")
        def _endpoint():
            pass

    setattr(mod, register_fn_name, _register)
    return mod


def _quant_api_import(blocked: set[str]):
    """Build an __import__ replacement that intercepts only quant.api.* imports."""
    def _import_fn(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("quant.api."):
            if name in blocked:
                raise ImportError(f"Mocked unavailable: {name}")
            return _make_route_module(name)
        return _real_import(name, globals, locals, fromlist, level)
    return _import_fn


def _call_router(*, blocked: set[str] | None = None, env: dict[str, str] | None = None):
    """Call create_quant_router() with controlled quant.api.* imports and env vars."""
    blocked = blocked or set()
    env = env or {}
    import_fn = _quant_api_import(blocked)

    with patch.dict(os.environ, env, clear=False):
        with patch.object(builtins, "__import__", side_effect=import_fn):
            from quant.router import create_quant_router
            return create_quant_router()


def _get_route_set(router) -> set[tuple[str, str]]:
    """Extract (method, path) tuples from a FastAPI APIRouter."""
    routes = set()
    for route in router.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", "")
        for m in methods:
            routes.add((m.upper(), path))
    return routes


# ---------------------------------------------------------------------------
# Property 3: Core dependency fail-fast
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("core_module", _CORE_MODULES)
def test_core_dep_fail_fast(core_module: str):
    """If a core route module is unimportable, create_quant_router() raises ImportError.

    **Validates: Requirements 4.1**
    """
    with pytest.raises(ImportError):
        _call_router(blocked={core_module})


# ---------------------------------------------------------------------------
# Property 4: No catch-all route regardless of optional dep availability
# ---------------------------------------------------------------------------

st_unavailable_subset = st.frozensets(st.sampled_from(_OPTIONAL_FULL_PATHS))


@settings(max_examples=100)
@given(unavailable=st_unavailable_subset)
def test_no_catch_all(unavailable: frozenset[str]):
    """For any subset of optional deps unavailable, no /{path:path} catch-all exists.

    **Validates: Requirements 4.2, 4.3**
    """
    env_overrides = {flag: "1" for flag in OPTIONAL_ROUTE_MODULES.values()}

    router = _call_router(blocked=set(unavailable), env=env_overrides)

    for route in router.routes:
        path = getattr(route, "path", "")
        assert "{path:path}" not in path, (
            f"Catch-all route found: {path} (unavailable deps: {unavailable})"
        )


# ---------------------------------------------------------------------------
# Property 5: Feature flag prevents import attempt
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "module_name,flag_var",
    list(OPTIONAL_ROUTE_MODULES.items()),
)
def test_feature_flag_prevents_import(module_name: str, flag_var: str):
    """When a feature flag is set to '0', the module's import is never attempted.

    **Validates: Requirements 4.5**
    """
    full_module_name = f"quant.api.{module_name}"
    imported_modules: list[str] = []

    def _tracking_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("quant.api."):
            imported_modules.append(name)
            return _make_route_module(name)
        return _real_import(name, globals, locals, fromlist, level)

    # Set target flag to "0", all others to "1"
    env_overrides = {v: "1" for v in OPTIONAL_ROUTE_MODULES.values()}
    env_overrides[flag_var] = "0"

    with patch.dict(os.environ, env_overrides, clear=False):
        with patch.object(builtins, "__import__", side_effect=_tracking_import):
            from quant.router import create_quant_router
            create_quant_router()

    assert full_module_name not in imported_modules, (
        f"{full_module_name} was imported despite {flag_var}=0"
    )


# ---------------------------------------------------------------------------
# Property 6: Deterministic route set for a given configuration
# ---------------------------------------------------------------------------

st_flag_config = st.fixed_dictionaries(
    {flag: st.sampled_from(["0", "1"]) for flag in OPTIONAL_ROUTE_MODULES.values()}
)

st_unavailable_optional = st.frozensets(st.sampled_from(_OPTIONAL_FULL_PATHS))


@st.composite
def st_router_config(draw):
    """Generate a complete router configuration (flags + unavailable deps)."""
    flags = draw(st_flag_config)
    unavailable = draw(st_unavailable_optional)
    return flags, unavailable


@settings(max_examples=100)
@given(config=st_router_config())
def test_deterministic_routes(config):
    """For any fixed config, calling create_quant_router() twice yields identical route sets.

    **Validates: Requirements 4.6**
    """
    flags, unavailable = config

    router1 = _call_router(blocked=set(unavailable), env=flags)
    router2 = _call_router(blocked=set(unavailable), env=flags)

    routes1 = _get_route_set(router1)
    routes2 = _get_route_set(router2)

    assert routes1 == routes2, (
        f"Non-deterministic routes!\n"
        f"  First call:  {sorted(routes1)}\n"
        f"  Second call: {sorted(routes2)}\n"
        f"  Config: flags={flags}, unavailable={unavailable}"
    )
