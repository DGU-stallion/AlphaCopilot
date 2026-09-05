# pyright: reportMissingImports=false
"""今日**实时**打板情绪（盘面数据页用）（原样搬运自 vibe-astock/duanxian/live_emotion.py）。

和复盘口径的 `/api/market/emotion` 分工：
  · `/api/market/emotion` = 复盘口径，要当天的**收盘**数据；
  · 这里 = 盘中快照，回答"此刻打板好不好做"，数字随盘变化。

⚠️ 炸板率必须**另取炸板池**：涨停池里的 `zbc` 只是"这一只炸过几次"，
   全市场炸了多少家它答不了。分母 = 最终封住 + 炸板未回封 = 尝试过涨停的家数。

搬运适配：原实现从 `sys.modules.get("astock")` 取数据层，AlphaCopilot 的数据层是
`research.astock`，这里直接导入；仍保留 `_pool_unpinned` → `em_zt_topic_pool` 的取数出口
兜底，口径不变。
"""

from __future__ import annotations

import threading
import time
from typing import Optional

import research.astock as astock

from . import trade_calendar
from .util import china_now

# 取一次要打四个池（涨停/炸板/跌停/昨日涨停）。分两档缓存降低对数据源的压力：
# 今日的池子缓存 15 秒；昨日的池子盘中不会变，缓存 1 小时；日历结果一天内不变，也缓存掉。
_TODAY_TTL = 15.0
_PREV_TTL = 3600.0
_CAL_TTL = 3600.0
_cache: dict[str, tuple[float, object]] = {}
_lock = threading.Lock()


def _cached(key: str, ttl: float, build):
    """极简 TTL 缓存。**失败不缓存**（下次重试），但「空但有效」要缓存。

    ⚠️ 判据必须是 `is not None`，不能写 `if val:` —— 那会把**合法的空结果**
    当成失败：今天跌停 0 家时 `dt` 是 `[]`，用真值判断就永不入缓存。
    取数失败时 `_pool` 返回 None，两者本来就能区分。
    """
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    val = build()
    if val is not None:
        with _lock:
            _cache[key] = (now, val)
    return val


def _pool(kind: str, ymd: str) -> Optional[list[dict]]:
    """取东财涨停板四池之一。走未加锁出口；拿不到返回 None（不把失败当成 0 家）。"""
    fetch = getattr(astock, "_pool_unpinned", None) or getattr(astock, "em_zt_topic_pool", None)
    if fetch is None:
        return None
    try:
        return fetch(kind, ymd, "fbt:asc") or []
    except Exception:  # noqa: BLE001  取不到就整块标不可用
        return None


def _rate(hit: int, total: int) -> Optional[float]:
    return round(hit / total, 4) if total else None


def snapshot() -> dict:
    """今日实时打板情绪。非交易时段 / 取不到数据 → available=False 并说明原因。"""
    today = china_now().strftime("%Y-%m-%d")
    ymd = today.replace("-", "")

    settled = _cached(f"settled:{today}", _CAL_TTL,
                      lambda: ("Y" if trade_calendar.is_settled(today) else "N")) == "Y"

    zt = _cached(f"zt:{ymd}", _TODAY_TTL, lambda: _pool("getTopicZTPool", ymd))
    if zt is None:
        return {"available": False, "reason": "涨停池取数失败"}
    if not zt:
        return {"available": False, "date": today,
                "reason": "今日还没有涨停池（未开盘 / 非交易日）"}

    zb = _cached(f"zb:{ymd}", _TODAY_TTL, lambda: _pool("getTopicZBPool", ymd))   # 炸板未回封
    dt = _cached(f"dt:{ymd}", _TODAY_TTL, lambda: _pool("getTopicDTPool", ymd))   # 跌停

    boards = [int(p.get("lbc") or 1) for p in zt]
    zt_n, zb_n = len(zt), (len(zb) if zb is not None else None)
    tried = zt_n + zb_n if zb_n is not None else None   # 尝试过涨停的家数

    # 晋级率：昨日涨停的票今天又封住的比例。不需要行情，只比两天的池子成员。
    # ⚠️ 别用东财的 `getYesterdayZTPool` —— 实测它对任何日期都返回 0 条。
    #    直接取「上一交易日」的涨停池自己比。
    prev_day = _cached(f"prevday:{today}", _CAL_TTL,
                       lambda: trade_calendar.prev_trade_date(today))
    prev = (_cached(f"zt:{prev_day}", _PREV_TTL,
                    lambda: _pool("getTopicZTPool", prev_day.replace("-", "")))
            if prev_day else None)
    today_codes = {str(p.get("c")) for p in zt}
    promo: Optional[float] = None
    promo_base: Optional[int] = None
    if prev:
        promo_base = len(prev)
        promo = _rate(sum(1 for p in prev if str(p.get("c")) in today_codes), promo_base)

    return {
        "available": True,
        "date": today,
        "as_of": china_now().strftime("%H:%M"),
        "phase": "盘中" if not settled else "已收盘",
        "zt_count": zt_n,
        "dt_count": len(dt) if dt is not None else None,
        "zb_count": zb_n,
        "max_boards": max(boards) if boards else 0,
        "lianban_count": sum(1 for b in boards if b >= 2),
        "seal_rate": _rate(zt_n, tried) if tried else None,
        "break_rate": _rate(zb_n, tried) if (tried and zb_n is not None) else None,
        "promotion_rate": promo,
        "promotion_base": promo_base,
        "promotion_base_date": prev_day,
    }
