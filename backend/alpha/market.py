"""alpha.market —— 盘面数据 + 涨停样本统计（S2，确定性只读页）。

对标 vibe-astock 的「客观市场事实」纪律：只陈述"今天发生了什么"，不做买卖建议；
数据源不可用时**如实标注不可用**，绝不把失败伪装成 0（沿用 vibe-astock 的偏执）。

数据来源复用现有 research.astock（东财涨停池 push2ex / 成交额榜 clist / 大盘指数），
它们在数据源不可达时返回 []（优雅降级）。本模块把纯计算与取数分离：
  · _compute_* 是纯函数，用 fixture 即可测（不依赖网络）；
  · 注册的 market.* / limit_up.* 组合取数 + 计算 + 产出 block payload。

注册进 alpha.registry 白名单，供 page spec 的 analysis_ref.fn 引用（复用现有 PageRenderer）。
"""

from __future__ import annotations

from datetime import date as _date
from typing import Any

from alpha.registry import register
from research import astock

# ---------------------------------------------------------------------------
# 纯计算 helper（fixture 可测，不碰网络）
# ---------------------------------------------------------------------------

def _pct_tone(pct: Any) -> str:
    """A 股红涨绿跌的 tone 映射（供 metric block 上色）。"""
    try:
        f = float(pct)
    except (TypeError, ValueError):
        return "muted"
    if f > 0:
        return "up"
    if f < 0:
        return "down"
    return "flat"


def _fmt_pct(v: Any) -> str:
    try:
        f = float(v)
        return f"{'+' if f > 0 else ''}{f:.2f}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_amount_yi(v: Any) -> str:
    """成交额（元）→ 亿元字符串。"""
    try:
        return f"{float(v) / 1e8:.1f}亿"
    except (TypeError, ValueError):
        return "—"


def compute_ladder(pool: list[dict]) -> dict[int, int]:
    """从涨停池算连板梯队分布：{连板数: 家数}。pool 每项含 lbc(连板数)。

    纯函数——给定 pool 就能算，不依赖网络。空池返回空 dict。
    """
    dist: dict[int, int] = {}
    for item in pool:
        boards = int(item.get("lbc", 1) or 1)
        dist[boards] = dist.get(boards, 0) + 1
    return dist


def compute_breadth(pool_zt: list[dict], pool_zb: list[dict], pool_dt: list[dict]) -> dict:
    """从涨停/炸板/跌停池算市场宽度概览。纯函数。

    返回 {limit_up, broken(炸板), limit_down, seal_rate(封板率)}。
    封板率 = 涨停 / (涨停 + 炸板)，反映资金封板质量；分母 0 时为 None。
    """
    n_zt = len(pool_zt)
    n_zb = len(pool_zb)
    n_dt = len(pool_dt)
    denom = n_zt + n_zb
    seal_rate = round(n_zt / denom, 3) if denom else None
    return {
        "limit_up": n_zt,
        "broken": n_zb,
        "limit_down": n_dt,
        "seal_rate": seal_rate,
        "max_boards": max((int(x.get("lbc", 1) or 1) for x in pool_zt), default=0),
    }


def compute_limitup_stats(pool: list[dict]) -> dict:
    """涨停样本统计：连板结构分布 + 行业分布。纯函数。

    返回 {total, ladder(梯队分布), by_industry(行业→家数, top 从多到少)}。
    """
    ladder = compute_ladder(pool)
    industries: dict[str, int] = {}
    for item in pool:
        ind = str(item.get("hybk") or item.get("industry") or "其它")
        industries[ind] = industries.get(ind, 0) + 1
    by_industry = dict(sorted(industries.items(), key=lambda kv: -kv[1]))
    return {"total": len(pool), "ladder": ladder, "by_industry": by_industry}


def _today_yyyymmdd() -> str:
    return _date.today().strftime("%Y%m%d")


def _unavailable_metric(reason: str) -> dict:
    """数据源不可用时的 metric block payload——如实标注，不伪装成 0。"""
    return {"items": [{"label": "数据状态", "value": "暂不可用", "hint": reason, "tone": "muted"}]}


# ---------------------------------------------------------------------------
# 注册的分析函数（盘面数据页）
# ---------------------------------------------------------------------------

@register("market.breadth", params=[])
def market_breadth() -> dict:
    """市场宽度指标卡：涨停/炸板/跌停家数 + 封板率 + 最高连板。返回 metric block payload。

    数据源（东财 push2ex 涨停板中心）不可用时如实标注「暂不可用」，不显示为 0。
    """
    d = _today_yyyymmdd()
    zt = astock.em_zt_topic_pool("getTopicZTPool", d)
    zb = astock.em_zt_topic_pool("getTopicZBPool", d)
    dt = astock.em_zt_topic_pool("getTopicDTPool", d)
    if not zt and not zb and not dt:
        return _unavailable_metric("涨停板行情中心数据源暂不可达（非交易时段或网络受限）")
    b = compute_breadth(zt, zb, dt)
    seal = f"{b['seal_rate'] * 100:.1f}%" if b["seal_rate"] is not None else "—"
    return {
        "items": [
            {"label": "涨停", "value": b["limit_up"], "tone": "up"},
            {"label": "炸板", "value": b["broken"], "tone": "muted"},
            {"label": "跌停", "value": b["limit_down"], "tone": "down"},
            {"label": "封板率", "value": seal, "hint": "涨停/(涨停+炸板)", "tone": "flat"},
            {"label": "最高连板", "value": b["max_boards"], "hint": "情绪高度", "tone": "up"},
        ]
    }


@register("market.index", params=[])
def market_index() -> dict:
    """A 股大盘指数表：上证/深证/创业板/沪深300 最新价与涨跌幅。返回 table block payload。"""
    try:
        indices = astock.index_quote()
    except Exception:  # noqa: BLE001
        indices = []
    if not indices:
        return {"columns": ["指数", "最新", "涨跌幅"], "rows": [["暂不可用", "—", "—"]]}
    rows = [[it.get("name", "—"), it.get("price", "—"), _fmt_pct(it.get("change_pct"))]
            for it in indices]
    return {"columns": ["指数", "最新", "涨跌幅"], "rows": rows}


@register("market.turnover", params=[])
def market_turnover() -> dict:
    """全市场成交额榜 Top20（客观公开榜单）。返回 table block payload。

    东财 push2 不可达时降级 push2delay（research 层已处理）；仍失败则标注不可用。
    """
    try:
        rank = astock.market_turnover_rank(20)
    except Exception:  # noqa: BLE001
        rank = []
    if not rank:
        return {"columns": ["代码", "名称", "成交额", "涨跌幅", "行业"],
                "rows": [["暂不可用", "—", "—", "—", "—"]]}
    rows = [[r.get("code", ""), r.get("name", ""), _fmt_amount_yi(r.get("amount")),
             _fmt_pct(r.get("pct")), r.get("industry", "")] for r in rank]
    return {"columns": ["代码", "名称", "成交额", "涨跌幅", "行业"], "rows": rows}


# ---------------------------------------------------------------------------
# 注册的分析函数（涨停样本统计页）
# ---------------------------------------------------------------------------

@register("limit_up.ladder", params=[])
def limit_up_ladder() -> dict:
    """涨停连板梯队分布柱状图：横轴连板数、纵轴家数。返回 ECharts bar option。

    梯队连续=资金逐级接力；出现断层=高标悬空（情绪断层信号）。数据源不可用时空图+提示。
    """
    from alpha import chart

    d = _today_yyyymmdd()
    pool = astock.em_zt_topic_pool("getTopicZTPool", d)
    if not pool:
        # 空图但结构合法（不伪装成 0 家；标题即说明）
        return chart.bar([], {"家数": []}, title="连板梯队（数据源暂不可用）")
    dist = compute_ladder(pool)
    boards = sorted(dist)
    labels = [f"{b}板" for b in boards]
    counts = [dist[b] for b in boards]
    return chart.bar(labels, {"家数": counts}, title="涨停连板梯队分布")


@register("limit_up.industry", params=[])
def limit_up_industry() -> dict:
    """涨停个股行业分布表（从多到少）。返回 table block payload。"""
    d = _today_yyyymmdd()
    pool = astock.em_zt_topic_pool("getTopicZTPool", d)
    if not pool:
        return {"columns": ["行业", "涨停家数"], "rows": [["暂不可用", "—"]]}
    stats = compute_limitup_stats(pool)
    rows = [[ind, n] for ind, n in stats["by_industry"].items()]
    return {"columns": ["行业", "涨停家数"], "rows": rows}


@register("limit_up.summary", params=[])
def limit_up_summary() -> dict:
    """涨停样本概览指标卡：涨停总数 + 最高连板 + 连板梯队档数。返回 metric block payload。"""
    d = _today_yyyymmdd()
    pool = astock.em_zt_topic_pool("getTopicZTPool", d)
    if not pool:
        return _unavailable_metric("涨停池数据源暂不可达")
    stats = compute_limitup_stats(pool)
    ladder = stats["ladder"]
    return {
        "items": [
            {"label": "涨停总数", "value": stats["total"], "tone": "up"},
            {"label": "最高连板", "value": max(ladder) if ladder else 0, "tone": "up"},
            {"label": "连板梯队档数", "value": len(ladder), "hint": "档数越多梯队越完整",
             "tone": "flat"},
        ]
    }
