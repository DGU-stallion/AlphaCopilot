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
