# Feature: architecture-deepening, Property 2: Cache isolation via injection
"""Property test: cache isolation via injection.

For any research route handler that accesses a cache, if a custom
ResearchCaches instance is injected via create_research_router(caches=custom),
then all cache reads and writes performed by that handler SHALL use the
injected instance and SHALL NOT touch any module-level global.

**Validates: Requirements 3.5, 3.6**
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

# Ensure research package is importable
_research_dir = Path(__file__).resolve().parent.parent
if str(_research_dir) not in sys.path:
    sys.path.insert(0, str(_research_dir))

from caches import ResearchCaches  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from fastapi import FastAPI  # noqa: E402


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

stock_code_strategy = st.from_regex(r"[0-9]{6}", fullmatch=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_mock_astock():
    """Create a mock astock module that returns simple data."""
    mock = MagicMock()
    mock.DependencyMissing = type("DependencyMissing", (Exception,), {})
    mock.valuation_percentile.return_value = {"pe_pct": 0.5, "pb_pct": 0.3}
    mock.announcements.return_value = [{"title": "test announcement"}]
    mock.financials.return_value = {"revenue": 1000}
    mock.margin_trading.return_value = {"margin": 100}
    mock.block_trade.return_value = {"trades": []}
    mock.holder_num_change.return_value = {"count": 500}
    mock.dividend_history.return_value = {"dividends": []}
    mock.stock_fund_flow_120d.return_value = {"inflow": 10}
    mock.dragon_tiger_board.return_value = {"entries": []}
    mock.lockup_expiry.return_value = {"lockups": []}
    mock.concept_blocks.return_value = {"blocks": []}
    mock.hot_concepts.return_value = {"concepts": []}
    mock.investor_qa.return_value = {"questions": []}
    mock.industry_comparison.return_value = {"industries": []}
    return mock


def _make_app_with_caches(caches: ResearchCaches) -> FastAPI:
    """Create a minimal FastAPI app with mocked external deps and injected caches.

    We must patch the external modules (astock, gstock, market, etc.) in the
    route sub-modules AFTER they've been imported, since they capture references
    at import time.
    """
    from router import create_research_router  # noqa: E402

    app = FastAPI()
    router = create_research_router(caches=caches)
    app.include_router(router)
    return app


def _patch_externals():
    """Return a context manager that patches external deps in the route modules."""
    mock_astock = _build_mock_astock()

    # Patch the astock reference in market_data and reports_news modules
    # since those modules imported astock at their top level.
    import routes.market_data as md_mod
    import routes.reports_news as rn_mod

    patches = [
        patch.object(md_mod, "astock", mock_astock),
        patch.object(md_mod, "gstock", MagicMock()),
        patch.object(md_mod, "market", MagicMock()),
        patch.object(rn_mod, "astock", mock_astock),
        patch.object(rn_mod, "newsradar", MagicMock()),
        patch.object(rn_mod, "mr", MagicMock()),
    ]
    return patches


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(code=stock_code_strategy)
def test_valuation_percentile_cache_isolation(code: str):
    """Writes to pct_cache on router_a must not appear in router_b's caches."""
    caches_a = ResearchCaches()
    caches_b = ResearchCaches()

    app_a = _make_app_with_caches(caches_a)

    patches = _patch_externals()
    for p in patches:
        p.start()
    try:
        client_a = TestClient(app_a)
        resp = client_a.get(f"/valuation/percentile?code={code}")
        assert resp.status_code == 200
    finally:
        for p in patches:
            p.stop()

    # pct_cache of caches_a should have an entry for this code
    assert code in caches_a.pct_cache

    # pct_cache of caches_b must remain empty — cache isolation
    assert len(caches_b.pct_cache) == 0
    assert len(caches_b.ann_cache) == 0
    assert len(caches_b.fin_cache) == 0
    assert len(caches_b.dc_cache) == 0


@settings(max_examples=100, deadline=None)
@given(code=stock_code_strategy)
def test_announcements_cache_isolation(code: str):
    """Writes to ann_cache on router_a must not appear in router_b's caches."""
    caches_a = ResearchCaches()
    caches_b = ResearchCaches()

    app_a = _make_app_with_caches(caches_a)

    patches = _patch_externals()
    for p in patches:
        p.start()
    try:
        client_a = TestClient(app_a)
        resp = client_a.get(f"/announcements?code={code}")
        assert resp.status_code == 200
    finally:
        for p in patches:
            p.stop()

    # ann_cache of caches_a should have an entry
    assert code in caches_a.ann_cache

    # caches_b must remain untouched
    assert len(caches_b.ann_cache) == 0
    assert len(caches_b.pct_cache) == 0
    assert len(caches_b.fin_cache) == 0
    assert len(caches_b.dc_cache) == 0


@settings(max_examples=100, deadline=None)
@given(code=stock_code_strategy)
def test_financials_cache_isolation(code: str):
    """Writes to fin_cache on router_a must not appear in router_b's caches."""
    caches_a = ResearchCaches()
    caches_b = ResearchCaches()

    app_a = _make_app_with_caches(caches_a)

    patches = _patch_externals()
    for p in patches:
        p.start()
    try:
        client_a = TestClient(app_a)
        resp = client_a.get(f"/financials?code={code}")
        assert resp.status_code == 200
    finally:
        for p in patches:
            p.stop()

    # fin_cache of caches_a should have an entry
    assert code in caches_a.fin_cache

    # caches_b must remain untouched
    assert len(caches_b.fin_cache) == 0
    assert len(caches_b.pct_cache) == 0
    assert len(caches_b.ann_cache) == 0
    assert len(caches_b.dc_cache) == 0


@settings(max_examples=100, deadline=None)
@given(code=stock_code_strategy)
def test_dc_cache_isolation_via_margin(code: str):
    """Writes to dc_cache on router_a (via /margin) must not appear in router_b's caches."""
    caches_a = ResearchCaches()
    caches_b = ResearchCaches()

    app_a = _make_app_with_caches(caches_a)

    patches = _patch_externals()
    for p in patches:
        p.start()
    try:
        client_a = TestClient(app_a)
        resp = client_a.get(f"/margin?code={code}")
        assert resp.status_code == 200
    finally:
        for p in patches:
            p.stop()

    # dc_cache of caches_a should have an entry
    assert ("margin", code) in caches_a.dc_cache

    # caches_b must remain untouched
    assert len(caches_b.dc_cache) == 0
    assert len(caches_b.pct_cache) == 0
    assert len(caches_b.ann_cache) == 0
    assert len(caches_b.fin_cache) == 0


@settings(max_examples=100, deadline=None)
@given(code=stock_code_strategy)
def test_two_routers_no_cross_contamination(code: str):
    """Hitting endpoint on router_a, then router_b: each only touches its own cache."""
    caches_a = ResearchCaches()
    caches_b = ResearchCaches()

    app_a = _make_app_with_caches(caches_a)
    app_b = _make_app_with_caches(caches_b)

    patches = _patch_externals()
    for p in patches:
        p.start()
    try:
        client_a = TestClient(app_a)
        resp_a = client_a.get(f"/valuation/percentile?code={code}")
        assert resp_a.status_code == 200

        client_b = TestClient(app_b)
        resp_b = client_b.get(f"/valuation/percentile?code={code}")
        assert resp_b.status_code == 200
    finally:
        for p in patches:
            p.stop()

    # Both caches should have the entry for their own router
    assert code in caches_a.pct_cache
    assert code in caches_b.pct_cache

    # But neither cache leaked to the other's non-pct caches
    assert len(caches_a.ann_cache) == 0
    assert len(caches_a.fin_cache) == 0
    assert len(caches_a.dc_cache) == 0
    assert len(caches_b.ann_cache) == 0
    assert len(caches_b.fin_cache) == 0
    assert len(caches_b.dc_cache) == 0
