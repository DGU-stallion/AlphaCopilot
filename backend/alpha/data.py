"""alpha.data —— 数据门面（T37）。

包住 research.* 纯函数，给 agent 一个稳定、少而精的取数 API。docstring 即 LLM schema：
agent 在不看源码的情况下靠这些 docstring 正确取到 K 线 / 行情 / 估值 / 全球 / 资讯。

设计（AGENTS 硬规则 5 精神）：门面零业务逻辑，只做「稳定签名 + 好文档 + 轻量整形」。
底层数据源（腾讯 gtimg / mootdx / akshare / 同花顺）缺失时按 research 层的既有行为降级。
"""

from __future__ import annotations

from typing import Any

from research import astock, gstock, newsradar

# K 线周期常量（对应 research.astock.kline 的 category）。
DAY = 4
WEEK = 5
MONTH = 6
MIN60 = 11


def kline(code: str, period: int = DAY, count: int = 60) -> list[dict[str, Any]]:
    """取个股 K 线（OHLC 序列）。

    参数：
      code:   6 位 A 股代码（如 '600519' 贵州茅台）。
      period: 周期，用本模块常量 DAY(日)/WEEK(周)/MONTH(月)/MIN60(60分钟)，默认日线。
      count:  取最近多少根，默认 60。
    返回：
      按时间升序的记录列表，每条含 open/high/low/close/vol 等字段（列名随数据源，
      通常有 'open'/'close'/'high'/'low'）。数据源不可用时返回空列表。

    用途：技术分析、均线/金叉、回测输入。回测请配合 alpha.backtest 使用。
    """
    return astock.kline(code, category=period, offset=count)


def quote(codes: list[str]) -> dict[str, dict[str, Any]]:
    """批量取 A 股实时行情快照。

    参数：codes 为 6 位代码列表（如 ['600519','000858']）。
    返回：{code: {name, price, change_pct, pe, pb, mktcap, ...}}。仅客观数据，不构成建议。
    """
    return astock.tencent_quote(codes)


def names(codes: list[str]) -> dict[str, str]:
    """批量取标的显示名称（代码 → 名称），供图表 series/轴标签用中文名而非代码。

    参数：codes 为 6 位代码列表（如 ['600519','000858']）。
    返回：{code: name}。复用 astock.tencent_quote 的 name 字段；某 code 取不到 name
    或整体请求异常时，该 code 回退为代码本身（不报错、不伪造名称）。
    """
    result: dict[str, str] = {c: c for c in codes}
    try:
        quotes = astock.tencent_quote(codes)
    except Exception:
        return result
    for code in codes:
        q = quotes.get(code)
        name = q.get("name") if q else None
        if name:
            result[code] = name
    return result


def valuation(code: str) -> dict[str, Any]:
    """取个股全量估值快照（PE/PB/PS 及其历史分位、同业对比、前向估值等）。

    参数：code 为 6 位 A 股代码。返回估值字段字典。用于「估值维度」分析。
    """
    return astock.full_valuation(code)


def index_quote() -> list[dict[str, Any]]:
    """取 A 股大盘指数实时行情（上证 / 深证成指 / 创业板指 / 沪深300）。返回记录列表。"""
    return astock.index_quote()


def global_stock(query: str) -> dict[str, Any]:
    """取美股 / 港股行情。

    参数：query 为标的名或代码（如 'AAPL'、'00700'、'腾讯'）。返回行情字典。
    用于跨市场联系分析（如 A 股与美股映射）。
    """
    return gstock.us_hk_stock(query)


def news_radar(force: bool = False) -> dict[str, Any]:
    """取资讯雷达（多源财经资讯聚合快照）。

    参数：force=True 强制刷新缓存。返回资讯结构。用于「事件催化与舆情」维度。
    """
    return newsradar.get_radar(force=force)


def closes(code: str, period: int = DAY, count: int = 250) -> list[float]:
    """便捷取收盘价序列（回测/相关性常用）。基于 kline，抽出 'close' 字段。

    参数：code 6 位代码；period 周期（DAY/WEEK/MONTH/MIN60）；count 根数（默认 250）。
    返回：收盘价 float 列表（时间升序）。数据源缺失或无 close 字段时返回空列表。
    """
    rows = kline(code, period=period, count=count)
    out: list[float] = []
    for r in rows:
        v = r.get("close")
        if v is not None:
            out.append(float(v))
    return out


# 区间预设 → 根数。与 registry._coerce_date_range 的白名单**必须一致**：
# 那里只认 3m/6m/1y 或 ISO 区间，所以前端也只能给这三个预设。
# 曾经前端多给了 2y/3y，选一下就 400（ROUND2 A5 修）。
RANGE_COUNT: dict[str, int] = {"3m": 63, "6m": 126, "1y": 250}

# ISO 区间回溯时的根数上限（约 8 年日线）。
#
# 为什么是 2000：实测数据源的天花板就在这里 ——
#   offset=1500 → 1500 根（首 2020-08-12）
#   offset=2000 → 2000 根（首 2018-07-23）
#   offset=3000 → 上游报错（且错误信息误导，说「代码可能不存在」）
# 设更大的值只会把上游错误当成本地故障。
# 上限的作用是防止「用户填了 2000 年」时去要一百万根，把数据源拖死。
_RANGE_MAX_BARS = 2000


def closes_for_range(
    code: str,
    range_spec: str,
    period: int = DAY,
    default_count: int = 250,
) -> list[tuple[str, float]]:
    """按**区间参数**取带日期的收盘价序列。

    这是 `range` 参数的唯一正确消费方式。此前 5 处调用点各自写
    `{"3m":63,"6m":126,"1y":250}.get(range, 250)` —— 于是传入
    `"2024-01-01:2024-12-31"` 这种**校验层已经放过**的 ISO 区间时，
    dict 查不到键就默默取最近 250 根：**用户选的年份被完全忽略，且无任何提示**。
    「算错」比抛异常危险得多，所以统一收到这里。

    两种形态：
      · 预设（3m / 6m / 1y）→ 转换成根数，行为与旧实现一致
      · ISO 区间（`YYYY-MM-DD:YYYY-MM-DD`）→ 按日期**真实过滤**
      · 其它未知值 → `default_count` 根（保持旧兜底行为，不因一次改动改两件事）

    ISO 区间为什么要先多取：`kline` 只能「取最近 N 根」，无法按日期范围拉。
    所以按「今天到 start 的自然日跨度」估算需要多少根，再过滤。估算偏大无害
    （多取几根），偏小会缺数据 —— 所以系数给 0.8 并留 40 根缓冲。
    """
    if not isinstance(range_spec, str):
        return closes_with_dates(code, period=period, count=default_count)

    if ":" not in range_spec:
        count = RANGE_COUNT.get(range_spec, default_count)
        return closes_with_dates(code, period=period, count=count)

    import datetime as _dt

    start_s, _, end_s = range_spec.partition(":")
    try:
        start = _dt.date.fromisoformat(start_s)
        end = _dt.date.fromisoformat(end_s)
    except ValueError as e:
        raise ValueError(f"非法 ISO 日期区间 {range_spec!r}") from e
    if start > end:
        # 用户填反了。不猜他的意图（猜错就是算错），直接报错。
        raise ValueError(f"区间起止颠倒：{start_s} > {end_s}")

    # 从「今天」回溯到 start 需要多少根日线（自然日 × 0.8 + 缓冲）
    today = _dt.date.today()
    span_days = max((today - start).days, 1)
    need = min(_RANGE_MAX_BARS, int(span_days * 0.8) + 40)

    rows = closes_with_dates(code, period=period, count=need)
    lo, hi = start.isoformat(), end.isoformat()
    return [(d, c) for d, c in rows if lo <= d[:10] <= hi]


def closes_with_dates(code: str, period: int = DAY, count: int = 250) -> list[tuple[str, float]]:
    """带日期的收盘价序列（相关性/对齐用）。基于 kline，抽 (date, close)。

    参数：code 6 位代码；period 周期（DAY/WEEK/MONTH/MIN60）；count 根数（默认 250）。
    返回：(日期字符串, 收盘价) 元组列表，时间升序。日期取 kline 记录的 'datetime'
    字段（mootdx bars 约定；兼容 'date'），截断到日粒度 'YYYY-MM-DD'。缺日期或 close
    的记录跳过；数据源缺失时返回空列表。

    用途：跨标的按日期对齐取交集（停牌/跨市场日历不齐时必需），再算相关性。
    """
    rows = kline(code, period=period, count=count)
    out: list[tuple[str, float]] = []
    for r in rows:
        close = r.get("close")
        raw = r.get("datetime", r.get("date"))
        if close is None or raw is None:
            continue
        out.append((str(raw)[:10], float(close)))
    return out
