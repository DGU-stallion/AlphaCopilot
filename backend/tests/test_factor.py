"""T43 alpha.factor.correlation —— 相关性分析纯函数（三图）单元测试。

关键正确性由测试守护（非真实网络，monkeypatch 注入假数据）：
  1. 日期对齐取交集：一标的停牌缺 2 天，对齐后长度=交集长度。
  2. 相关基于日收益率而非价格：价格相关 ≠ 收益率相关（证明用了收益率）。
  3. 相关矩阵对角=1 且对称。
  4. 叠加走势归一化起点=100。

假数据：3 标的 × 10 天，S3 停牌缺 2 天（用于验证对齐取交集）。
"""

import pytest

from alpha import chart, factor

# 10 个交易日
_DATES = [f"2024-01-{d:02d}" for d in range(1, 11)]

# S1、S2 全 10 天；S3 缺 2024-01-04、2024-01-05（停牌）→ 交集应为 8 天。
# S2 与 S1 走势大体同向（价格皮尔逊高），但日间涨跌幅度不同 → 收益率相关明显不同于价格相关，
# 用以证明矩阵用的是收益率而非价格（价格非平稳会产生伪高相关）。
_S1 = [10.0, 10.2, 10.5, 10.3, 10.8, 11.0, 10.9, 11.2, 11.5, 11.3]
_S2 = [20.0, 20.1, 21.4, 21.3, 21.5, 22.3, 21.6, 22.9, 23.1, 23.0]
_S3 = [5.0, 5.1, 5.05, 4.9, 5.2, 5.0, 5.15, 5.3]  # 缺 04/05，走势与 S1 无强关联

_S3_DATES = [d for d in _DATES if d not in ("2024-01-04", "2024-01-05")]

_FAKE = {
    "000001": list(zip(_DATES, _S1, strict=True)),
    "000002": list(zip(_DATES, _S2, strict=True)),
    "000003": list(zip(_S3_DATES, _S3, strict=True)),
}


@pytest.fixture
def fake_data(monkeypatch):
    def fake_closes_with_dates(code, period=factor.data.DAY, count=250):
        return list(_FAKE[code])
    monkeypatch.setattr(factor.data, "closes_with_dates", fake_closes_with_dates)


def _series_by_name(option, name):
    return next(s for s in option["series"] if s["name"] == name)


# ---- overlay ----

def test_overlay_normalized_to_100_start(fake_data):
    option = factor.correlation_overlay(["000001", "000002"], "1y")
    chart.validate_option(option)  # 结构合法
    for name in ("000001", "000002"):
        s = _series_by_name(option, name)
        assert s["type"] == "line"
        assert s["data"][0] == 100.0, f"{name} 归一化起点应为 100"


def test_overlay_aligns_to_intersection(fake_data):
    # 含停牌标的：x 轴长度应为交集（8 天）
    option = factor.correlation_overlay(["000001", "000003"], "1y")
    assert len(option["xAxis"]["data"]) == len(_S3_DATES) == 8
    for name in ("000001", "000003"):
        assert len(_series_by_name(option, name)["data"]) == 8


# ---- matrix ----

def test_matrix_diagonal_one_and_symmetric(fake_data):
    option = factor.correlation_matrix(["000001", "000002", "000003"], "1y")
    assert option["series"][0]["type"] == "heatmap"
    m = factor._corr_matrix_values  # 供测试读取的最近一次矩阵（诊断用）
    n = len(m)
    for i in range(n):
        assert m[i][i] == pytest.approx(1.0), "对角必须=1"
        for j in range(n):
            assert m[i][j] == pytest.approx(m[j][i]), "矩阵必须对称"


def test_matrix_uses_returns_not_prices(fake_data):
    """价格相关 ≠ 收益率相关 —— 证明矩阵基于日收益率。

    S1、S2 价格近似线性放大（价格皮尔逊≈1），但日收益率序列不同，
    收益率相关应显著 < 价格相关（价格非平稳会产生伪高相关）。
    """
    # 对齐 S1、S2（全 10 天）
    a = _S1
    b = _S2
    price_corr = factor._pearson(a, b)
    ret_a = factor._pct_change(a)
    ret_b = factor._pct_change(b)
    ret_corr = factor._pearson(ret_a, ret_b)
    assert abs(ret_corr - price_corr) > 1e-6, "收益率相关应不同于价格相关"
    # 且矩阵里用的是收益率相关值
    factor.correlation_matrix(["000001", "000002"], "1y")
    assert factor._corr_matrix_values[0][1] == pytest.approx(ret_corr)


# ---- rolling ----

def test_rolling_correlation_line(fake_data):
    option = factor.correlation_rolling(["000001", "000002"], 3, "1y")
    chart.validate_option(option)
    assert option["series"][0]["type"] == "line"
    # 滚动窗口 window=3 基于收益率；收益率长度=9，滚动相关点数=9-3+1=7
    data = option["series"][0]["data"]
    assert len(data) == 7
    for v in data:
        assert -1.0 <= v <= 1.0


# ---- pure helpers ----

def test_pct_change_math():
    assert factor._pct_change([10.0, 11.0, 22.0]) == pytest.approx([0.1, 1.0])


def test_align_intersection():
    a = list(zip(["d1", "d2", "d3"], [1.0, 2.0, 3.0], strict=True))
    b = list(zip(["d2", "d3", "d4"], [9.0, 8.0, 7.0], strict=True))
    dates, cols = factor._align([a, b])
    assert dates == ["d2", "d3"]
    assert cols == [[2.0, 3.0], [9.0, 8.0]]
