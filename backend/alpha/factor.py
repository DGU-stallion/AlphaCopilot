"""alpha.factor —— 相关性分析因子（T43，ADR-0007 承诺 A/B）。

三个经 registry 白名单登记的纯函数，前端「相关性分析」页按 analysis_ref.fn 调用：
  correlation.overlay  归一化叠加走势（多标的对齐起点=100 看相对强弱）
  correlation.matrix   日收益率皮尔逊相关矩阵热力图
  correlation.rolling  前两标的滚动窗口收益率相关折线

关键正确性（金融口径，非可选）：
  · 相关必须基于【日收益率】而非价格——价格非平稳，直接算价格相关会产生伪高相关。
  · 多标的必须按【日期对齐取交集】——停牌/跨市场交易日历不齐，错位对齐会算出垃圾。
  · 叠加走势必须【归一化】到同一起点（100），不同价位标的才可比。

取数经 alpha.data.closes_with_dates（带日期，供对齐）；画图经 alpha.chart。
纯库无框架依赖；相关/收益率用纯 Python 实现（不引 pandas/numpy）。
"""

from __future__ import annotations

import math

from alpha import chart, data
from alpha.registry import ParamSpec, register

# 参数名 range 会遮蔽内建 range —— 在遮蔽前保存别名，函数内部用它做序号迭代。
_seq = range

# 供单元测试读取的「最近一次相关矩阵」诊断钩子（不参与业务逻辑）。
_corr_matrix_values: list[list[float]] = []

_MAX_SYMBOLS = 8


# ---------------------------------------------------------------------------
# 纯计算 helper
# ---------------------------------------------------------------------------

def _pct_change(values: list[float]) -> list[float]:
    """日收益率序列：r[t] = v[t]/v[t-1] - 1。长度 = len(values)-1。"""
    out: list[float] = []
    for i in range(1, len(values)):
        prev = values[i - 1]
        out.append(values[i] / prev - 1.0 if prev else 0.0)
    return out


def _pearson(a: list[float], b: list[float]) -> float:
    """皮尔逊相关系数。等长序列，标准差为 0 时返回 0。"""
    n = len(a)
    if n == 0 or n != len(b):
        return 0.0
    ma = sum(a) / n
    mb = sum(b) / n
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    denom = math.sqrt(va * vb)
    if denom < 1e-12:
        return 0.0
    return cov / denom


def _align(series: list[list[tuple[str, float]]]) -> tuple[list[str], list[list[float]]]:
    """多标的按日期对齐取交集。

    输入：每个标的的 (date, close) 列表。
    返回：(共同日期升序, 各标的对齐后的收盘价列表)。停牌缺日的标的自然被交集裁掉。
    """
    if not series:
        return [], []
    maps = [dict(s) for s in series]
    common = set(maps[0])
    for m in maps[1:]:
        common &= set(m)
    dates = sorted(common)
    cols = [[m[d] for d in dates] for m in maps]
    return dates, cols


def _normalize_100(values: list[float]) -> list[float]:
    """归一化到起点 100（相对走势）。首值为 0 时原样返回。"""
    if not values or not values[0]:
        return list(values)
    base = values[0]
    return [round(v / base * 100.0, 4) for v in values]


def _fetch(symbols: list[str], range: str) -> list[list[tuple[str, float]]]:
    """按标的取带日期收盘价。range 目前只作根数上的粗粒度映射（区间语义在 data 层演进）。"""
    count = {"3m": 63, "6m": 126, "1y": 250}.get(range, 250)
    return [data.closes_with_dates(code, count=count) for code in symbols]


# ---------------------------------------------------------------------------
# 注册的分析函数
# ---------------------------------------------------------------------------

@register(
    "correlation.overlay",
    params=[
        ParamSpec("symbols", "symbol_list", default=["600519", "000858"], max_len=_MAX_SYMBOLS),
        ParamSpec("range", "date_range", default="1y"),
    ],
)
def correlation_overlay(symbols: list[str], range: str) -> dict:
    """归一化叠加走势图（起点=100），返回 ECharts line option。

    对齐日期交集后各标的除以自身首值×100，同图叠加看相对强弱。
    """
    dates, cols = _align(_fetch(symbols, range))
    series = {code: _normalize_100(col) for code, col in zip(symbols, cols, strict=True)}
    return chart.line(dates, series, title="归一化叠加走势（起点=100）")


@register(
    "correlation.matrix",
    params=[
        ParamSpec("symbols", "symbol_list", default=["600519", "000858"], max_len=_MAX_SYMBOLS),
        ParamSpec("range", "date_range", default="1y"),
    ],
)
def correlation_matrix(symbols: list[str], range: str) -> dict:
    """日收益率皮尔逊相关矩阵热力图，返回 ECharts heatmap option。

    对齐 → 转日收益率（pct_change）→ 两两皮尔逊。基于收益率而非价格（避免伪相关）。
    """
    _dates, cols = _align(_fetch(symbols, range))
    rets = [_pct_change(col) for col in cols]
    n = len(symbols)
    matrix = [[_pearson(rets[i], rets[j]) for j in _seq(n)] for i in _seq(n)]
    _corr_matrix_values.clear()
    _corr_matrix_values.extend([row[:] for row in matrix])
    return chart.heatmap(list(symbols), matrix, title="日收益率相关矩阵")


@register(
    "correlation.rolling",
    params=[
        ParamSpec("symbols", "symbol_list", default=["600519", "000858"], max_len=_MAX_SYMBOLS),
        ParamSpec("window", "int", default=60, min=2, max=250),
        ParamSpec("range", "date_range", default="1y"),
    ],
)
def correlation_rolling(symbols: list[str], window: int, range: str) -> dict:
    """前两标的滚动 window 日收益率相关折线，返回 ECharts line option。

    对齐 → 收益率 → 滑动窗口逐点算皮尔逊。用于观察相关性随时间变化（非恒定）。
    """
    if len(symbols) < 2:
        raise ValueError("correlation.rolling 需要至少 2 个标的")
    dates, cols = _align(_fetch(symbols[:2], range))
    ra = _pct_change(cols[0])
    rb = _pct_change(cols[1])
    # 收益率对应的日期（丢掉首日）
    ret_dates = dates[1:]
    rolling: list[float] = []
    x: list[str] = []
    for end in _seq(window, len(ra) + 1):
        seg_a = ra[end - window:end]
        seg_b = rb[end - window:end]
        rolling.append(round(_pearson(seg_a, seg_b), 4))
        x.append(ret_dates[end - 1])
    label = f"{symbols[0]}~{symbols[1]} 滚动{window}日相关"
    return chart.line(x, {label: rolling}, title=f"滚动 {window} 日收益率相关")


def range_iter(window: int, length: int):
    """滚动窗口右端点序列 [window, length]，闭区间右端。"""
    return range(window, length + 1)
