"""区间参数必须真的生效（ROUND2 A5）。

## 两个真 bug（2026-10-22 核实）

1. **前端给了后端不认的选项**：`ParamBar` 的 date_range 下拉有 2y/3y，
   而后端 `ParamSpec._coerce_date_range` 只认 1y/6m/3m 或 ISO 区间。
   选「2 年」直接 400。这是我自己引入的（把 UI 选项写成想当然）。

2. **ISO 日期被静默忽略**：后端*接受* `"2024-01-01:2024-12-31"`（校验通过），
   但 5 处调用点都是 `_RANGE_COUNT.get(range, 250)` —— 键对不上就默默取最近
   250 天。用户选了 2024 年，拿到的是最近一年，而且**没有任何提示**。
   这是「算错」类 bug，比抛异常危险得多。
"""

from __future__ import annotations

import pytest

from alpha import data


def _fake_rows(n: int = 400, start_day: int = 1):
    """造 n 根日线，日期从 2025-01-01 起逐日递增（跳过月份长度差异不影响本测）。"""
    import datetime as dt

    base = dt.date(2025, 1, 1)
    return [
        {"datetime": (base + dt.timedelta(days=i)).isoformat(), "close": 100.0 + i}
        for i in range(n)
    ]


@pytest.fixture()
def fake_kline(monkeypatch):
    rows = _fake_rows()
    monkeypatch.setattr(data, "kline", lambda code, period=0, count=250: rows[-count:])
    return rows


class TestPresetRanges:
    def test_1y_maps_to_250_bars(self, fake_kline):
        out = data.closes_for_range("600519", "1y")
        assert len(out) == 250

    def test_3m_maps_to_63_bars(self, fake_kline):
        assert len(data.closes_for_range("600519", "3m")) == 63

    def test_6m_maps_to_126_bars(self, fake_kline):
        assert len(data.closes_for_range("600519", "6m")) == 126


class TestIsoRanges:
    def test_iso_range_actually_filters_by_date(self, fake_kline):
        """核心断言：给了起止日期，返回的每一条都必须落在区间内。

        旧实现会忽略日期直接给「最近 250 根」，于是 2025-02-01 之前的行也会出现。
        """
        out = data.closes_for_range("600519", "2025-02-01:2025-02-28")
        assert out, "区间内应有数据"
        dates = [d for d, _ in out]
        assert dates[0] >= "2025-02-01"
        assert dates[-1] <= "2025-02-28"
        assert len(out) == 28, f"2025-02 应恰好 28 天，实得 {len(out)}"

    def test_iso_range_is_not_ignored(self, fake_kline):
        """回归保护：旧实现返回 250 根，区间过滤后必然更少。"""
        iso = data.closes_for_range("600519", "2025-02-01:2025-02-10")
        preset = data.closes_for_range("600519", "1y")
        assert len(iso) < len(preset)

    def test_iso_range_outside_data_returns_empty(self, fake_kline):
        """区间完全没有数据 → 空列表（不是「拿最近的凑」）。"""
        assert data.closes_for_range("600519", "2020-01-01:2020-12-31") == []

    def test_iso_range_swapped_dates_rejected(self, fake_kline):
        """start > end 是用户填错，要报错而不是返回奇怪的结果。"""
        with pytest.raises(ValueError):
            data.closes_for_range("600519", "2025-03-01:2025-02-01")

    def test_unknown_preset_still_falls_back_to_default(self, fake_kline):
        """未知预设仍按 250 根兜底 —— 保持旧行为，避免一次改动同时改两件事。"""
        assert len(data.closes_for_range("600519", "whatever")) == 250
