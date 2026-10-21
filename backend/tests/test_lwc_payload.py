"""renderer=lwc 的载荷整形（M2-6）。

测的是三条「画错比不画更糟」的规则：
  - 系列与横轴长度不一致 → 整条丢弃（错位的净值曲线会误导人）
  - 非有限数 → 跳过而不是补 0（补 0 会在曲线上造出假的断崖）
  - 时间严格递增去重（LWC 内部断言要求，否则抛错白屏）
"""

import math

from alpha.lwc import lwc_payload, option_to_series


def _opt(series: list[dict], x: list[str] | None = None) -> dict:
    """默认按最长系列生成长度匹配的横轴（手写长度容易写错，已踩）。"""
    if x is None:
        n = max((len(s.get("data") or []) for s in series), default=3)
        x = [f"d{i + 1}" for i in range(n)]
    return {"xAxis": {"type": "category", "data": x}, "series": series}


def test_basic_line_option_converted():
    out = option_to_series(_opt([{"name": "策略", "data": [1.0, 1.1, 1.05]}]))
    assert out == [{
        "name": "策略",
        "points": [
            {"time": "d1", "value": 1.0},
            {"time": "d2", "value": 1.1},
            {"time": "d3", "value": 1.05},
        ],
    }]


def test_length_mismatch_drops_whole_series():
    """长度不一致说明 series 与 xAxis 不同源。整条丢，不截断对齐。"""
    # 显式给 3 个横轴点，但 series 只有 2 个值 —— 必须整条丢
    out = option_to_series(_opt([{"name": "坏", "data": [1.0, 2.0]}], ["d1", "d2", "d3"]))
    assert out == []


def test_non_finite_values_skipped_not_zeroed():
    """None / NaN / inf 对应的点跳过。补 0 会造出假断崖。"""
    out = option_to_series(_opt([
        {"name": "含空", "data": [1.0, None, float("nan")]},
        {"name": "含inf", "data": [1.0, math.inf, 3.0]},
    ]))
    assert out[0]["points"] == [{"time": "d1", "value": 1.0}]
    assert [p["time"] for p in out[1]["points"]] == ["d1", "d3"]


def test_series_entirely_non_finite_dropped():
    out = option_to_series(_opt([{"name": "全空", "data": [None, None, None]}]))
    assert out == []


def test_xaxis_missing_returns_empty():
    assert option_to_series({"series": [{"name": "x", "data": [1, 2]}]}) == []
    assert option_to_series(None) == []
    assert option_to_series({}) == []


def test_multiple_series_keep_order():
    out = option_to_series(_opt([
        {"name": "策略", "data": [1.0, 1.1, 1.2]},
        {"name": "基准", "data": [1.0, 1.0, 0.9]},
    ]))
    assert [s["name"] for s in out] == ["策略", "基准"]


class TestDrawdown:
    def test_drawdown_is_non_positive(self):
        """回撤 ≤ 0。正值说明算错了（相对历史最高点不会高于 0）。"""
        opt = _opt([{"name": "策略", "data": [1.0, 1.2, 0.9, 1.3]}])
        dd = lwc_payload(opt)["drawdown"]
        assert all(p["value"] <= 0 for p in dd)

    def test_drawdown_values_correct(self):
        # 1.0 → 峰值 1.0, dd=0；1.2 → 峰值 1.2, dd=0；0.9 → (0.9-1.2)/1.2=-25%
        opt = _opt([{"name": "策略", "data": [1.0, 1.2, 0.9]}])
        dd = lwc_payload(opt)["drawdown"]
        assert [round(p["value"], 4) for p in dd] == [0.0, 0.0, -0.25]

    def test_drawdown_same_length_as_equity(self):
        """净值与回撤必须一一对应，否则 pane 之间会错位。"""
        opt = _opt([{"name": "策略", "data": [1.0, 1.2, 0.9, 1.1]}])
        payload = lwc_payload(opt)
        assert len(payload["drawdown"]) == len(payload["series"][0]["points"])

    def test_drawdown_empty_when_no_series(self):
        assert lwc_payload(_opt([]))["drawdown"] == []

    def test_drawdown_uses_first_series_only(self):
        """回撤只对主策略算（基准回撤放在另一个 pane 会看不过来）。"""
        opt = _opt([
            {"name": "策略", "data": [1.0, 0.8, 0.9]},
            {"name": "基准", "data": [1.0, 1.0, 1.0]},
        ])
        payload = lwc_payload(opt)
        assert len(payload["series"]) == 2
        assert payload["drawdown"][1]["value"] < 0   # 来自策略，不是基准
