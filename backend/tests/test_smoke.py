"""Smoke tests: research data-layer library imports cleanly without web framework deps.

Legacy dsh-route modules (chat / cli_runtime / portfolio / myreports / caches) were
removed during the deterministic-platform cleanup. Only the live data layer remains:
astock / gstock / market / newsradar / models.
"""

import research.astock
import research.gstock
import research.market
import research.models
import research.newsradar


def test_core_data_functions_exposed():
    assert callable(research.astock.kline)
    assert callable(research.astock.tencent_quote)
    assert callable(research.astock.full_valuation)
    assert callable(research.gstock.us_hk_stock)
    assert callable(research.newsradar.get_radar)
