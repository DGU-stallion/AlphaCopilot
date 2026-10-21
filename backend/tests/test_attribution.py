"""策略归因（M4-5）。

## 这一层的价值在哪

回测给出「总收益 -16.88%」，但不告诉你**这 -16.88% 是怎么来的**：
是买错了标的，还是择时错了，还是费用吃掉了？

归因要回答：把一个总收益拆成几块，每块可以单独评价。

## 三个必须做对的判断

1. **择时 vs 选股要能分开**：满仓持有的收益（选股/选标的）与
   「在场/空仓的时机」（择时）是两个完全不同的能力，
   合成一个数字就什么都学不到。
2. **费用必须单独列，不能混进策略收益**：否则「策略不行」和「交易太频繁」
   分不清，而这两者的改进方向完全相反。
3. **拆出来的各块相加必须等于总收益**（可加性）。加不上的归因是错的，
   哪怕每一项看起来都合理 —— 这是归因分析最容易出错的地方。
"""

from __future__ import annotations

import pytest

from alpha.attribution import (
    buy_and_hold_return,
    cost_drag,
    exposure_split,
    timing_vs_selection,
    trade_costs,
)


class TestBuyAndHold:
    def test_simple(self):
        assert buy_and_hold_return([100.0, 110.0, 121.0]) == pytest.approx(0.21)

    def test_flat(self):
        assert buy_and_hold_return([100.0, 100.0]) == pytest.approx(0.0)

    def test_empty_or_single(self):
        assert buy_and_hold_return([]) is None
        assert buy_and_hold_return([100.0]) is None

    def test_zero_start_is_none_not_inf(self):
        """起点为 0 无法算收益率。返回 None，不返回 inf。"""
        assert buy_and_hold_return([0.0, 100.0]) is None


class TestExposureSplit:
    """把收益拆成「在场日」与「空仓日」两部分。

    空仓日收益恒为 0，所以「空仓贡献」应该正好是 0 —— 这是可加性检验的锚点。
    """

    def test_all_in_market(self):
        eq = [100.0, 110.0, 121.0]
        out = exposure_split(eq, positions=[100, 100, 100])
        assert out["in_market_days"] == 3
        assert out["out_market_days"] == 0
        assert out["in_market_return"] == pytest.approx(0.21)

    def test_half_time_out(self):
        # 第 2 天空仓（权益不变），第 3 天在场
        eq = [100.0, 100.0, 110.0]
        out = exposure_split(eq, positions=[100, 0, 100])
        assert out["out_market_days"] == 1
        assert out["in_market_days"] == 2

    def test_empty_is_zero_not_crash(self):
        out = exposure_split([], positions=[])
        assert out["in_market_days"] == 0
        assert out["in_market_return"] is None


class TestTradeCosts:
    def test_sums_costs(self):
        trades = [
            {"side": "buy", "amount": 10000.0, "fee": 5.0},
            {"side": "sell", "amount": 10000.0, "fee": 15.0},
        ]
        out = trade_costs(trades)
        assert out["total_fee"] == pytest.approx(20.0)
        assert out["n_trades"] == 2

    def test_empty(self):
        out = trade_costs([])
        assert out["total_fee"] == 0.0
        assert out["n_trades"] == 0

    def test_cost_drag_is_ratio_of_capital(self):
        """费用耗损要表达成「占总资金的比例」，不是绝对金额。

        绝对金额没法跨策略比较（大资金 100 块费用毫无意义）。
        """
        assert cost_drag(total_fee=100.0, capital=10000.0) == pytest.approx(0.01)
        assert cost_drag(total_fee=0.0, capital=10000.0) == pytest.approx(0.0)

    def test_cost_drag_zero_capital_is_none(self):
        assert cost_drag(total_fee=100.0, capital=0.0) is None


class TestTimingVsSelection:
    """择时与选股分开 —— 归因的核心。

    关键约束：**必须有 benchmark（标的自身价格）**。
    拿策略净值冒充满仓基准是假的（净值里已含空仓，差值恒 0，
    「择时」永远显示 0 —— 看着漂亮，实际什么都没算）。
    """

    def test_without_benchmark_timing_is_none_not_zero(self):
        """缺基准时 reporting None，不是 0。

        0 会被读成「择时没有贡献」，而实际是「没算」。
        两者对决策的含义完全相反。
        """
        out = timing_vs_selection([100.0, 110.0, 121.0], positions=[100, 100, 100])
        assert out["total"] == pytest.approx(0.21)
        assert out["timing"] is None
        assert out["full"] is None
        assert out["note"]          # 必须说明为什么算不了

    def test_always_in_has_no_timing_component(self):
        """全程在场且基准 = 策略净值 → 择时恰好为 0（差值为 0 是真实的，不是缺省）。"""
        eq = [100.0, 110.0, 121.0]
        out = timing_vs_selection(eq, positions=[100, 100, 100], benchmark=eq)
        assert out["timing"] == pytest.approx(0.0, abs=1e-9)
        assert out["selection"] == pytest.approx(0.21)

    def test_timing_positive_when_avoiding_drawdown(self):
        """空仓躲过下跌 → 择时贡献为正。

        策略：100 → 90（在场，跌）→ 90（空仓，持平）→ 99（在场，涨）
        基准（一直持有）：100 → 90 → 81 → 89.1（继续跌）
        策略少亏了，差额就是择时的贡献。
        """
        strat = [100.0, 90.0, 90.0, 99.0]
        bench = [100.0, 90.0, 81.0, 89.1]
        out = timing_vs_selection(strat, positions=[100, 100, 0, 100], benchmark=bench)
        assert out["timing"] > 0, out

    def test_timing_negative_when_missing_rally(self):
        """空仓踏空 → 择时贡献为负。这条同样重要：择时也会帮倒忙。"""
        strat = [100.0, 100.0, 100.0]          # 空仓，没涨
        bench = [100.0, 110.0, 121.0]          # 标的涨了 21%
        out = timing_vs_selection(strat, positions=[0, 0, 0], benchmark=bench)
        assert out["timing"] < 0, out

    def test_components_add_up_to_total(self):
        """可加性：timing + selection == total（误差 < 1e-6，因为都四舍五入到 6 位）。"""
        cases = [
            ([100.0, 105.0, 103.0, 110.0], [100, 100, 100, 100], [100.0, 105.0, 103.0, 110.0]),
            ([100.0, 100.0, 108.0], [100, 0, 100], [100.0, 110.0, 121.0]),
            ([100.0, 95.0, 95.0, 100.0, 104.0], [100, 100, 0, 100, 100],
             [100.0, 95.0, 90.0, 95.0, 99.0]),
        ]
        for strat, pos, bench in cases:
            out = timing_vs_selection(strat, positions=pos, benchmark=bench)
            assert out["timing"] + out["selection"] == pytest.approx(out["total"], abs=1e-6), out

    def test_empty_returns_nones(self):
        out = timing_vs_selection([], positions=[], benchmark=[])
        assert out["total"] is None
        assert out["timing"] is None
        assert out["selection"] is None
