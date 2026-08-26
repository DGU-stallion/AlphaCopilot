"""Smoke tests: research data-layer library imports cleanly without web framework deps.

caches.py is excluded — it is FastAPI response-cache glue kept only as archive
reference; it will be replaced by MCP-side caching (T08+).
"""

import research.astock
import research.chat
import research.cli_runtime
import research.gstock
import research.market
import research.models
import research.myreports
import research.newsradar
import research.portfolio


def test_core_data_functions_exposed():
    assert callable(research.astock.kline)
    assert callable(research.astock.tencent_quote)
    assert callable(research.astock.full_valuation)
    assert callable(research.gstock.us_hk_stock)
    assert callable(research.newsradar.get_radar)


def test_analysis_framework_is_frozen():
    from research.chat import ANALYSIS_FRAMEWORK

    for dimension in ("估值", "资金面", "财报质量", "行业景气", "事件催化"):
        assert dimension in ANALYSIS_FRAMEWORK
