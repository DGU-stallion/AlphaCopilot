"""策略归因（M4-5）：把一个总收益拆成可以单独评价的几块。

════════ 为什么需要归因 ════════

回测说「总收益 -16.88%」，但不告诉你这 -16.88% 是怎么来的：
买错了标的？择时错了？费用吃掉了？三者改进方向完全相反，
混在一起等于什么都没学到。

════════ 三条口径（测试锁死）════════

1. **可加性优先**：`timing + selection == total`，误差 < 1e-9。
   归因最典型的错误是每一项看起来都合理、加起来不等于总数。
   所以本模块的拆法从「可加」出发反推定义，而不是先定义再祈祷能加。

2. **择时 = 策略收益 − 全程满仓收益。**
   理由：把「策略实际做的」减去「一次都不卖会怎样」，差值只能来自
   「什么时候不在场」。全程满仓时差值恒为 0 —— 没有「选择不参与」
   这件事，就没有择时可言。
   剩下的「全程满仓收益」就是选股/选标的 + 市场 beta，即 selection。

3. **费用单独列、表达成占资金比例。**
   绝对金额无法跨策略比较（大资金 100 块手续费毫无意义）。
   费用不能混进策略收益：那会让「策略不行」与「交易太频繁」分不清。

════════ 这里不做什么 ════════

不做 Brinson 行业归因（需要行业分类数据，且单标的回测没有行业分解的基础）。
等有多标的组合 + 行业映射时再单独做，不要在这里硬塞一个需要外部数据的东西。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def _r6(x: float | None) -> float | None:
    return None if x is None else round(x, 6)


def buy_and_hold_return(equity: Sequence[float]) -> float | None:
    """区间总收益。起点 <= 0 时返回 None（无法算收益率，不能返回 inf）。"""
    if len(equity) < 2:
        return None
    first, last = equity[0], equity[-1]
    if first <= 0:
        return None
    return _r6(last / first - 1.0)


def exposure_split(
    equity: Sequence[float], *, positions: Sequence[float],
) -> dict[str, Any]:
    """在场/空仓的天数与收益贡献。

    「空仓日贡献恒为 0」是这里的定义基石：空仓那天权益不该动。
    如果它动了，说明 positions 与 equity 不同源 —— 那是调用方的问题，
    本函数不掩盖（in_market_return 会与总收益对不上，一眼可见）。
    """
    n = min(len(equity), len(positions))
    if n == 0:
        return {"in_market_days": 0, "out_market_days": 0, "in_market_return": None}

    in_days = sum(1 for i in range(n) if float(positions[i]) > 1e-9)
    out_days = n - in_days
    # 在场日的复合收益（只对 position > 0 的日子累乘）
    growth = 1.0
    for i in range(1, n):
        if float(positions[i]) > 1e-9 and equity[i - 1] > 0:
            growth *= equity[i] / equity[i - 1]
    return {
        "in_market_days": in_days,
        "out_market_days": out_days,
        "in_market_return": _r6(growth - 1.0),
    }


def trade_costs(trades: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """成交费用汇总。trades 里每笔要有 fee（没有按 0 算）。"""
    total = 0.0
    for t in trades:
        fee = t.get("fee")
        if isinstance(fee, (int, float)) and fee == fee:  # 排除 NaN
            total += float(fee)
    return {"total_fee": _r6(total) or 0.0, "n_trades": len(trades)}


def cost_drag(*, total_fee: float, capital: float) -> float | None:
    """费用耗损 = 总费用 / 资金。capital <= 0 时 None（不能除零）。"""
    if not (capital > 0):
        return None
    return _r6(total_fee / capital)


def timing_vs_selection(
    equity: Sequence[float], *, positions: Sequence[float],
    benchmark: Sequence[float] | None = None,
) -> dict[str, Any]:
    """择时 vs 选股（口径见模块 docstring 第 2 条）。

    total     —— 策略实际总收益
    full      —— 「一次都不卖」的收益。**必须有 benchmark（标的自身价格序列）**，
                 拿策略净值冒充满仓基准是假的：策略净值里已经含空仓，
                 用它当基准，差值恒为 0，于是「择时」永远显示 0 ——
                 那是个看起来漂亮、实际什么都没算的数。
    timing    —— total - full，只可能来自「什么时候不在场」
    selection —— 剩下的部分

    benchmark 缺失时：full / timing 都是 None，**不返回 0**。
    界面显示「—（缺基准）」，而不是一个假的 0。
    """
    total = buy_and_hold_return(equity)
    if total is None:
        return {"total": None, "full": None, "timing": None, "selection": None,
                "note": "样本不足，无法归因"}

    full = buy_and_hold_return(benchmark) if benchmark else None
    if full is None:
        return {
            "total": _r6(total),
            "full": None,
            "timing": None,
            "selection": None,
            "note": "缺标的基准序列（benchmark），无法拆分择时与选股",
        }

    timing = total - full
    # selection 用「满仓基准」而不是 total：选股能力是在满仓假设下衡量的，
    # 这样 timing + selection == total 成立（可加性由构造保证）。
    return {
        "total": _r6(total),
        "full": _r6(full),
        "timing": _r6(timing),
        "selection": _r6(full),
        "note": "",
    }
