"""alpha.backtest —— 最小回测引擎（T39）。

信号 → 持仓 → 净值 → 指标（总收益 / 年化 / 最大回撤 / 夏普）。纯库，无框架依赖。
只做最小可用：单标的、全仓/空仓（信号 1/0）、按收盘价、无手续费/滑点（可后续扩展）。

不做实盘/下单/择时建议（合规底线）。这是研究工具，产出客观指标与净值曲线。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

_TRADING_DAYS = 252


@dataclass
class BacktestResult:
    dates: list[str]
    equity: list[float]          # 策略净值曲线（起始 1.0）
    drawdown: list[float]        # 各时点回撤（<=0）
    positions: list[int]         # 每日持仓（0/1）
    metrics: dict[str, float] = field(default_factory=dict)


def ma(values: list[float], window: int) -> list[float | None]:
    """简单移动平均。前 window-1 个为 None。"""
    out: list[float | None] = []
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= window:
            s -= values[i - window]
        out.append(s / window if i >= window - 1 else None)
    return out


def golden_cross_signal(closes: list[float], fast: int, slow: int) -> list[int]:
    """双均线金叉信号：fast 上穿 slow → 持仓 1，否则 0（死叉后空仓）。

    参数：closes 收盘价序列；fast/slow 快慢均线窗口（如 20/60）。
    返回：与 closes 等长的 0/1 持仓信号（slow-1 之前无信号，记 0）。
    """
    fast_ma = ma(closes, fast)
    slow_ma = ma(closes, slow)
    sig: list[int] = []
    for i in range(len(closes)):
        f, s = fast_ma[i], slow_ma[i]
        if f is None or s is None:
            sig.append(0)
        else:
            sig.append(1 if f >= s else 0)
    return sig


def run(
    closes: list[float],
    signal: list[int],
    *,
    dates: list[str] | None = None,
    risk_free: float = 0.0,
) -> BacktestResult:
    """回测：按信号次日持仓（避免未来函数），按收盘价计日收益，产净值与指标。

    参数：
      closes: 收盘价序列。
      signal: 与 closes 等长的 0/1 持仓信号（当日收盘确定，次日生效）。
      dates:  可选日期标签（与 closes 等长）；缺省用序号。
      risk_free: 年化无风险利率（夏普用），默认 0。
    返回：BacktestResult（equity 起始 1.0；metrics 含 total_return/annual_return/
      max_drawdown/sharpe/trade_count）。

    约定：position[t] = signal[t-1]（次日生效，无未来函数）；日收益 = position[t] *
    (closes[t]/closes[t-1]-1)；无手续费/滑点。
    """
    n = len(closes)
    if n < 2 or len(signal) != n:
        raise ValueError("closes 与 signal 长度须一致且 >= 2")

    dates = dates or [str(i) for i in range(n)]
    positions = [0] * n
    for t in range(1, n):
        positions[t] = 1 if signal[t - 1] == 1 else 0

    equity = [1.0] * n
    daily_returns: list[float] = [0.0]
    trade_count = 0
    for t in range(1, n):
        r = (closes[t] / closes[t - 1] - 1.0) * positions[t]
        daily_returns.append(r)
        equity[t] = equity[t - 1] * (1.0 + r)
        if positions[t] != positions[t - 1]:
            trade_count += 1

    # 回撤：相对历史峰值。
    drawdown = [0.0] * n
    peak = equity[0]
    for t in range(n):
        peak = max(peak, equity[t])
        drawdown[t] = equity[t] / peak - 1.0

    total_return = equity[-1] - 1.0
    years = max((n - 1) / _TRADING_DAYS, 1e-9)
    annual_return = (equity[-1]) ** (1.0 / years) - 1.0 if equity[-1] > 0 else -1.0
    max_drawdown = min(drawdown)

    # 夏普：日超额收益均值/标准差 * sqrt(252)。
    rf_daily = risk_free / _TRADING_DAYS
    excess = [r - rf_daily for r in daily_returns[1:]]
    if len(excess) >= 2:
        mean = sum(excess) / len(excess)
        var = sum((x - mean) ** 2 for x in excess) / (len(excess) - 1)
        std = math.sqrt(var)
        sharpe = (mean / std) * math.sqrt(_TRADING_DAYS) if std > 1e-12 else 0.0
    else:
        sharpe = 0.0

    return BacktestResult(
        dates=dates,
        equity=equity,
        drawdown=drawdown,
        positions=positions,
        metrics={
            "total_return": round(total_return, 6),
            "annual_return": round(annual_return, 6),
            "max_drawdown": round(max_drawdown, 6),
            "sharpe": round(sharpe, 6),
            "trade_count": trade_count,
        },
    )


def backtest_golden_cross(
    closes: list[float],
    *,
    fast: int = 20,
    slow: int = 60,
    dates: list[str] | None = None,
) -> BacktestResult:
    """便捷：对收盘价序列跑 fast/slow 金叉策略（如 20/60），返回回测结果。"""
    sig = golden_cross_signal(closes, fast, slow)
    return run(closes, sig, dates=dates)
