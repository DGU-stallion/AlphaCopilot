"""行情/基本面/资金面工具单元测试 —— mock 数据层，无需网络。"""

from unittest.mock import patch

from alphacopilot_research.tools.flows import (
    get_block_trade,
    get_dividend_history,
    get_dragon_tiger,
    get_holder_changes,
)
from alphacopilot_research.tools.fundamental import (
    _MAX_CHARS,
    get_financials,
    get_margin_trading,
    get_valuation,
)


def test_get_valuation_success():
    fake = {"code": "600519", "pe_ttm": 20.0}
    with patch("alphacopilot_research.tools.fundamental.astock.full_valuation", return_value=fake) as m:
        result = get_valuation("600519")
        m.assert_called_once_with("600519")
        assert result == {"data": fake}


def test_get_valuation_error():
    with patch("alphacopilot_research.tools.fundamental.astock.full_valuation", side_effect=ValueError("boom")):
        result = get_valuation("600519")
        assert "error" in result


def test_get_financials_success():
    fake = {"revenue_yoy": 0.1}
    with patch("alphacopilot_research.tools.fundamental.astock.financials", return_value=fake) as m:
        result = get_financials("000858")
        m.assert_called_once()
        assert result == {"data": fake}


def test_get_financials_error():
    with patch("alphacopilot_research.tools.fundamental.astock.financials", side_effect=KeyError("missing")):
        result = get_financials("000001")
        assert "error" in result


def test_get_margin_success():
    fake = [{"date": "2026-08-01", "balance": 100.0}]
    with patch("research.astock.margin_trading", return_value=fake):
        result = get_margin_trading("600519")
        assert result == {"data": fake}
    fake = {"total": 1, "boards": []}
    with patch("alphacopilot_research.tools.flows.astock.dragon_tiger_board", return_value=fake) as m:
        result = get_dragon_tiger("600519")
        m.assert_called_once()
        assert result == {"data": fake}


def test_get_dragon_tiger_with_date():
    fake = {"total": 0}
    with patch("alphacopilot_research.tools.flows.astock.dragon_tiger_board", return_value=fake) as m:
        result = get_dragon_tiger("000858", trade_date="2026-07-01")
        m.assert_called_once_with("000858", trade_date="2026-07-01")
        assert result == {"data": fake}


def test_get_block_trade_success():
    fake = [{"price": 130.0}]
    with patch("alphacopilot_research.tools.flows.astock.block_trade", return_value=fake) as m:
        result = get_block_trade("600519")
        m.assert_called_once()
        assert result == {"data": fake}


def test_get_holder_changes_success():
    fake = [{"date": "2026-06-30", "count": 180000}]
    with patch("alphacopilot_research.tools.flows.astock.holder_num_change", return_value=fake) as m:
        result = get_holder_changes("600519")
        m.assert_called_once()
        assert result == {"data": fake}


def test_get_dividend_history_success():
    fake = [{"pay_date": "2026-06-15", "amount": 2.5}]
    with patch("alphacopilot_research.tools.flows.astock.dividend_history", return_value=fake) as m:
        result = get_dividend_history("600519")
        m.assert_called_once()
        assert result == {"data": fake}


def test_clip_truncation():
    from alphacopilot_research.tools.fundamental import _clip

    huge = {"x": "a" * (_MAX_CHARS + 100)}
    result = _clip(huge)
    assert result.get("truncated") is True
    assert len(result["head"]) == _MAX_CHARS


def test_clip_within_limit():
    from alphacopilot_research.tools.fundamental import _clip

    small = {"price": 1300.0}
    result = _clip(small)
    assert "truncated" not in result
    assert result["data"] == small
