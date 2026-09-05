"""alpha.backtest_engine —— A 股确定性回测引擎（S4）。

规则移植自 Vibe-Research/backtest（engines/china_a.py，MIT，上游移植 HKUDS/Vibe-Trading）：
  · T+1：当日买入不可当日卖出
  · 不可做空（散户）
  · 涨跌停按板块：主板 ±10% / 创业板科创 ±20% / 北交所 ±30%（ST 未从代码识别，简化）
  · 最小 100 股整手（买入向下取整到手）
  · 费用：佣金万2.5 起 ¥5 + 过户费万0.1 双边 + 印花税万5 仅卖出
  · 无未来函数：信号次日按开盘价成交；涨跌停用**前收**判定（非当日收盘）

与上游差异（有意）：
  · 用纯 Python + 项目自己的收盘价序列（alpha.data），不引 pandas/numpy 进核心循环，
    保持轻量可 fixture 测试；不搬 crypto/futures/forex/options 等域外引擎。
  · 单标的择时策略（信号序列）——多标的组合回测在「模拟组合」页覆盖。

gate（回测前闸口）：数据不足/信号非法先拒，不跑出"看着正常其实是错"的回测。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

_TRADING_DAYS = 252

# 费用常量（移植自 china_a.py）
_COMMISSION_RATE = 0.00025
_COMMISSION_MIN = 5.0
_STAMP_TAX = 0.0005
_TRANSFER_FEE = 0.00001


def price_limit(code: str) -> float:
    """按板块返回涨跌停幅度（移植 _price_limit）。code 为 6 位或带后缀。"""
    c = code.split(".")[0] if "." in code else code
    if c.startswith("300") or c.startswith("688"):
        return 0.20
    if c.startswith("8") and len(c) == 6:
        return 0.30
    return 0.10


def buy_cost(notional: float) -> float:
    """买入费用：佣金（万2.5 起 ¥5）+ 过户费（万0.1）。"""
    return max(notional * _COMMISSION_RATE, _COMMISSION_MIN) + notional * _TRANSFER_FEE


def sell_cost(notional: float) -> float:
    """卖出费用：佣金 + 过户费 + 印花税（万5，仅卖出）。"""
    return (
        max(notional * _COMMISSION_RATE, _COMMISSION_MIN)
        + notional * _TRANSFER_FEE
        + notional * _STAMP_TAX
    )


def round_lot(shares: float) -> int:
    """向下取整到 100 股整手。"""
    return max(int(shares // 100) * 100, 0)


@dataclass
class BacktestResult:
    dates: list[str]
    equity: list[float]        # 净值曲线（起始 1.0）
    drawdown: list[float]      # 各时点回撤 (<=0)
    positions: list[int]       # 每日持仓股数
    trades: int
    metrics: dict[str, float] = field(default_factory=dict)


def gate(closes: list[float], signal: list[int], dates: list[str] | None) -> str | None:
    """回测前闸口：返回拒绝原因字符串；None 表示可跑。

    拒绝条件（宁拒不糊弄）：
      · 收盘价不足 2 根 → 无法算收益
      · 信号与收盘价长度不一致
      · dates 提供但长度不一致
      · 收盘价含非正数（停牌/脏数据）
    """
    if len(closes) < 2:
        return f"收盘价不足（{len(closes)} 根 < 2），无法回测"
    if len(signal) != len(closes):
        return f"信号长度 {len(signal)} 与收盘价 {len(closes)} 不一致"
    if dates is not None and len(dates) != len(closes):
        return f"日期长度 {len(dates)} 与收盘价 {len(closes)} 不一致"
    if any(c <= 0 for c in closes):
        return "收盘价含非正数（停牌或脏数据）"
    return None


def run(
    code: str,
    closes: list[float],
    signal: list[int],
    *,
    dates: list[str] | None = None,
    initial_cash: float = 1_000_000.0,
    risk_free: float = 0.0,
) -> BacktestResult:
    """A 股单标的择时回测。signal[t]==1 表示 t 收盘后想持有，次日开盘按 T+1 生效。

    忠于无未来函数：position 变化在信号次日按当日收盘价（近似开盘）成交并计费；
    涨跌停用前收判定，封板日不成交。返回净值/回撤/指标（含费用后）。

    抛 ValueError 若未过 gate（调用方应先调 gate 或捕获）。
    """
    reason = gate(closes, signal, dates)
    if reason:
        raise ValueError(reason)

    n = len(closes)
    dates = dates or [str(i) for i in range(n)]
    limit = price_limit(code)

    cash = initial_cash
    shares = 0
    entry_idx: int | None = None  # 建仓日索引（T+1 判定）
    positions = [0] * n
    equity_abs = [initial_cash] * n
    trades = 0

    for t in range(1, n):
        prev_close = closes[t - 1]
        px = closes[t]
        day_move = px / prev_close - 1.0 if prev_close else 0.0
        want = signal[t - 1]  # 次日生效（T+1，无未来函数）

        # 涨跌停封板：达到板则当日不成交（买卖都受限）
        locked_up = day_move >= limit - 1e-9
        locked_down = day_move <= -limit + 1e-9

        if want == 1 and shares == 0 and not locked_up:
            # 建仓：可用现金买入整手
            raw = cash / (px * (1 + _COMMISSION_RATE + _TRANSFER_FEE))
            lot = round_lot(raw)
            if lot > 0:
                notional = lot * px
                cost = buy_cost(notional)
                if notional + cost <= cash:
                    cash -= notional + cost
                    shares = lot
                    entry_idx = t
                    trades += 1
        elif want == 0 and shares > 0 and not locked_down:
            # 平仓：T+1（非建仓当日）才可卖
            if entry_idx is None or t > entry_idx:
                notional = shares * px
                cash += notional - sell_cost(notional)
                shares = 0
                entry_idx = None
                trades += 1

        positions[t] = shares
        equity_abs[t] = cash + shares * px

    equity = [e / initial_cash for e in equity_abs]

    # 回撤
    drawdown = [0.0] * n
    peak = equity[0]
    for t in range(n):
        peak = max(peak, equity[t])
        drawdown[t] = equity[t] / peak - 1.0

    # 日收益 → 指标
    daily = [0.0]
    for t in range(1, n):
        daily.append(equity[t] / equity[t - 1] - 1.0 if equity[t - 1] else 0.0)
    total_return = equity[-1] - 1.0
    years = max((n - 1) / _TRADING_DAYS, 1e-9)
    annual = equity[-1] ** (1.0 / years) - 1.0 if equity[-1] > 0 else -1.0
    max_dd = min(drawdown)
    rf_daily = risk_free / _TRADING_DAYS
    excess = [r - rf_daily for r in daily[1:]]
    if len(excess) >= 2:
        mean = sum(excess) / len(excess)
        var = sum((x - mean) ** 2 for x in excess) / (len(excess) - 1)
        std = math.sqrt(var)
        sharpe = (mean / std) * math.sqrt(_TRADING_DAYS) if std > 1e-12 else 0.0
    else:
        sharpe = 0.0

    return BacktestResult(
        dates=dates,
        equity=[round(e, 6) for e in equity],
        drawdown=[round(d, 6) for d in drawdown],
        positions=positions,
        trades=trades,
        metrics={
            "total_return": round(total_return, 6),
            "annual_return": round(annual, 6),
            "max_drawdown": round(max_dd, 6),
            "sharpe": round(sharpe, 6),
            "trade_count": trades,
        },
    )


def golden_cross_signal(closes: list[float], fast: int, slow: int) -> list[int]:
    """双均线金叉信号（复用自玩具引擎口径）：fast MA >= slow MA → 1，否则 0。"""
    def ma(vals: list[float], w: int) -> list[float | None]:
        out: list[float | None] = []
        s = 0.0
        for i, v in enumerate(vals):
            s += v
            if i >= w:
                s -= vals[i - w]
            out.append(s / w if i >= w - 1 else None)
        return out

    fm, sm = ma(closes, fast), ma(closes, slow)
    return [1 if (fm[i] is not None and sm[i] is not None and fm[i] >= sm[i]) else 0
            for i in range(len(closes))]
