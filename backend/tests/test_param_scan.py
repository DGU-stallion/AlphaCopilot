"""Param scan（M4-3）。

用**构造的确定性引擎替身**测，不跑真实数据（行情会让测试随日况闪烁）。

重点守的是五条「会让人误判」的口径（模块 docstring 约定 1–5）：
fast>=slow 必须排除、单格失败不断整次、best() 拒样本薄、高原/孤岛判定、
热力图双向色阶。每条错了都不会崩，但会让扫描**说谎**。
"""

from __future__ import annotations

import pytest

from alpha import param_scan as ps

FAST = [10, 20, 30]
SLOW = [20, 30, 40]          # 9 组里 fast>=slow 的：20/20,30/30,30/20×… 共 3 组


def _fake_engine(table: dict[tuple[int, int], dict] | None = None,
                 fail_on: tuple[int, int] | None = None):
    """引擎替身：metric 从表里查，查不到给默认值；fail_on 指定组合抛错。"""
    def engine(closes, dates, *, fast, slow, **kwargs):
        if fail_on and (fast, slow) == fail_on:
            raise ValueError("构造的引擎故障")
        m = (table or {}).get((fast, slow), {})
        return {"sharpe": m.get("sharpe", 0.5),
                "total_return": m.get("total_return", 0.1),
                "trade_count": m.get("trade_count", 10)}
    return engine


def _scan(engine, **kw) -> dict:
    return ps.scan([10.0] * 5, ["d1", "d2", "d3", "d4", "d5"],
                   fast_grid=kw.pop("fast_grid", FAST),
                   slow_grid=kw.pop("slow_grid", SLOW),
                   engine=engine, **kw)


class TestScanGrid:
    def test_grid_size_ignores_invalid_pairings(self):
        """3×3=9 组，fast>=slow 的 3 组跳过（不算但也不许静默丢）。"""
        r = _scan(_fake_engine())
        assert r["combos"] == 9
        assert len(r["grid"]) == 6
        assert len(r["failed"]) == 3
        got = {(e["fast"], e["slow"]) for e in r["grid"]}
        assert got == {(10, 20), (10, 30), (10, 40), (20, 30), (20, 40), (30, 40)}

    def test_invalid_pairings_recorded_with_reason(self):
        r = _scan(_fake_engine())
        pairs = {(e["fast"], e["slow"]) for e in r["failed"]}
        # fast>=slow 的对：本网格里为 (20,20),(30,30),(30,20)
        assert pairs == {(20, 20), (30, 30), (30, 20)}
        # reason 必须写明「无效」，让使用者能区分引擎异常 vs 无效组合
        for e in r["failed"]:
            assert "无效" in e["reason"]
            assert str(e["fast"]) in e["reason"] and str(e["slow"]) in e["reason"]


class TestSingleFailure:
    def test_one_engine_error_does_not_kill_scan(self):
        r = _scan(_fake_engine(fail_on=(20, 30)))
        assert len(r["grid"]) == 5          # 6 - 1 失败
        assert len(r["failed"]) == 4        # 3 无效 + 1 故障
        assert len({e["fast"] for e in r["grid"]}) == 3   # 其他组照常
        reason = next(e["reason"] for e in r["failed"] if e["fast"] == 20 and e["slow"] == 30)
        assert "构造的引擎故障" in reason

    def test_missing_metric_recorded_not_dropped(self):
        """请求的指标缺失的组合进 failed（记『指标缺失』），其余照常跑。"""
        def engine(closes, dates, *, fast, slow, **kw):
            if fast == 10:
                return {"sharpe": 1.0, "trade_count": 5}  # 无 total_return
            return {"sharpe": 0.2, "total_return": 0.0, "trade_count": 5}
        # scan(sharpe)：fast==10 组合都有 sharpe → 全部有效
        r = _scan(engine)
        assert len(r["grid"]) == 6
        # scan(total_return)：fast==10 的两个组合缺失 → 记 failed
        r2 = _scan(engine, fast_grid=[10, 20], slow_grid=[20, 30], metric="total_return")
        assert len(r2["grid"]) == 1        # (20,30) 有效；(10,20)(10,30) 缺指标
        assert sum(1 for e in r2["failed"] if "指标" in e["reason"]) == 2


class TestBest:
    def test_excludes_thin_samples(self):
        """1 次交易踩中一段大行情 → sharpe 虚高，不许进 top N。"""
        table = {
            (10, 20): {"sharpe": 9.0, "trade_count": 1},   # 样本薄，不许入选
            (10, 30): {"sharpe": 1.5, "trade_count": 12},
            (10, 40): {"sharpe": 1.0, "trade_count": 8},
            (20, 30): {"sharpe": 2.0, "trade_count": 15},
            (20, 40): {"sharpe": 0.6, "trade_count": 20},
            (30, 40): {"sharpe": 1.2, "trade_count": 30},
        }
        r = _scan(_fake_engine(table))
        top = ps.best(r, n=3)
        assert [t["fast"] for t in top] == [20, 10, 30]   # 无 10/20（sharpe 9 但 1 次交易）
        assert [(t["fast"], t["slow"]) for t in top] == \
            [(20, 30), (10, 30), (30, 40)]
        assert top[0]["value"] == pytest.approx(2.0)

    def test_min_trades_is_ceilable(self):
        table = {(10, 20): {"sharpe": 5.0, "trade_count": 2},
                 (10, 30): {"sharpe": 1.0, "trade_count": 5}}
        r = _scan(_fake_engine(table), slow_grid=[20, 30], fast_grid=[10])
        assert ps.best(r)[0]["fast"] == 10 and ps.best(r)[0]["slow"] == 30
        assert ps.best(r, min_trades=1)[0]["slow"] == 20   # 放宽门槛后可见


class TestStability:
    def _scan_from_values(self, values: dict[tuple[int, int], float]) -> dict:
        table = {k: {"sharpe": v, "trade_count": 10} for k, v in values.items()}
        fasts = sorted({f for f, _ in values})
        slows = sorted({s for _, s in values})
        return _scan(_fake_engine(table), fast_grid=fasts, slow_grid=slows)

    def test_plateau_detected(self):
        """最优点的邻居都保有高相对表现 → 高原。"""
        values = {(10, 20): 0.8, (10, 30): 0.99, (10, 40): 0.85,
                  (20, 30): 1.0, (20, 40): 0.99, (30, 40): 0.8}
        r = self._scan_from_values(values)
        st = ps.stability(r)
        assert st["verdict"] == "plateau"
        assert st["best"]["fast"] == 20 and st["best"]["slow"] == 30
        assert st["neighbor_mean_score"] == pytest.approx(0.95, abs=0.01)

    def test_island_detected(self):
        """只有一格高、邻居全塌 → 孤岛（最危险的「最优解」）。"""
        values = {}
        for f in (10, 20, 30):
            for s in (20, 30, 40):
                if f >= s:
                    continue
                values[(f, s)] = 1.0 if (f, s) == (20, 30) else 0.0
        r = self._scan_from_values(values)
        st = ps.stability(r)
        assert st["verdict"] == "island"
        assert st["neighbor_mean_score"] == pytest.approx(0.0, abs=0.01)

    def test_mixed_between_thresholds(self):
        # 邻居均分 ≈ (0.45/0.9 + 0.4/0.9)/2 ≈ 0.47（在 0.3–0.7 之间）→ mixed
        values = {(10, 20): 0.1, (10, 30): 0.55, (10, 40): 0.1,
                  (20, 30): 1.0, (20, 40): 0.5, (30, 40): 0.1}
        r = self._scan_from_values(values)
        st = ps.stability(r)
        assert st["verdict"] == "mixed"

    def test_single_combo_is_unknown(self):
        r = _scan(_fake_engine(), fast_grid=[10], slow_grid=[20])
        assert ps.stability(r)["verdict"] == "unknown"

    def test_empty_grid_is_unknown(self):
        r = _scan(_fake_engine(), fast_grid=[], slow_grid=[])
        assert ps.stability(r)["verdict"] == "unknown"


class TestHeatmap:
    def test_axes_and_cells(self):
        table = {(f, s): {"sharpe": i * 0.1, "trade_count": 9}
                 for i, (f, s) in enumerate([(10, 20), (10, 30), (10, 40),
                                             (20, 30), (20, 40), (30, 40)])}
        r = _scan(_fake_engine(table))
        h = ps.to_heatmap(r)
        assert h["xAxis"]["data"] == ["10", "20", "30"]
        assert h["yAxis"]["data"] == ["20", "30", "40"]
        assert len(h["series"][0]["data"]) == 6
        for x, y, _ in h["series"][0]["data"]:
            assert 0 <= x < 3 and 0 <= y < 3

    def test_bidirectional_scale(self):
        """双向色阶（红涨绿跌）：min<0<max，色带三段绿→白→红。"""
        table = {(10, 20): {"sharpe": -1.0, "trade_count": 9},
                 (10, 30): {"sharpe": 2.0, "trade_count": 9}}
        h = ps.to_heatmap(_scan(_fake_engine(table),
                                fast_grid=[10], slow_grid=[20, 30]))
        vm = h["visualMap"]
        assert vm["min"] < 0 < vm["max"]
        colors = vm["inRange"]["color"]
        assert len(colors) == 3                     # 绿 / 白 / 红
        assert colors[0] != colors[2]               # 正负都端到可见
        assert colors[-1].upper() == "#D9534F"      # A股口径：涨=红
        assert colors[0].upper() == "#3FAE7A"       # 跌=绿

    def test_empty_grid_no_crash(self):
        r = _scan(_fake_engine(), fast_grid=[], slow_grid=[])
        h = ps.to_heatmap(r)
        assert h["xAxis"]["data"] == []
        assert h["series"][0]["data"] == []


class TestDefaultEngine:
    def test_default_engine_runs_real_backtest_on_synthetic_data(self):
        """不注入引擎时的默认链路：golden_cross_signal + backtest_engine。"""
        n = 120
        closes = [100.0 * (1.001 ** i) for i in range(n)]
        r = ps.scan(closes, None, fast_grid=[5], slow_grid=[20])
        assert len(r["grid"]) == 1
        assert "sharpe" in r["grid"][0]["metrics"]
        assert r["grid"][0]["metrics"]["trade_count"] >= 0

    def test_default_engine_skips_invalid_pairings(self):
        closes = [100.0 * (1.001 ** i) for i in range(120)]
        r = ps.scan(closes, None, fast_grid=[20], slow_grid=[20])
        assert r["grid"] == [] and len(r["failed"]) == 1


class TestRegistry:
    def test_paramscan_heatmap_registered_as_echarts(self):
        from alpha.registry import get, is_registered

        assert is_registered("paramscan.heatmap")
        from api.page_spec import RENDERER_BY_FN

        assert RENDERER_BY_FN["paramscan.heatmap"] == "echarts"
        # 页函数数据不可用时应降级为空热力图，不许崩
        option = get("paramscan.heatmap").fn
        opt = option("000001", fast_grid="5", slow_grid="10", range="3m")
        assert opt["series"][0]["type"] == "heatmap"
