"""T32 alpha.chart 测试 —— 4 类 helper 产出合法 option + 非法 option 被拒。"""

import pytest

from alpha import chart


def test_line_option_valid():
    opt = chart.line(["2024-01", "2024-02"], {"茅台": [1.0, 2.0]}, title="价格")
    assert opt["series"][0]["type"] == "line"
    assert opt["legend"]["data"] == ["茅台"]
    assert any(z["type"] == "inside" for z in opt["dataZoom"])
    chart.validate_option(opt)  # 幂等校验不抛


def test_bar_option_valid():
    opt = chart.bar(["A", "B"], {"量": [3, 5]})
    assert opt["series"][0]["type"] == "bar"
    chart.validate_option(opt)


def test_heatmap_option_valid():
    labels = ["茅台", "五粮液", "沪深300"]
    m = [[1.0, 0.8, 0.5], [0.8, 1.0, 0.4], [0.5, 0.4, 1.0]]
    opt = chart.heatmap(labels, m, title="相关性")
    assert opt["series"][0]["type"] == "heatmap"
    # N×N -> N*N 个格子
    assert len(opt["series"][0]["data"]) == 9
    # visualMap 相关系数域
    assert opt["visualMap"]["min"] == -1.0 and opt["visualMap"]["max"] == 1.0
    chart.validate_option(opt)


def test_heatmap_rejects_non_square():
    with pytest.raises(ValueError):
        chart.heatmap(["a", "b"], [[1.0, 0.5]])  # 1 行 != 2×2


def test_candlestick_option_valid_with_overlays():
    dates = ["d1", "d2", "d3"]
    ohlc = [[10, 11, 9, 12], [11, 10, 9, 11], [10, 12, 10, 13]]
    opt = chart.candlestick(dates, ohlc, title="茅台K线",
                            overlays={"MA20": [None, None, 11.0]})  # type: ignore[list-item]
    types = [s["type"] for s in opt["series"]]
    assert "candlestick" in types and "line" in types
    assert "MA20" in opt["legend"]["data"]
    chart.validate_option(opt)


def test_candlestick_rejects_bad_ohlc():
    with pytest.raises(ValueError):
        chart.candlestick(["d1"], [[10, 11, 9]])  # 少一个值


def test_validate_option_rejects_missing_series():
    with pytest.raises(ValueError):
        chart.validate_option({"title": {"text": "x"}})


def test_validate_option_rejects_bad_series_type():
    with pytest.raises(ValueError):
        chart.validate_option({"series": [{"type": "pie"}]})  # pie 不在支持集


def test_validate_option_rejects_empty_series():
    with pytest.raises(ValueError):
        chart.validate_option({"series": []})
