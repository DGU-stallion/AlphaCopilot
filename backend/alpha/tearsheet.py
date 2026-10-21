"""alpha.tearsheet —— 回测 Tear Sheet 标准化（M4-2）。

回测跑完后给一份**结构化标准报告**（dict，不是 markdown 字符串），
让「这个策略行不行」一眼能看出来。参照 QuantStats 的 tear sheet 标准。
纯计算层：只用标准库，不 import 框架，不读 env，不碰数据源。

════════ 设计约定（口径锁定，测试锁死，改动需同步改测试）════════

1. **Sharpe 用样本标准差（ddof=1），日收益年化 ×√252。**
   与 alpha.backtest / alpha.backtest_engine 现有口径完全一致（一致性优先于
   个人偏好——同一产品里两个 Sharpe 数值不同是事故）。
   · ddof=1：Sharpe 衡量「从有限样本推断的风险调整收益」，样本 std 无偏；
     population（ddof=0）会系统性地把 Sharpe 抬高 √(n/(n-1))，短序列尤甚。
   · ×√252：输入是**日频**收益（252 个交易日/年），任何其他年化基数都要有
     业务理由；periods_per_year 参数显式暴露，谁换口径谁传参。
   · 无风险利率 = 0（下游指标口径一致，简化）；要加 rf 走 summary 之后再说。

2. **Sortino 的下行偏差：只把严格 < 0 的收益计入分子，零收益不算下行。**
   · 零收益（典型是空仓日）既没有「下到 MAR 之下」，也不该为策略积攒下行风险；
     QuantStats 的 MAR 口径同样只取 r < target。选「不含零」。
   · **分母用全样本 n（含零/空仓日），不是只数负收益的个数。**
     这是与 Morningstar 一致的 full-sample 口径：分母与波动率同构（都是除以 n），
     Sortino 与 Sharpe 才可比；空仓日摊大分母会压低下行偏差，这个「稀释」与
     Sharpe 对空仓日的稀释是同一件事，用 in_market_pct 统一暴露（见 5）。
   · 下行偏差 = 0（无任何负收益日）→ Sortino 返回 None，不是 inf——
     「没有下行情」时这个比值没有意义，前端显示「—」。

3. **年化收益只在样本 ≥ 252 个交易日时才有；不足一年 → None，绝不外推。**
   几何年化 = (equity[-1]/equity[0])^(252/n_days) - 1（与 backtest.py 同口径）。
   把 30 天的 +30% 外推成「年化 300%」是 tear sheet 里最经典的自欺。
   代价：Calmar（年化/最大回撤）在不足一年的样本里也为 None。波动率没有
   外推问题（√252 只是量纲换算，不复合），照常给。
   换手率照常年化（round trips / 年数）：频率估计不复合，短样本不误导。

4. **空仓期（权益一模不变的日子）对 Sharpe/Sortino 的假象是本模块最关心的坑。**
   机制：空仓日收益恰好 = 0，全部样本里混入这些 0 会**同时**稀释均值（拉向 0）
   和压缩标准差（更剧烈），净效果几乎总是**抬高 Sharpe**——一个只在 10% 的日子
   满仓吃了大肉、其余时间空仓的策略，全序列 Sharpe 看起来跟全天候满仓一样甚至
   更好。这不是修复不了，是不该混。
   处理（不假装能修复，只做三件事让假象显形）：
   · summary.in_market_pct：在场比例，第一眼先看它；
   · summary.sharpe_in_market：**只用在场日的收益**重算一遍 Sharpe（场内口径，
     与场外数字同公式）；全序列远高于场内 → 大概率是空仓稀释在帮忙；
   · report["notes"]：机器可读的提示字段——在场占比 < 100% 时生成一条 note，
     前端可以直接展示给用户，不许静默。
   场内 Sharpe 需要知道仓位：由 trades 参数还原（见 exposure 6）；给不出
   （trades=None）→ 两个字段为 None，不算数。

5. **月度矩阵：空仓月/无数据月 = None，绝不写 0。**
   0 会让人以为「那个月不赚不亏」；None 让前端渲染成格子留白。一个月内权益
   **一模不变**时同样给 None——现实里净值精确不变几乎只有空仓一种解释，
   给 0 的错误方向（伪装成「在场且持平」）比给 None（可能漏掉一个真·零收益月）
   保守得多。

6. **exposure：输入是逐日仓位居映射（0/1 或股数/权重 >0 视为在场）。**
   · in_market_pct = 在场日 / 全部日；
   · avg_holding_days = 连续在场段的平均长度（0 段不算）；
   · turnover = 建仓段数 / 年数（年数 = (n-1)/252；频率估计不复合，短样本照给——
     不是「把 30 天收益外推成年化」那类误导，见 3）；
   · 空序列 → 全 0（0.0/0.0/0.0），不崩。

7. **除零全域防守：std=0 → 0.0，downside=0 → Sortino None，maxdd=0 → Calmar None，**
   **无任何交易 → win_rate None。** 全部返回有限数或 None，绝不输出 inf/NaN——
   前端拿到 inf 会把色标炸掉；「没有风险」显成「—」比显示 inf 诚实。
8. **drawdown 深度是百分比小数（<= 0，-0.55 = 跌 55%），不是绝对值、不是已乘
   100 的「%」数。** 回撤是相对历史峰值的比值；同一段回撤的 days 数到修复前一日
   （含首日），current_days 只数当前还在水下的天数。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from alpha import chart, data
from alpha.registry import ParamSpec, register

# 函数参数名叫 range（page spec 的区间参数），会遮蔽内置 range()。
# 用别名解决，而不是改参数名 —— 参数名要与 ParamSpec("range") 对齐，
# 改了会让 page spec 的参数解析失效。
_range = range

_TRADING_DAYS = 252
_TOP_DRAWDOWNS = 5
_WINDOW = 60
_MONTHS = 12


# ── 基础工具（与 factor_lab 同约定的最小重复，保持本模块独立可测）────────

def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _sample_std(xs: Sequence[float]) -> float:
    """样本标准差（ddof=1）；n<2 或各值相同 → 0.0（空崩防线，不是统计真相）。"""
    n = len(xs)
    if n < 2 or max(xs) - min(xs) < 1e-15:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def _r6(x: float | None) -> float | None:
    return None if x is None else round(x, 6)


def daily_returns(equity: Sequence[float]) -> list[float]:
    """权益 → 逐日收益 [equity[t]/equity[t-1]-1]，长度 len(equity)-1。"""
    out: list[float] = []
    for t in range(1, len(equity)):
        base = equity[t - 1]
        out.append(equity[t] / base - 1.0 if base != 0.0 else 0.0)
    return out


def downside_deviation(
    returns: Sequence[float], periods_per_year: int = _TRADING_DAYS,
) -> float | None:
    """年化下行偏差（约定 2 的口径）：分子只累加严格 <0 的收益平方，分母全样本 n。

    无任何负收益 → 0.0（调用方决定要不要把 Sortino 显示成 None）。
    """
    n = len(returns)
    if n < 2:
        return None
    sq = sum(r * r for r in returns if r < 0.0)
    return math.sqrt(sq / n) * math.sqrt(periods_per_year)


# ── 对外：滚动序列 / 回撤 ─────────────────────────────────────────────

def rolling_sharpe(
    returns: Sequence[float],
    window: int = _WINDOW,
    periods_per_year: int = _TRADING_DAYS,
) -> list[float]:
    """滚动 Sharpe：只输出**凑满完整窗口**的尾端点（不画小样本尾巴）。

    每个点 = 前 window 个收益的 mean / 样本std × √PPY（口径 1）；std=0 的窗口
    给 0.0（约定 7）。返回长度 = max(len(returns) - window + 1, 0)。
    """
    if window < 2:
        raise ValueError("window 必须 >= 2")
    out: list[float] = []
    for i in range(window - 1, len(returns)):
        seg = returns[i - window + 1 : i + 1]
        s = _sample_std(seg)
        out.append(_mean(seg) / s * math.sqrt(periods_per_year) if s > 0.0 else 0.0)
    return out


def drawdown_series(equity: Sequence[float]) -> list[float]:
    """逐时点回撤（<= 0，相对历史峰值）。backtest.py 只在 run() 内联了同款逻辑
    且未导出函数，此处为正式实现；不去改冻结中的 backtest.py。"""
    if not equity:
        return []
    peak = equity[0]
    out: list[float] = []
    for v in equity:
        if v > peak:
            peak = v
        out.append(v / peak - 1.0 if peak > 0.0 else 0.0)
    return out


def drawdown_duration(equity: Sequence[float]) -> dict[str, Any]:
    """回撤 Episodes 起止与时长。

    Episode = 权益低于历史峰值的连续区间（含跌入首日与修复前一日）。
      episodes: [{start, end, days, depth}]（索引 0 起；days = end-start+1；
                depth = 该段最深的回撤，<= 0）
      max_days: 最长 Episode 的天数（无回撤 → 0）
      current_days: 若当前仍在水下 = 末点 − 最近一次回到峰值的索引（约定：
                dd==0 的日子算「回到峰值」，含触到旧高峰本人的日子）；
                否则 0
    """
    dd = drawdown_series(equity)
    episodes: list[dict[str, int]] = []
    cur: dict[str, int] | None = None
    for i, d in enumerate(dd):
        if d < -1e-12:
            if cur is None:
                cur = {"start": i, "end": i, "depth": d}
            else:
                cur["end"] = i
                cur["depth"] = min(cur["depth"], d)
        elif cur is not None:
            episodes.append(cur)
            cur = None
    if cur is not None:
        episodes.append(cur)
    out_eps = [
        {"start": e["start"], "end": e["end"], "days": e["end"] - e["start"] + 1,
         "depth": round(e["depth"], 6)}
        for e in episodes
    ]
    max_days = max((e["days"] for e in out_eps), default=0)
    below_water = bool(dd) and dd[-1] < -1e-12
    last_peak_idx = max((i for i, d in enumerate(dd) if d >= -1e-12), default=0)
    current_days = (len(dd) - 1 - last_peak_idx) if below_water else 0
    return {"episodes": out_eps, "max_days": max_days, "current_days": current_days}


# ── 对外：月度 / 在场 ─────────────────────────────────────────────────

def monthly_returns(dates: Sequence[str], equity: Sequence[float]) -> list[dict[str, Any]]:
    """月度收益矩阵 [{year, month, ret}]（calendar 全覆盖，None = 空仓月/无数据月）。

    · 覆盖 first–last 日期之间的**每个日历月**（有数据有值，没数据/持平 = None）；
    · 月收益 = 月末日 / 上月末日 - 1（首月以 equity[0] 为基）；
    · 月内权益**一模不变** → None（约定 5：宁可说「不在场」也不把 0 塞给人看）。
    """
    if len(dates) != len(equity) or not equity:
        return []

    def _ym(d: str) -> tuple[int, int] | None:
        """'YYYY-MM-…' → (year, month)；非日期标签（如序号）→ None（不满月报）。"""
        try:
            y, m = int(d[:4]), int(d[5:7])
        except ValueError:
            return None
        if not (1 <= m <= _MONTHS):
            return None
        return y, m

    yms = [_ym(d) for d in dates]
    if any(v is None for v in yms):
        return []                       # 有非 ISO 日期位（序号标签）→ 月报无意义，不给
    # 逐日按 (year, month) 聚合：记录每日索引
    by_month: dict[tuple[int, int], list[int]] = {}
    for i, d in enumerate(dates):
        y, m = int(d[:4]), int(d[5:7])
        by_month.setdefault((y, m), []).append(i)
    # 日历全覆盖：first–last 之间的每个月都吐一条（包括没有任何数据的月份）
    y0, m0 = int(dates[0][:4]), int(dates[0][5:7])
    y1, m1 = int(dates[-1][:4]), int(dates[-1][5:7])
    months: list[tuple[int, int]] = []
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        months.append((y, m))
        m += 1
        if m > _MONTHS:
            y, m = y + 1, 1
    out: list[dict[str, Any]] = []
    base = equity[0]                   # 首月基准
    for y, m in months:
        idxs = by_month.get((y, m))
        if not idxs:
            out.append({"year": y, "month": m, "ret": None})
            continue
        ret = equity[idxs[-1]] / base - 1.0
        # 全月持平 → None（约定 5）
        flat = all(equity[i] == base for i in idxs)
        out.append({"year": y, "month": m, "ret": None if flat else round(ret, 6)})
        base = equity[idxs[-1]]
    return out


def exposure(positions_or_signals: Sequence[float]) -> dict[str, float | int | None]:
    """在场统计（约定 6）。positions/signals 混用：>0 视为在场。

    turnover 年化为 round trips / 年 数（年数 = (len-1)/252，不足一年也照给，
    见约定 3 的理由：频率估计不复合）。空输入 → 全 0。"""
    flags = [1 if float(v) > 1e-9 else 0 for v in positions_or_signals]
    n = len(flags)
    if n == 0:
        return {"in_market_pct": 0.0, "avg_holding_days": 0.0, "turnover": 0.0}
    runs: list[int] = []
    cur = 0
    for f in flags:
        if f:
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
    if cur:
        runs.append(cur)
    years = max((n - 1) / _TRADING_DAYS, 1e-9)
    return {
        "in_market_pct": sum(flags) / n,
        "avg_holding_days": (_mean([float(r) for r in runs]) if runs else 0.0),
        "turnover": len(runs) / years,
    }


def _mask_from_trades(trades: Any, dates: Sequence[str]) -> list[int] | None:
    """trades → 逐日在场掩码；给不出（None/非 list/空）→ None 或全 0。

    · list[dict] 且含 entry/exit（日期须能命中 dates）→ 段标记；
    · list[int/float/bool] → 当作仓位居映射直接用；
    · 其它形状（int 计数等）→ None（不是在场信息）。
    """
    if trades is None:
        return None
    if not isinstance(trades, list):
        return None
    if not trades:
        return [0] * len(dates)
    if all(isinstance(t, dict) for t in trades):
        mask = [0] * len(dates)
        idx_of = {d: i for i, d in enumerate(dates)}
        for t in trades:
            a, b = t.get("entry"), t.get("exit")
            if a not in idx_of or b not in idx_of:
                continue  # 命不中就忽略这段（宁缺勿错画）
            i0, i1 = idx_of[a], idx_of[b]
            for i in range(min(i0, i1), max(i0, i1) + 1):
                mask[i] = 1
        return mask
    if all(isinstance(t, (int, float)) and not isinstance(t, bool) for t in trades):
        return [1 if float(v) > 1e-9 else 0 for v in trades]
    return None


# ── 对外：tear sheet ──────────────────────────────────────────────────

_EMPTY_SUMMARY: dict[str, Any] = {
    "total_return": 0.0,
    "annual_return": None,
    "annual_volatility": 0.0,
    "sharpe": 0.0,
    "sharpe_in_market": None,
    "sortino": None,
    "calmar": None,
    "max_drawdown": 0.0,
    "max_drawdown_days": 0,
    "current_drawdown_days": 0,
    "win_rate": None,
    "in_market_pct": None,
    "benchmark_total_return": None,
}


def _empty_report() -> dict[str, Any]:
    """空/单点输入的安全结构（约定 8）：形状完整、值全零/None，不崩。"""
    return {
        "summary": dict(_EMPTY_SUMMARY),
        "rolling_sharpe": [],
        "monthly": [],
        "drawdowns": [],
        "exposure": {"in_market_pct": 0.0, "avg_holding_days": 0.0, "turnover": 0.0},
        "notes": [
            "样本为空或不足 2 个交易日，无法构成 tear sheet；先跑一次有效回测。"
        ],
    }


def tear_sheet(
    dates: Sequence[str],
    equity: Sequence[float],
    *,
    benchmark_equity: Sequence[float] | None = None,
    trades: Any = None,
) -> dict[str, Any]:
    """标准化 tear sheet（约定 1–8；返回结构化 dict，不是 markdown）。

    参数：
      dates:            ISO 日期（升序），与 equity 等长
      equity:           策略净值曲线（任意正起点）
      benchmark_equity: 可选基准净值（用于基准总收益一行对照）
      trades:           可选在场信息：list[dict{entry,exit}] 或 0/1 仓位居映射；
                        给不出去掉在场字段（None），绝不猜

    返回 keys: summary / rolling_sharpe / monthly / drawdowns / exposure / notes。
    所有浮点 round 6。
    """
    if len(dates) != len(equity):
        raise ValueError("dates 与 equity 长度须一致")
    n = len(equity)
    if n and not equity[0] > 0:
        raise ValueError("equity 起点必须为正")
    if n < 2:
        return _empty_report()

    rets = daily_returns(equity)
    n_days = len(rets)
    base = equity[0]
    total_return = equity[-1] / base - 1.0

    # —— summary（口径见模块 docstring 1–5）——
    growth = equity[-1] / base
    annual_return = growth ** (_TRADING_DAYS / n_days) - 1.0 if n_days >= _TRADING_DAYS else None
    vol = _sample_std(rets)
    annual_vol = vol * math.sqrt(_TRADING_DAYS)
    mean_ex = _mean(rets)
    sharpe = (mean_ex / vol) * math.sqrt(_TRADING_DAYS) if (n_days >= 2 and vol > 0) else 0.0
    dd_dev = downside_deviation(rets)
    sortino = None if not dd_dev else (mean_ex / (dd_dev / math.sqrt(_TRADING_DAYS)))
    dd_ser = drawdown_series(equity)
    max_dd = min(dd_ser)
    dur = drawdown_duration(equity)
    calmar = None if (annual_return is None or abs(max_dd) < 1e-12) else annual_return / abs(max_dd)
    nonzero = [r for r in rets if abs(r) > 1e-12]
    win_rate = sum(1 for r in nonzero if r > 0) / len(nonzero) if nonzero else None

    # —— 空仓假象（约定 4）：在场掩码 → 场内 Sharpe ——
    mask = _mask_from_trades(trades, list(dates))
    sharpe_in_market: float | None = None
    if mask is not None:
        in_ret = [r for t, r in enumerate(rets, start=1) if mask[t] and abs(r) > 1e-12]
        if len(in_ret) >= 2:
            m = _mean(in_ret)
            s = _sample_std(in_ret)
            sharpe_in_market = (m / s) * math.sqrt(_TRADING_DAYS) if s > 0 else 0.0
    in_pct = (sum(mask) / n) if mask is not None else None

    bench_total = None
    if benchmark_equity is not None and len(benchmark_equity) >= 2 and benchmark_equity[0] > 0:
        bench_total = benchmark_equity[-1] / benchmark_equity[0] - 1.0

    # —— rolling_sharpe（完整窗口尾端点，对齐收益对应日期）——
    r_sharpe = rolling_sharpe(rets, _WINDOW)
    rolling_pairs: list[list[Any]] = []
    if r_sharpe:
        start = 1 + (_WINDOW - 1)               # rets[0] 对应 dates[1]
        rolling_pairs = [
            [dates[start + i], round(v, 6)] for i, v in enumerate(r_sharpe)
        ]

    # —— drawdowns：最深的前 N 段 ——
    top = sorted(dur["episodes"], key=lambda e: e["depth"])[:_TOP_DRAWDOWNS]

    notes: list[str] = []
    if in_pct is not None and in_pct < 1.0 - 1e-12:
        notes.append(
            f"该策略在场占比 {in_pct:.0%}：全序列 Sharpe/波动把空仓日的 0 收益也算了进去，"
            "会低估波动、抬高 Sharpe（空仓稀释）。判断择时质量请对照 "
            "summary.sharpe_in_market（仅在场日）。"
        )
    if annual_return is None:
        notes.append(
            f"样本仅 {n_days} 个交易日（不足一年），年化收益/Calmar 置 None 不外推。"
        )

    return {
        "summary": {
            "total_return": _r6(total_return),
            "annual_return": _r6(annual_return),
            "annual_volatility": _r6(annual_vol),
            "sharpe": _r6(sharpe),
            "sharpe_in_market": _r6(sharpe_in_market),
            "sortino": _r6(sortino),
            "calmar": _r6(calmar),
            "max_drawdown": _r6(max_dd),
            "max_drawdown_days": dur["max_days"],
            "current_drawdown_days": dur["current_days"],
            "win_rate": _r6(win_rate),
            "in_market_pct": _r6(in_pct),
            "benchmark_total_return": _r6(bench_total),
        },
        "rolling_sharpe": rolling_pairs,
        "monthly": monthly_returns(dates, equity),
        "drawdowns": top,
        "exposure": exposure(mask) if mask is not None else {
            "in_market_pct": None, "avg_holding_days": None, "turnover": None,
        },
        "notes": notes,
    }


# ── 注册图表 fn（机制同 factor_lab；数据源不可用时空图降级）───────────────

def _run_page(symbol: str, fast: int, slow: int, range: str):
    """复用 backtest_page 的页级管线（gate + A股回测引擎），失败返回 (None, reason)。"""
    from alpha.backtest_page import _run  # 局部 import 避免模块级耦合

    return _run(symbol, fast, slow, range)


_PARAMS: list[ParamSpec] = [
    ParamSpec("symbol", "str", default="600519", label="标的"),
    ParamSpec("fast", "int", default=20, min=2, max=120, label="快线"),
    ParamSpec("slow", "int", default=60, min=3, max=250, label="慢线"),
    ParamSpec("range", "date_range", default="1y", label="区间"),
]


@register("tearsheet.rolling_sharpe", params=_PARAMS)
def tearsheet_rolling_sharpe(symbol: str, fast: int = 20, slow: int = 60,
                             range: str = "1y") -> dict:
    """滚动 Sharpe（60 日窗口，完整窗口尾端点）时间序列，renderer=lwc。"""
    res, reason = _run_page(symbol, fast, slow, range)
    if res is None:
        return chart.line([], {"滚动Sharpe(60日)": []}, title=f"滚动 Sharpe（{reason}）")
    rets = daily_returns(res.equity)
    series = rolling_sharpe(rets, _WINDOW)
    tail = res.dates[_WINDOW:] if res.dates else []
    if not res.dates:
        tail = list(range(len(series)))          # 无日期时退化为序号
    vals = [round(v, 4) for v in series]
    if len(vals) != len(tail):                   # 防御：错宁可空图
        vals = [None] * len(tail)
    return chart.line(tail, {"滚动Sharpe(60日)": vals},
                      title=f"滚动 Sharpe（60日，{range}）")


@register("tearsheet.drawdown", params=_PARAMS)
def tearsheet_drawdown(symbol: str, fast: int = 20, slow: int = 60,
                       range: str = "1y") -> dict:
    """回撤曲线（%，相对历史峰值），renderer=lwc（与净值同金融时间语义）。"""
    res, reason = _run_page(symbol, fast, slow, range)
    if res is None:
        return chart.line([], {"回撤": []}, title=f"回撤（{reason}）")
    dd_pct = [round(d * 100, 4) for d in drawdown_series(res.equity)]
    name = data.names([symbol])[symbol]
    return chart.line(res.dates, {"回撤(%)": dd_pct}, title=f"{name} 回撤（tear sheet 口径）")


@register("tearsheet.monthly_heatmap", params=_PARAMS)
def tearsheet_monthly_heatmap(symbol: str, fast: int = 20, slow: int = 60,
                              range: str = "1y") -> dict:
    """月度收益热力图：x=年份，y=1–12 月，值=月收益(%)；空仓/无数据月留白。"""
    res, reason = _run_page(symbol, fast, slow, range)
    months = monthly_returns(res.dates, res.equity) if res is not None else []
    years = sorted({m["year"] for m in months if m["ret"] is not None})
    y_index = {y: i for i, y in enumerate(years)}
    cells = [
        [y_index[m["year"]], m["month"] - 1, round(m["ret"] * 100, 4)]
        for m in months
        if m["ret"] is not None and m["year"] in y_index
    ]
    vals = [c[2] for c in cells]
    bound = max((abs(v) for v in vals), default=1.0) or 1.0
    title = "月度收益热力图" if months else f"月度收益热力图（{reason or '数据暂不可用'}）"
    return chart.validate_option({
        "title": {"text": title},
        "tooltip": {"trigger": "item"},
        "grid": {"left": 60, "right": 24, "top": 48, "bottom": 80, "containLabel": True},
        "xAxis": {"type": "category", "data": [str(y) for y in years],
                  "splitArea": {"show": True}},
        "yAxis": {"type": "category", "data": [str(i) for i in _range(1, _MONTHS + 1)],
                  "splitArea": {"show": True}},
        "visualMap": {"min": -bound, "max": bound, "calculable": True,
                      "orient": "horizontal", "left": "center", "bottom": 16},
        "series": [{"name": "月收益(%)", "type": "heatmap", "data": cells,
                    "label": {"show": True}}],
    })
