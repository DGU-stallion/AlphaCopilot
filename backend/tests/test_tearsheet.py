"""Tear sheet（M4-2）。

用**答案已知的构造数据**测，不用真实行情（那样测试会随数据变化闪烁）。

这里重点守的是七条「会让人误判」的口径（模块 docstring 的约定 1–8）：
每一条错了都不会让程序崩，但会让报告**说谎**——那比崩更危险。
"""

from __future__ import annotations

import math

import pytest

from alpha import tearsheet as ts


def _eq(*v: float) -> list[float]:
    return list(v)


class TestDailyReturns:
    def test_simple(self):
        assert ts.daily_returns([1.0, 1.1, 1.21]) == pytest.approx([0.1, 0.1])

    def test_empty_or_single(self):
        assert ts.daily_returns([]) == []
        assert ts.daily_returns([1.0]) == []


class TestRollingSharpe:
    def test_monotonic_up_has_high_sharpe(self):
        eq = [100.0 * (1.001 ** i) for i in range(200)]
        rs = ts.rolling_sharpe(eq, window=60)
        assert rs
        assert all(v is not None and v > 0 for v in rs[-10:])

    def test_flat_equity_returns_zero_not_crash(self):
        """权益完全不变（空仓）→ std=0。不能除零、不能 inf/NaN。"""
        rs = ts.rolling_sharpe([100.0] * 120, window=60)
        assert all(v == 0.0 for v in rs if v is not None)
        assert not any(isinstance(v, float) and not math.isfinite(v) for v in rs if v is not None)

    def test_window_larger_than_data(self):
        assert ts.rolling_sharpe([100.0, 101.0], window=60) == []


class TestDrawdown:
    def test_monotonic_up_has_zero_drawdown(self):
        dd = ts.drawdown_series([100.0, 101.0, 102.0])
        assert all(d == 0.0 for d in dd)

    def test_depth_is_ratio_not_absolute(self):
        """深度是**百分比小数**（-0.2），不是绝对值（-20）也不是 -20%。"""
        dd = ts.drawdown_series([100.0, 120.0, 96.0])
        assert dd[2] == pytest.approx(-0.2)      # 96/120-1 = -0.2

    def test_duration_counts_days_underwater(self):
        # 100 → 120(峰) → 90 → 100 → 130(新高)
        info = ts.drawdown_duration([100.0, 120.0, 90.0, 100.0, 130.0])
        assert info["max_days"] == 2              # 90、100 两天在水下
        assert info["current_days"] == 0          # 已创新高
        assert info["episodes"]
        ep = info["episodes"][0]
        assert ep["depth"] == pytest.approx(-0.25)   # 90/120-1

    def test_current_drawdown_not_recovered(self):
        info = ts.drawdown_duration([100.0, 120.0, 90.0])
        assert info["current_days"] == 1
        assert info["max_days"] == 1


class TestMonthly:
    def test_month_attribution_across_year_boundary(self):
        """跨年时月份必须归对年 —— 这是最容易静默错的一处。"""
        dates = ["2026-12-30", "2026-12-31", "2027-01-04", "2027-01-05"]
        eq = [100.0, 110.0, 110.0, 121.0]
        rows = ts.monthly_returns(dates, eq)
        got = {(r["year"], r["month"]): r["ret"] for r in rows}
        # 12 月：100 → 110（+10%）；1 月：110 → 121（+10%）
        assert got[(2026, 12)] == pytest.approx(0.10, abs=1e-6)
        assert got[(2027, 1)] == pytest.approx(0.10, abs=1e-6)

    def test_month_without_any_data_is_none_not_zero(self):
        """日历全覆盖时，中间完全没有数据的月份也必须是 None。

        与「持平月」是两个不同的分支（`if not idxs` vs `flat`），
        变异测试发现只测持平月会漏掉这一条 —— 两条都要守。
        """
        # 1 月有数据、3 月有数据、2 月完全没有
        dates = ["2026-01-05", "2026-01-06", "2026-03-02", "2026-03-03"]
        eq = [100.0, 110.0, 120.0, 132.0]
        rows = ts.monthly_returns(dates, eq)
        got = {(r["year"], r["month"]): r["ret"] for r in rows}
        assert (2026, 2) in got, "日历全覆盖应包含 2 月"
        assert got[(2026, 2)] is None, "无数据的月份必须是 None，不能是 0"

    def test_flat_month_is_none_not_zero(self):
        """空仓月（权益完全不变）给 None，不给 0。

        0 会让人以为「那个月在场且不赚不亏」；None 渲染成留白，不撒谎。
        """
        rows = ts.monthly_returns(["2026-01-05", "2026-01-06"], [100.0, 100.0])
        assert rows[0]["ret"] is None


class TestExposure:
    def test_all_in(self):
        e = ts.exposure([1, 1, 1, 1])
        assert e["in_market_pct"] == pytest.approx(1.0)

    def test_half_in(self):
        e = ts.exposure([1, 0, 1, 0])
        assert e["in_market_pct"] == pytest.approx(0.5)

    def test_empty_is_zero_not_crash(self):
        e = ts.exposure([])
        assert e["in_market_pct"] == 0.0
        assert e["avg_holding_days"] == 0.0


class TestTearSheetSummary:
    def _long(self, n=300):
        dates = [f"2026-{(i // 28) % 12 + 1:02d}-{i % 28 + 1:02d}" for i in range(n)]
        eq = [100.0 * (1.0005 ** i) for i in range(n)]
        return dates, eq

    def test_returns_structured_not_string(self):
        d, e = self._long()
        rep = ts.tear_sheet(d, e)
        assert isinstance(rep, dict)
        assert isinstance(rep["summary"], dict)
        assert "sharpe" in rep["summary"]

    def test_no_inf_or_nan_anywhere(self):
        """任何字段都不能是 inf/NaN —— 前端拿到 inf 会把色标炸掉。"""
        d, e = self._long()
        rep = ts.tear_sheet(d, e)

        def walk(o, path=""):
            if isinstance(o, dict):
                for k, v in o.items():
                    walk(v, f"{path}.{k}")
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    walk(v, f"{path}[{i}]")
            elif isinstance(o, float):
                assert math.isfinite(o), f"{path} 是 {o}"

        walk(rep)

    def test_flat_equity_does_not_crash(self):
        d, _ = self._long()
        rep = ts.tear_sheet(d, [100.0] * len(d))
        assert rep["summary"]["max_drawdown"] == 0.0

    def test_short_sample_annualized_is_none(self):
        """样本不足一年 → 年化必须是 None，绝不外推成「年化 300%」。"""
        dates = [f"2026-01-{i + 1:02d}" for i in range(10)]
        eq = [100.0 * (1.03 ** i) for i in range(10)]
        rep = ts.tear_sheet(dates, eq)
        assert rep["summary"]["annual_return"] is None
        assert rep["summary"]["calmar"] is None
        # 但波动率没有外推问题，照常给
        assert rep["summary"]["annual_volatility"] is not None

    def test_empty_input_no_crash(self):
        rep = ts.tear_sheet([], [])
        assert rep["summary"]["sharpe"] is None or rep["summary"]["sharpe"] == 0.0


class TestEmptyPositionIllusion:
    """空仓期对 Sharpe 的假象 —— 这是 tear sheet 里最会骗人的地方。

    只在少数日子满仓、其余空仓的策略，全序列 Sharpe 会被 0 收益日稀释抬高。
    不能假装能修复，但**必须让假象显形**：给 in_market_pct 与场内 Sharpe。
    """

    def test_reports_in_market_pct(self):
        n = 300
        dates = [f"2026-{(i // 28) % 12 + 1:02d}-{i % 28 + 1:02d}" for i in range(n)]
        eq = [100.0] * n
        # 只在最后 30 天上涨
        for i in range(n - 30, n):
            eq[i] = 100.0 * (1.01 ** (i - (n - 30)))
        rep = ts.tear_sheet(dates, eq)
        assert "in_market_pct" in rep["summary"]

    def test_notes_field_exists(self):
        """report["notes"] 必须是机器可读的列表（前端能直接展示）。"""
        n = 100
        dates = [f"2026-{(i // 28) % 12 + 1:02d}-{i % 28 + 1:02d}" for i in range(n)]
        rep = ts.tear_sheet(dates, [100.0] * n)
        assert isinstance(rep.get("notes"), list)
