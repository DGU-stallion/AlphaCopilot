"""alpha.factor_lab —— 因子实验室（M4-1）：IC / RankIC / ICIR / 衰减 / 分层 / 换手。

纯计算层：只用标准库，不 import 框架，不读 env。输入是普通 list / dict，
截面（cross-section）= 同一天里「股票 → 值」的映射。

════════ 设计约定（测试锁定，改动需同步改测试）════════

1. **缺失值：按股票 pairwise 丢弃，不弃整日。**
   factor 或 return 任一侧为 None / NaN / inf 的那只股票整只丢掉，其余股票照常配对。
   后果：个别股票停牌/缺数据不会让整个交易日的 IC 消失（弃整日会把一整个截面
   清空，IC 序列出现大片空洞）；代价是各日参与计算的股票集合不同（样本数 n 会漂），
   所以 IC 序列里的点样本量不严格一致。截面剩余 < 2 只 → 该日没有 IC。

2. **无 IC 的日子在序列里「跳过」，不填 0。**
   ic()/rank_ic() 这类单截面函数在样本不足/全缺失时返回 0.0（给前端安全值）；
   但 ic_series/decay 会跳过这种日子——否则「没数据」会被画成「IC=0」。
   截面内某一侧全部相同（方差为 0）时相关系数数学上无定义，返回 0.0
   （「无线性关系」），该日仍计入序列。

3. **icir：std=0 / 样本 < 2 → 返回 0.0（不是 NaN/inf）。**
   IC 序列全相同时 std=0，除零会得到 inf/NaN；前端把 0.0 解读为「无证据」。
   std 用**样本标准差（ddof=1）**——ICIR 衡量的是从有限期 IC 样本推断因子稳定性，
   样本标准差无偏；population(ddof=0) 会系统性高估 ICIR（短序列尤甚）。

4. **分位：q=1 为最低因子值，q=q 为最高。** 桶号 = floor(i*q/n)（i 为升序名次），
   因子值并列时按输入顺序稳定打破。样本不足 q 只时只返回**非空桶**；
   空桶不造 0 收益（0 会伪装成「这层赚了 0%」）。

5. **decay：period=N 取 N 日前瞻（forward）复合收益。**
   t 日因子 vs (t, t+N] 的收益 prod(1+r)-1，逐日横截面取 IC 后求均值。
   绝不能用当日收益（那是未来函数反过来：用 t 日因子去解释 t 日已发生的收益）。
   前瞻数据不足的 period（日期窗口走不到）不出现在结果里。
   日期顺序按字符串升序（ISO 日期字符串天然有序）；日线收益 ret_by_date[d]
   指「d-1 → d」的收益。

6. **turnover：相邻两期，在两期都有的股票里，所属分位发生变化的比例**，各期对求平均。
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from alpha import chart, data
from alpha.registry import ParamSpec, register

DEFAULT_PERIODS = (1, 5, 10, 20)
_METHODS = ("pearson", "spearman")


# ── 基础工具 ─────────────────────────────────────────────────────────

def _clean(v: Any) -> float | None:
    """有限数 → float；None/NaN/inf/非数值 → None。"""
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _pairs(factor: Sequence[Any], ret: Sequence[Any]) -> tuple[list[float], list[float]]:
    """股票级 pairwise 丢弃：任一侧缺失则整只丢掉。"""
    xs: list[float] = []
    ys: list[float] = []
    for a, b in zip(factor, ret, strict=False):
        x, y = _clean(a), _clean(b)
        if x is None or y is None:
            continue
        xs.append(x)
        ys.append(y)
    return xs, ys


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _sample_std(xs: Sequence[float]) -> float:
    """样本标准差（ddof=1）；n<2 或各值相同 → 0.0。"""
    n = len(xs)
    if n < 2 or max(xs) - min(xs) < 1e-12:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    """皮尔逊相关。调用方保证 n>=2 且等长。任一侧常数 → 0.0。"""
    if max(xs) == min(xs) or max(ys) == min(ys):
        return 0.0
    mx, my = _mean(xs), _mean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    r = sxy / math.sqrt(sxx * syy)
    return max(-1.0, min(1.0, r))


def _ranks(xs: Sequence[float]) -> list[float]:
    """平均位次（midrank，1 起）：并列值取所占位次的平均。"""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        mid = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[order[k]] = mid
        i = j + 1
    return out


def _ic_or_none(factor: Sequence[Any], ret: Sequence[Any], method: str) -> float | None:
    """单截面 IC；样本 < 2（pairwise 丢弃后）返回 None 表示「无 IC」。"""
    if method not in _METHODS:
        raise ValueError(f"未知 IC 方法 {method!r}（支持 {_METHODS}）")
    xs, ys = _pairs(factor, ret)
    if len(xs) < 2:
        return None
    if method == "spearman":
        xs, ys = _ranks(xs), _ranks(ys)
    return _pearson(xs, ys)


def _section_lists(f: Mapping[str, Any], r: Mapping[str, Any]) -> tuple[list[Any], list[Any]]:
    """两个截面 dict → 按共同代码（排序）对齐的两个 list。"""
    codes = sorted(set(f) & set(r))
    return [f[c] for c in codes], [r[c] for c in codes]


# ── 对外：单截面 ─────────────────────────────────────────────────────

def ic(factor: Sequence[Any], ret: Sequence[Any], method: str = "pearson") -> float:
    """单截面信息系数。样本不足/全缺失 → 0.0。method: pearson | spearman。

    IC vs RankIC 的区别：IC 对数值大小敏感，一个极端因子值（杠杆点）能把它拖走；
    RankIC 只看排序。例：因子 [1,2,3,100]、收益 [1,2,3,3]，IC≈0.54，RankIC≈0.92。
    """
    v = _ic_or_none(factor, ret, method)
    return 0.0 if v is None else v


def rank_ic(factor: Sequence[Any], ret: Sequence[Any]) -> float:
    """Spearman 秩相关（并列取平均位次）。"""
    return ic(factor, ret, method="spearman")


def icir(ics: Sequence[float]) -> float:
    """ICIR = mean(IC) / sample_std(IC)。std=0 或样本 < 2 → 0.0（见模块约定 3）。"""
    vals = [x for x in (_clean(v) for v in ics) if x is not None]
    if len(vals) < 2:
        return 0.0
    s = _sample_std(vals)
    if s == 0.0:
        return 0.0
    return _mean(vals) / s


def _buckets(values: Sequence[float], q: int) -> list[int]:
    """升序名次 → 桶号 floor(i*q/n)（0 起）。并列按输入顺序稳定打破。"""
    n = len(values)
    order = sorted(range(n), key=lambda i: (values[i], i))
    out = [0] * n
    for rank, idx in enumerate(order):
        out[idx] = rank * q // n
    return out


def quantile_returns(
    factor: Sequence[Any], ret: Sequence[Any], q: int = 5
) -> list[dict[str, Any]]:
    """单截面分层：返回非空桶的 [{quantile(1..q), mean_return, count}]，Q1=最低因子。"""
    if q < 1:
        raise ValueError("q 必须 >= 1")
    xs, ys = _pairs(factor, ret)
    if not xs:
        return []
    bk = _buckets(xs, q)
    sums = [0.0] * q
    cnt = [0] * q
    for b, y in zip(bk, ys, strict=True):
        sums[b] += y
        cnt[b] += 1
    return [
        {"quantile": b + 1, "mean_return": sums[b] / cnt[b], "count": cnt[b]}
        for b in range(q)
        if cnt[b]
    ]


# ── 对外：多日 ───────────────────────────────────────────────────────

def ic_series(
    factor_by_date: Mapping[str, Mapping[str, Any]],
    ret_by_date: Mapping[str, Mapping[str, Any]],
    window: int | None = None,
    method: str = "pearson",
) -> list[tuple[str, float]]:
    """逐日 IC 序列 [(date, ic)]，日期升序。

    ret_by_date[d] 必须已是与 factor_by_date[d] 配对的**前瞻收益**（调用方对齐，
    见 forward_returns）。无 IC 的日子跳过。window=k：滚动均值，
    只输出凑满 k 期的尾端点（不输出部分窗口，避免把小样本均值画成真低 IC）。
    """
    raw: list[tuple[str, float]] = []
    for d in sorted(set(factor_by_date) & set(ret_by_date)):
        xs, ys = _section_lists(factor_by_date[d], ret_by_date[d])
        v = _ic_or_none(xs, ys, method)
        if v is not None:
            raw.append((d, v))
    if window is None:
        return raw
    if window < 1:
        raise ValueError("window 必须 >= 1")
    return [
        (raw[i][0], _mean([v for _, v in raw[i - window + 1 : i + 1]]))
        for i in range(window - 1, len(raw))
    ]


def forward_returns(
    ret_by_date: Mapping[str, Mapping[str, Any]], period: int = 1
) -> dict[str, dict[str, float]]:
    """日线收益 → 前瞻 period 日复合收益：fwd[t][code] = prod(1+r[t+1..t+period]) - 1。

    t+1..t+period 取 ret_by_date 的日期升序序列（交易日历）。窗口内该股任何一天
    缺失 → 该股在 t 日无前瞻收益。走不到 period 天的日期不输出。
    """
    if period < 1:
        raise ValueError("period 必须 >= 1")
    dates = sorted(ret_by_date)
    out: dict[str, dict[str, float]] = {}
    for i in range(len(dates) - period):
        window = [ret_by_date[d] for d in dates[i + 1 : i + 1 + period]]
        sec: dict[str, float] = {}
        for code in set.intersection(*(set(w) for w in window)):
            growth = 1.0
            ok = True
            for w in window:
                r = _clean(w[code])
                if r is None:
                    ok = False
                    break
                growth *= 1.0 + r
            if ok:
                sec[code] = growth - 1.0
        out[dates[i]] = sec
    return out


def decay(
    factor_by_date: Mapping[str, Mapping[str, Any]],
    ret_by_date: Mapping[str, Mapping[str, Any]],
    periods: Sequence[int] = (1,) + DEFAULT_PERIODS[1:],
    method: str = "pearson",
) -> dict[int, float]:
    """IC 衰减：{period: 均值 IC}。ret_by_date 为**日线收益**，period=未来 N 日复合收益。

    没有任何有效截面的 period 不出现在结果里。
    """
    out: dict[int, float] = {}
    for n in periods:
        ics = [v for _, v in ic_series(factor_by_date, forward_returns(ret_by_date, n),
                                       method=method)]
        if ics:
            out[n] = _mean(ics)
    return out


def turnover(factor_by_date: Mapping[str, Mapping[str, Any]], q: int = 5) -> float:
    """分位换手率：相邻两期共同股票里所属分位变化的比例，均值。<2 期 → 0.0。"""
    if q < 1:
        raise ValueError("q 必须 >= 1")
    groups: list[dict[str, int]] = []
    for d in sorted(factor_by_date):
        sec = {c: x for c, v in factor_by_date[d].items() if (x := _clean(v)) is not None}
        if not sec:
            continue
        codes = sorted(sec)
        groups.append(dict(zip(codes, _buckets([sec[c] for c in codes], q), strict=True)))
    rates: list[float] = []
    for prev, cur in zip(groups, groups[1:], strict=False):
        common = set(prev) & set(cur)
        if common:
            rates.append(sum(prev[c] != cur[c] for c in common) / len(common))
    return _mean(rates)


def _mean_quantiles(
    factor_by_date: Mapping[str, Mapping[str, Any]],
    fwd_by_date: Mapping[str, Mapping[str, Any]],
    q: int,
) -> list[dict[str, Any]]:
    """各日分层收益的逐日均值（按分位聚合）。count 为各日样本数之和。"""
    acc: dict[int, list[float]] = {}
    cnt: dict[int, int] = {}
    for d in sorted(set(factor_by_date) & set(fwd_by_date)):
        xs, ys = _section_lists(factor_by_date[d], fwd_by_date[d])
        for row in quantile_returns(xs, ys, q):
            acc.setdefault(row["quantile"], []).append(row["mean_return"])
            cnt[row["quantile"]] = cnt.get(row["quantile"], 0) + row["count"]
    return [
        {"quantile": k, "mean_return": _mean(acc[k]), "count": cnt[k]} for k in sorted(acc)
    ]


def report(
    factor_by_date: Mapping[str, Mapping[str, Any]],
    ret_by_date: Mapping[str, Mapping[str, Any]],
    q: int = 5,
    periods: Sequence[int] = DEFAULT_PERIODS,
    daily_ret_by_date: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """因子体检汇总。

    ret_by_date：与因子配对的前瞻收益（ic_series / 分层 用）。
    daily_ret_by_date：日线收益，仅 decay 需要；不给则 decay = {}。
    所有浮点 round 到 6 位。
    """
    r6 = lambda x: round(x, 6)  # noqa: E731
    ic_s = ic_series(factor_by_date, ret_by_date)
    ric_s = ic_series(factor_by_date, ret_by_date, method="spearman")
    ics = [v for _, v in ic_s]
    rics = [v for _, v in ric_s]
    dec = decay(factor_by_date, daily_ret_by_date, periods) if daily_ret_by_date else {}
    qr = _mean_quantiles(factor_by_date, ret_by_date, q)
    return {
        "n_dates": len(ics),
        "ic_mean": r6(_mean(ics)),
        "ic_std": r6(_sample_std(ics)),
        "ic_ir": r6(icir(ics)),
        "rank_ic_mean": r6(_mean(rics)),
        "rank_ic_ir": r6(icir(rics)),
        "ic_series": [(d, r6(v)) for d, v in ic_s],
        "rank_ic_series": [(d, r6(v)) for d, v in ric_s],
        "decay": {n: r6(v) for n, v in dec.items()},
        "turnover": r6(turnover(factor_by_date, q)),
        "quantile_returns": [
            {**row, "mean_return": r6(row["mean_return"])} for row in qr
        ],
    }


# ── 数据管线 + 注册的图表 fn ─────────────────────────────────────────

_RANGE_COUNT = {"3m": 63, "6m": 126, "1y": 250}
_Q = 5
_rng = range  # 注册 fn 的参数名 range 会遮蔽内建


def _load(symbols: list[str], momentum: int, range: str):
    """取价 → 动量因子 / 日线收益 / 前瞻 1 日收益。数据缺失返回 None。

    因子 = close[t]/close[t-momentum] - 1（只用 t 及以前，无未来函数）。
    """
    factor: dict[str, dict[str, float]] = {}
    daily: dict[str, dict[str, float]] = {}
    for code in symbols:
        rows = data.closes_for_range(code, range)
        for i, (d, c) in enumerate(rows):
            if i >= 1 and rows[i - 1][1]:
                daily.setdefault(d, {})[code] = c / rows[i - 1][1] - 1.0
            if i >= momentum and rows[i - momentum][1]:
                factor.setdefault(d, {})[code] = c / rows[i - momentum][1] - 1.0
    if not factor or not daily:
        return None
    return factor, daily, forward_returns(daily, 1)


_PARAMS = [
    ParamSpec("symbols", "symbol_list",
              default=["600519", "000858", "000568", "002304", "600036", "601318"],
              max_len=30, label="股票池"),
    ParamSpec("momentum", "int", default=20, min=2, max=120, label="动量窗口"),
    ParamSpec("range", "date_range", default="1y", label="区间"),
]


@register("factorlab.ic_series", params=_PARAMS)
def factorlab_ic_series(symbols: list[str], momentum: int = 20, range: str = "1y") -> dict:
    """动量因子逐日 IC / RankIC 时间序列（renderer=lwc）。"""
    loaded = _load(symbols, momentum, range)
    if loaded is None:
        return chart.line([], {"IC(pearson)": [], "RankIC": []}, title="因子 IC（数据暂不可用）")
    factor, _daily, fwd = loaded
    s_ic = ic_series(factor, fwd)
    s_ric = ic_series(factor, fwd, method="spearman")
    return chart.line(
        [d for d, _ in s_ic],
        {"IC(pearson)": [round(v, 6) for _, v in s_ic],
         "RankIC": [round(v, 6) for _, v in s_ric]},
        title=f"动量({momentum}日)因子 IC",
    )


@register("factorlab.ic_decay", params=_PARAMS)
def factorlab_ic_decay(symbols: list[str], momentum: int = 20, range: str = "1y") -> dict:
    """IC 衰减曲线：横轴为前瞻期限 t+N（不是日期，故不走 LWC 的 time 语义）。"""
    loaded = _load(symbols, momentum, range)
    labels = [f"t+{n}" for n in DEFAULT_PERIODS]
    if loaded is None:
        return chart.line(labels, {"IC": [None] * len(labels)}, title="IC 衰减（数据暂不可用）")
    factor, daily, _fwd = loaded
    dec = decay(factor, daily, DEFAULT_PERIODS)
    return chart.line(
        labels,
        {"IC": [round(dec[n], 6) if n in dec else None for n in DEFAULT_PERIODS]},
        title=f"动量({momentum}日)因子 IC 衰减",
    )


@register("factorlab.quantile_returns", params=_PARAMS)
def factorlab_quantile_returns(symbols: list[str], momentum: int = 20,
                               range: str = "1y") -> dict:
    """分层平均次日收益柱状图（Q1 最低因子 … Q5 最高）。无样本的分位为空（None）。"""
    labels = [f"Q{i}" for i in _rng(1, _Q + 1)]
    loaded = _load(symbols, momentum, range)
    if loaded is None:
        return chart.bar(labels, {"平均收益(%)": [None] * _Q}, title="分层收益（数据暂不可用）")
    factor, _daily, fwd = loaded
    by_q = {r["quantile"]: r["mean_return"] for r in _mean_quantiles(factor, fwd, _Q)}
    return chart.bar(
        labels,
        {"平均收益(%)": [round(by_q[i] * 100, 4) if i in by_q else None
                         for i in _rng(1, _Q + 1)]},
        title=f"动量({momentum}日)因子分层次日收益",
    )


@register("factorlab.quantile_heatmap", params=_PARAMS)
def factorlab_quantile_heatmap(symbols: list[str], momentum: int = 20,
                               range: str = "1y") -> dict:
    """分层收益热力图：x=月份，y=Q1..Q5，值=该月各日分层次日收益均值(%)。"""
    labels = [f"Q{i}" for i in _rng(1, _Q + 1)]
    loaded = _load(symbols, momentum, range)
    months: dict[str, dict[int, list[float]]] = {}
    if loaded is not None:
        factor, _daily, fwd = loaded
        for d in sorted(set(factor) & set(fwd)):
            xs, ys = _section_lists(factor[d], fwd[d])
            for row in quantile_returns(xs, ys, _Q):
                months.setdefault(d[:7], {}).setdefault(row["quantile"], []).append(
                    row["mean_return"])
    month_labels = sorted(months)
    cells = [
        [mi, qi - 1, round(_mean(months[m][qi]) * 100, 4)]
        for mi, m in enumerate(month_labels)
        for qi in _rng(1, _Q + 1)
        if qi in months[m]
    ]
    vals = [c[2] for c in cells]
    bound = max((abs(v) for v in vals), default=1.0) or 1.0
    title = "分层收益热力图" if loaded is not None else "分层收益热力图（数据暂不可用）"
    return chart.validate_option({
        "title": {"text": title},
        "tooltip": {"trigger": "item"},
        "grid": {"left": 60, "right": 24, "top": 48, "bottom": 80, "containLabel": True},
        "xAxis": {"type": "category", "data": month_labels, "splitArea": {"show": True}},
        "yAxis": {"type": "category", "data": labels, "splitArea": {"show": True}},
        "visualMap": {"min": -bound, "max": bound, "calculable": True,
                      "orient": "horizontal", "left": "center", "bottom": 16},
        "series": [{"name": "次日收益(%)", "type": "heatmap", "data": cells,
                    "label": {"show": True}}],
    })
