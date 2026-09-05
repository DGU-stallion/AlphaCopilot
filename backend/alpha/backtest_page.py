"""alpha.backtest_page —— 回测页分析函数（S4）。

把 A 股回测引擎（alpha.backtest_engine）接到页面驱动引擎：参数（标的/快慢均线/区间）
→ 取收盘价（alpha.data，失败降级）→ gate → 逐 bar 回测 → 净值/回撤图 + 指标卡。

注册进 alpha.registry；回测页 spec 的 blocks 引用这些 fn。数据源不可用时优雅降级（空图/不可用卡）。
"""

from __future__ import annotations

from alpha import backtest_engine as be
from alpha import chart, data
from alpha.registry import ParamSpec, register

_RANGE_COUNT = {"3m": 63, "6m": 126, "1y": 250}


def _load(symbol: str, range: str) -> tuple[list[str], list[float]]:
    """取带日期收盘价。数据源不可用时返回 ([], [])。"""
    count = _RANGE_COUNT.get(range, 250)
    rows = data.closes_with_dates(symbol, count=count)
    dates = [d for d, _ in rows]
    closes = [c for _, c in rows]
    return dates, closes


def _run(symbol: str, fast: int, slow: int, range: str):
    """公共：取数 + gate + 回测。返回 (result, dates) 或 (None, reason)。"""
    dates, closes = _load(symbol, range)
    if len(closes) < 2:
        return None, "数据源暂不可用或历史不足"
    signal = be.golden_cross_signal(closes, fast, slow)
    reason = be.gate(closes, signal, dates)
    if reason:
        return None, reason
    return be.run(symbol, closes, signal, dates=dates), None


_PARAMS = [
    ParamSpec("symbol", "str", default="600519", label="标的"),
    ParamSpec("fast", "int", default=20, min=2, max=120, label="快线"),
    ParamSpec("slow", "int", default=60, min=3, max=250, label="慢线"),
    ParamSpec("range", "date_range", default="1y", label="区间"),
]


@register("backtest.equity", params=_PARAMS)
def backtest_equity(symbol: str, fast: int, slow: int, range: str) -> dict:
    """双均线金叉策略净值 vs 买入持有基准，返回 ECharts line option。

    净值扣 A 股费用（佣金/印花/过户）；无未来函数（信号次日成交、涨跌停按前收）。
    数据源不可用时返回空图 + 标题提示。
    """
    res, reason = _run(symbol, fast, slow, range)
    if res is None:
        return chart.line([], {"净值": []}, title=f"回测净值（{reason}）")
    # 买入持有基准（归一化）
    _dates, closes = _load(symbol, range)
    base0 = closes[0]
    benchmark = [round(c / base0, 6) for c in closes]
    return chart.line(
        res.dates,
        {f"{fast}/{slow}金叉策略": res.equity, "买入持有": benchmark},
        title=f"{symbol} 回测净值（{range}）",
    )


@register("backtest.drawdown", params=_PARAMS)
def backtest_drawdown(symbol: str, fast: int, slow: int, range: str) -> dict:
    """策略回撤曲线，返回 ECharts line option。数据源不可用时空图 + 提示。"""
    res, reason = _run(symbol, fast, slow, range)
    if res is None:
        return chart.line([], {"回撤": []}, title=f"回撤（{reason}）")
    dd_pct = [round(d * 100, 4) for d in res.drawdown]
    return chart.line(res.dates, {"回撤(%)": dd_pct}, title=f"{symbol} 回撤")


@register("backtest.metrics", params=_PARAMS)
def backtest_metrics(symbol: str, fast: int, slow: int, range: str) -> dict:
    """回测指标卡：总收益/年化/最大回撤/夏普/交易次数。返回 metric block payload。"""
    res, reason = _run(symbol, fast, slow, range)
    if res is None:
        return {"items": [{"label": "数据状态", "value": "暂不可用", "hint": reason,
                           "tone": "muted"}]}
    m = res.metrics
    return {
        "items": [
            {"label": "总收益", "value": f"{m['total_return'] * 100:.2f}%",
             "tone": "up" if m["total_return"] > 0 else "down"},
            {"label": "年化", "value": f"{m['annual_return'] * 100:.2f}%",
             "tone": "up" if m["annual_return"] > 0 else "down"},
            {"label": "最大回撤", "value": f"{m['max_drawdown'] * 100:.2f}%", "tone": "down"},
            {"label": "夏普", "value": f"{m['sharpe']:.2f}", "tone": "flat"},
            {"label": "交易次数", "value": m["trade_count"], "tone": "muted"},
        ]
    }
