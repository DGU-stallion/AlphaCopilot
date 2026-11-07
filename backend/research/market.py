# pyright: reportMissingImports=false, reportArgumentType=false, reportAttributeAccessIssue=false, reportOptionalIterable=false, reportOptionalMemberAccess=false
"""市场总览数据层 —— 市场情绪 + 板块资金流（板块/大盘级公开数据，不涉个股推荐）。

省流量：全站共享一份缓存（TTL 默认 5 分钟），多个用户/多次打开只抓一次；
盘中 5 分钟刷新足够，非交易时段数据本就不变。数据源全免费、无 key。
"""

from __future__ import annotations

import time
from collections import Counter
from datetime import datetime, timedelta, timezone

import research.astock as astock
import research.gstock as gstock

BEIJING = timezone(timedelta(hours=8))
_CACHE: dict = {}
_TTL = 300  # 5 分钟；全站共享，省数据源压力


def _cached(key: str, fn, valid=bool):
    """TTL 缓存。数据源故障的空结果不缓存（valid 判否），下次请求直接重试。"""
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    val = fn()
    if valid(val):
        _CACHE[key] = (now, val)
    return val


def _num(v) -> int:
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


# 涨停原因（题材串）—— 东财涨停池(push2ex)不含原因字段，唯一可靠来源是同花顺问财。
# 需环境变量 IWENCAI_API_KEY（不入库）；缺 key / 查询失败时返回 {}，reason 留空不伪造。
def _clean_reason(text: str, max_tags: int = 4, max_len: int = 40) -> str:
    """题材串清洗：统一分隔符、限标签数与总长（问财多用 '+' 分隔）。"""
    text = text.replace("，", "+").replace(",", "+").strip()
    tags = [t.strip() for t in text.split("+") if t.strip()]
    return "+".join(tags[:max_tags])[:max_len]


def _fetch_zt_reasons(date: str) -> dict:
    """问财拉指定交易日全部涨停股的涨停原因，返回 {6位代码: 题材串}。

    查询必须带日期（写"今日"常返 0 行、且可能与回退到的池子不同日）。缺 key / 失败 → {}。
    """
    import os

    key = os.environ.get("IWENCAI_API_KEY", "").strip()
    if not key:
        return {}
    import secrets

    import requests

    base = os.environ.get("IWENCAI_BASE_URL", "https://openapi.iwencai.com").rstrip("/")
    headers = {
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        "X-Claw-Call-Type": "normal", "X-Claw-Skill-Id": "report-search",
        "X-Claw-Skill-Version": "2.0.0", "X-Claw-Plugin-Id": "none",
        "X-Claw-Plugin-Version": "none", "X-Claw-Trace-Id": secrets.token_hex(32),
    }
    reasons: dict[str, str] = {}
    try:
        for page in range(1, 4):  # 单页 50，涨停一般 1~3 页
            payload = {"query": f"{date}涨停的股票 涨停原因", "page": str(page),
                       "limit": "50", "is_cache": "1", "expand_index": "true"}
            r = requests.post(f"{base}/v1/query2data", json=payload, headers=headers, timeout=30)
            rows = (r.json() or {}).get("datas") or []
            if not rows:
                break
            code_cols = [c for c in rows[0] if "代码" in c]
            reason_cols = [c for c in rows[0] if "涨停原因" in c]
            if not code_cols or not reason_cols:
                break
            cc, rc = code_cols[0], reason_cols[0]
            for row in rows:
                code6 = str(row.get(cc, ""))[:6]
                reason = str(row.get(rc, "")).strip()
                if code6 and reason and reason.lower() != "nan" and code6 not in reasons:
                    reasons[code6] = _clean_reason(reason)
            if len(rows) < 50:
                break
    except Exception:  # noqa: BLE001  问财不可达/异常 → 已取到的照常返回，其余留空
        return reasons
    return reasons


def _sentiment() -> dict:
    """市场情绪：涨跌家数/涨停跌停/活跃度 + 大盘宽度、题材投机（客观数据机械分档）。"""
    try:
        # akshare 惰性导入（同 astock 模式）：未装时降级返回空，不挡整个服务启动
        df = astock._akshare().stock_market_activity_legu()
        d = {row["item"]: row["value"] for _, row in df.iterrows()}
    except Exception:
        return {}
    up, down, flat = _num(d.get("上涨")), _num(d.get("下跌")), _num(d.get("平盘"))
    zt, zt_real = _num(d.get("涨停")), _num(d.get("真实涨停"))
    dt, dt_real = _num(d.get("跌停")), _num(d.get("真实跌停"))
    r = up / max(down, 1)
    if up < 600:
        breadth = "冰点"
    elif r < 0.7:
        breadth = "偏弱"
    elif r < 1.2:
        breadth = "中性"
    elif r < 2.5:
        breadth = "偏强"
    else:
        breadth = "普涨"
    speculation = "亢奋" if zt_real >= 100 else "活跃" if zt_real >= 60 else "普通" if zt_real >= 30 else "冰点"
    return {
        "up": up, "down": down, "flat": flat,
        "zt": zt, "zt_real": zt_real, "dt": dt, "dt_real": dt_real,
        "active": str(d.get("活跃度", "")),
        "breadth": breadth, "speculation": speculation,
        "date": str(d.get("统计日期", "")),
    }


def _sectors() -> list[dict]:
    """行业资金流（按净额降序）。不含领涨股等个股字段。"""
    try:
        f = astock._akshare().stock_fund_flow_industry(symbol="即时")
        f = f.sort_values("净额", ascending=False)
    except Exception:
        return []
    out = []
    for _, row in f.iterrows():
        out.append({
            "name": str(row["行业"]),
            "pct": round(float(row.get("行业-涨跌幅", 0) or 0), 2),
            "net": round(float(row.get("净额", 0) or 0), 2),
            "inflow": round(float(row.get("流入资金", 0) or 0), 2),
            "outflow": round(float(row.get("流出资金", 0) or 0), 2),
            "firms": _num(row.get("公司家数")),
        })
    return out


def get_overview() -> dict:
    """市场情绪 + 板块资金（含缓存）。资金轮动由前端从 sectors 头尾取。"""
    def build():
        return {
            "sentiment": _sentiment(),
            "sectors": _sectors(),
            "updated": datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M"),
        }
    return _cached("overview", build, valid=lambda v: bool(v.get("sentiment") or v.get("sectors")))


def _emotion_for_date(resolved: str) -> dict:
    """算**指定交易日**（YYYYMMDD）的情绪聚合。

    为什么抽出来：当日实时（`_emotion`）与历史回填（scripts/backfill-emotion.py）
    必须用**同一段计算逻辑**。各写一份的话，两者算出的「封板率」迟早会不一致，
    而图表上分不出哪个是对的。

    只把池子聚合成计数与比率，**不输出任何个股 code/name** —— 守产品「零标的」红线。
    返回 {} 表示这一天没有涨停（非交易日/未开盘）。
    """
    zt = astock.em_zt_topic_pool("getTopicZTPool", resolved, "fbt:asc")
    if not zt:
        return {}

    # 跌停池**必须** sort=fund:asc：其他排序（含默认）会返回空数组而不报错，
    # 让人误以为「当天没跌停」。实测 2026-10-21：默认排序 0 条，fund:asc 5 条。
    zb = astock.em_zt_topic_pool("getTopicZBPool", resolved, "fbt:asc")    # 炸板池
    dt = astock.em_zt_topic_pool("getTopicDTPool", resolved, "fund:asc")   # 跌停池
    yzt = astock.em_zt_topic_pool("getYesterdayZTPool", resolved, "zs:desc")  # 昨涨停池

    boards = [_num(p.get("lbc")) or 1 for p in zt]      # 每只连板数（缺省按 1 板）
    lianban = [b for b in boards if b >= 2]             # 2 板及以上（连板）
    tiers = Counter(min(b, 5) for b in lianban)
    ladder = [{"boards": b, "count": tiers[b], "plus": b >= 5} for b in sorted(tiers)]

    zt_count, zb_count, yzt_count = len(zt), len(zb), len(yzt)
    attempts = zt_count + zb_count                       # 尝试涨停 = 封住 + 炸板
    seal_rate = round(zt_count / attempts, 3) if attempts else None      # 封板率
    break_rate = round(zb_count / attempts, 3) if attempts else None     # 炸板率
    promotion_rate = round(len(lianban) / yzt_count, 3) if yzt_count else None

    return {
        "date": f"{resolved[:4]}-{resolved[4:6]}-{resolved[6:]}",
        "zt_count": zt_count,
        "dt_count": len(dt),
        "zb_count": zb_count,
        "max_boards": max(boards) if boards else 0,
        "lianban_count": len(lianban),
        "ladder": ladder,
        "seal_rate": seal_rate,
        "break_rate": break_rate,
        "promotion_rate": promotion_rate,
        "yzt_count": yzt_count,
    }


def _emotion() -> dict:
    """短线情绪（**当日**）：连板梯队 / 最高连板 / 炸板率 / 封板率 / 晋级率 / 涨跌停家数。

    数据源＝东财涨停板四池（push2ex）。计算逻辑在 `_emotion_for_date`，
    与历史回填共用（见那里的注释）。

    与旧版的区别：旧版内联了一整套计算，现在只负责「定位最近交易日」+ 补个股名，
    聚合的部分全部交出去。
    """
    # 定位最近交易日：从今天往前回溯，第一日有涨停池即取（非交易日/盘前返空则继续回溯）。
    today = datetime.now(BEIJING).date()
    resolved: str | None = None
    for back in range(8):
        d = (today - timedelta(days=back)).strftime("%Y%m%d")
        if astock.em_zt_topic_pool("getTopicZTPool", d, "fbt:asc"):
            resolved = d
            break
    if not resolved:
        return {}

    agg = _emotion_for_date(resolved)
    if not agg:
        return {}

    # 连板股清单（2 板+，客观公开榜单数据；按连板数、成交额降序）。
    # 产品定位调整（2026-07-05）：从「零标的」→「展示客观榜单但不推荐/不预测/不评分」。
    # 注意：**这一部分不进历史表**（api/emotion_store.py 只存聚合计数）。
    zt = astock.em_zt_topic_pool("getTopicZTPool", resolved, "fbt:asc")
    reasons = _fetch_zt_reasons(resolved)  # 涨停原因题材串（问财；缺 key/失败 → {}）
    lianban_stocks = sorted(
        ({
            "code": str(p.get("c", "")), "name": p.get("n", ""),
            "boards": _num(p.get("lbc")) or 1,
            "price": round((astock._numf(p.get("p")) or 0) / 1000, 2),
            "pct": round(astock._numf(p.get("zdp")) or 0, 2),
            "amount": astock._numf(p.get("amount")),      # 成交额,元
            "float_cap": astock._numf(p.get("ltsz")),     # 流通市值,元
            "industry": p.get("hybk", ""),
            "reason": reasons.get(str(p.get("c", ""))) or None,
        } for p in zt if (_num(p.get("lbc")) or 1) >= 2),
        key=lambda x: (-x["boards"], -(x["amount"] or 0)),
    )
    return {**agg, "lianban_stocks": lianban_stocks}


def get_short_term_emotion() -> dict:
    """短线情绪（含缓存，5 分钟）。"""
    return _cached("emotion", _emotion)


def get_turnover_top() -> dict:
    """全市场成交额榜 Top20（客观公开榜单，含缓存 5 分钟）。"""
    def build():
        return {
            "stocks": astock.market_turnover_rank(20),
            "updated": datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M"),
        }
    return _cached("turnover_top", build, valid=lambda v: bool(v.get("stocks")))


def get_global_indices() -> list[dict]:
    """全球指数快照（美股 / 港股，含缓存 5 分钟）。空结果不缓存。"""
    return _cached("global_indices", gstock.global_indices, valid=bool)
