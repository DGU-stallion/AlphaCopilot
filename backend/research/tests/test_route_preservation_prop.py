# Feature: architecture-deepening, Property 1: Research route set preservation
"""Property test: the split research router preserves all expected (method, path) tuples.

Since the original monolithic router no longer exists, this test defines a BASELINE_ROUTES
set representing the full route contract and verifies the refactored router matches exactly.

**Validates: Requirements 3.4**
"""

from __future__ import annotations

from router import create_research_router


# Baseline route set — every (HTTP method, path) the research API exposes.
# Captured from the monolithic implementation before the split (42 routes total).
BASELINE_ROUTES: set[tuple[str, str]] = {
    # router.py (inline)
    ("GET", "/health"),
    # chat.py
    ("POST", "/chat"),
    # portfolio.py
    ("GET", "/portfolio"),
    ("POST", "/portfolio/holding"),
    ("DELETE", "/portfolio/holding"),
    ("POST", "/portfolio/close"),
    ("DELETE", "/portfolio/close"),
    ("POST", "/portfolio/refresh"),
    # market_data.py — overview
    ("GET", "/market/overview"),
    ("GET", "/market/emotion"),
    ("GET", "/market/turnover-top"),
    # market_data.py — global
    ("GET", "/global/indices"),
    ("GET", "/global/stock"),
    # market_data.py — A-stock core
    ("GET", "/indices"),
    ("GET", "/quote"),
    ("GET", "/valuation/percentile"),
    ("GET", "/valuation"),
    ("GET", "/kline"),
    ("GET", "/finance"),
    ("GET", "/info"),
    ("GET", "/disclosure"),
    # market_data.py — signals / chips
    ("GET", "/margin"),
    ("GET", "/block-trade"),
    ("GET", "/holders"),
    ("GET", "/dividend"),
    ("GET", "/fund-flow"),
    ("GET", "/dragon-tiger"),
    ("GET", "/lockup"),
    ("GET", "/blocks"),
    ("GET", "/hot-concepts"),
    ("GET", "/investor-qa"),
    ("GET", "/industry"),
    # reports_news.py — my reports
    ("GET", "/myreports"),
    ("POST", "/myreports"),
    ("GET", "/myreports/file/{rid}"),
    ("DELETE", "/myreports/{rid}"),
    # reports_news.py — radar
    ("GET", "/radar"),
    ("POST", "/radar/refresh"),
    # reports_news.py — news, reports, announcements, financials
    ("GET", "/news"),
    ("GET", "/reports"),
    ("GET", "/announcements"),
    ("GET", "/financials"),
}


def _extract_routes(router) -> set[tuple[str, str]]:
    """Extract (method, path) tuples from a FastAPI APIRouter."""
    return {
        (method, route.path)
        for route in router.routes
        for method in (route.methods or set())
    }


def test_split_router_matches_baseline():
    """The refactored split router MUST expose exactly the same route set as the baseline."""
    router = create_research_router()
    actual_routes = _extract_routes(router)

    missing = BASELINE_ROUTES - actual_routes
    extra = actual_routes - BASELINE_ROUTES

    assert not missing, f"Routes missing from split router: {sorted(missing)}"
    assert not extra, f"Unexpected extra routes in split router: {sorted(extra)}"
    assert actual_routes == BASELINE_ROUTES


def test_route_count_unchanged():
    """The total number of routes must match the expected baseline count."""
    router = create_research_router()
    actual_routes = _extract_routes(router)
    assert len(actual_routes) == len(BASELINE_ROUTES), (
        f"Expected {len(BASELINE_ROUTES)} routes, got {len(actual_routes)}"
    )


def test_router_is_deterministic():
    """Calling create_research_router() multiple times yields identical route sets."""
    r1 = create_research_router()
    r2 = create_research_router()
    assert _extract_routes(r1) == _extract_routes(r2)
