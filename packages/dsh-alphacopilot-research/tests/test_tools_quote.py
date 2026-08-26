"""Unit tests for quote tools — mock data layer, no network."""

from unittest.mock import patch

from alphacopilot_research.tools.quote import _MAX_CHARS, get_kline, get_quote


def test_get_quote_success():
    fake = {"600519": {"name": "贵州茅台", "price": 1300.0}}
    with patch("alphacopilot_research.tools.quote.astock.tencent_quote", return_value=fake) as m:
        result = get_quote(["600519"])
        m.assert_called_once_with(["600519"])
        assert result == {"data": fake}


def test_get_quote_error_turns_into_error_dict():
    with patch("alphacopilot_research.tools.quote.astock.tencent_quote", side_effect=RuntimeError("boom")):
        result = get_quote(["000000"])
        assert "error" in result
        assert "RuntimeError" in result["error"]


def test_get_kline_success():
    fake = [{"open": 10, "close": 11}] * 3
    with patch("alphacopilot_research.tools.quote.astock.kline", return_value=fake) as m:
        result = get_kline("600519", category=4, offset=3)
        m.assert_called_once()
        assert result == {"data": fake}


def test_get_kline_error():
    with patch("alphacopilot_research.tools.quote.astock.kline", side_effect=ImportError("mootdx missing")):
        result = get_kline("600519")
        assert "error" in result


def test_clip_truncation():
    huge = {"x": "a" * (_MAX_CHARS + 100)}
    with patch("alphacopilot_research.tools.quote.astock.tencent_quote", return_value=huge):
        result = get_quote(["600519"])
        assert result.get("truncated") is True
        assert len(result["head"]) == _MAX_CHARS


def test_clip_within_limit_not_truncated():
    small = {"600519": {"price": 1}}
    with patch("alphacopilot_research.tools.quote.astock.tencent_quote", return_value=small):
        result = get_quote(["600519"])
        assert "truncated" not in result
        assert result["data"] == small
