"""alpha.portfolio —— 雪球式模拟组合净值计算（S4）。

模型：组合 = 若干调仓事件（rebalance event），每个事件含生效日期 + {code: 目标权重}。
从首个事件生效日起按调仓事件持有，事件之间权重自然漂移。不涉及真实下单。

净值规则（对标 planning transcript 的确定性口径）：
  · 调仓在生效日按当日收盘价换算虚拟持股数量；事件之间持股数不变，权重随价格漂移。
  · 权重和不足 1.0 的部分视为现金（不计息）。
  · 组合净值与基准（默认沪深300）都归一化到起点 1.0。
  · 第一版不计手续费（页面显式声明假设）；不做空、不融资。

_compute_nav 是纯函数（fixture 可测，不碰网络）；build_* 组合取数 + 计算 + 产 chart/metric。
数据源不可用时优雅降级。
"""

from __future__ import annotations

from typing import Any


def _align_prices(price_map: dict[str, dict[str, float]]) -> list[str]:
    """所有标的价格日期的交集，升序。price_map: {code: {date: close}}。"""
    if not price_map:
        return []
    common: set[str] | None = None
    for series in price_map.values():
        keys = set(series)
        common = keys if common is None else (common & keys)
    return sorted(common or set())


def compute_nav(
    events: list[dict[str, Any]],
    price_map: dict[str, dict[str, float]],
) -> tuple[list[str], list[float]]:
    """按调仓事件计算组合净值曲线（归一化起点 1.0）。纯函数。

    events: [{effective_on, weights: {code: w}}]，按 effective_on 升序。
    price_map: {code: {date: close}}。
    返回 (dates, nav)；数据不足返回 ([], [])。

    算法：在每个交易日，持有「最近一次生效的调仓」所定的虚拟持股数；调仓日按当日
    收盘价用当时组合市值 × 目标权重 / 价格重新换算持股数。现金部分（1-Σw）保持不变。
    """
    if not events:
        return [], []
    events = sorted(events, key=lambda e: e["effective_on"])
    dates = _align_prices(price_map)
    if len(dates) < 2:
        return [], []
    start = events[0]["effective_on"]
    dates = [d for d in dates if d >= start]
    if len(dates) < 2:
        return [], []

    init_value = 1.0
    shares: dict[str, float] = {}
    cash = init_value
    nav: list[float] = []
    ev_idx = 0

    for d in dates:
        # 应用所有生效日 <= d 且尚未应用的调仓事件
        while ev_idx < len(events) and events[ev_idx]["effective_on"] <= d:
            w = events[ev_idx]["weights"]
            # 当前市值（用当日价）
            mv = cash + sum(
                shares.get(c, 0.0) * price_map[c].get(d, 0.0) for c in shares
            )
            if ev_idx == 0:
                mv = init_value
            invested = 0.0
            shares = {}
            for code, weight in w.items():
                px = price_map.get(code, {}).get(d)
                if px and px > 0:
                    shares[code] = mv * weight / px
                    invested += mv * weight
            cash = mv - invested
            ev_idx += 1
        # 当日组合市值
        mv = cash + sum(shares.get(c, 0.0) * price_map[c].get(d, 0.0) for c in shares)
        nav.append(round(mv / init_value, 6))

    return dates, nav


def compute_benchmark_nav(
    dates: list[str], bench_prices: dict[str, float]
) -> list[float]:
    """基准归一化净值（对齐 dates 起点=1.0）。缺失日用前值填充。"""
    if not dates:
        return []
    aligned = [bench_prices.get(d) for d in dates]
    # 前向填充缺失
    filled: list[float] = []
    last = None
    for v in aligned:
        if v is not None and v > 0:
            last = v
        filled.append(last if last is not None else 0.0)
    base = next((v for v in filled if v > 0), 0.0)
    if base <= 0:
        return [1.0] * len(dates)
    return [round(v / base, 6) if v > 0 else 1.0 for v in filled]
