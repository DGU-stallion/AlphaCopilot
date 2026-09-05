# pyright: reportMissingImports=false
"""涨停样本统计 —— 昨日涨停样本在次日的历史表现（缝合搬运自 vibe-astock/duanxian/backtest.py）。

⚠️ **这是「市场现象统计」，不是「策略回测」，更不是"打板策略的收益"。**
样本 = 昨日**收盘**留在涨停池里的票（事后名单）：冲板未封住的、排队未成交的、
一字板买不进的都不在内 —— 真实打板的期望必然低于这里的数字。策略名保留只为可读性。

## 数据来源：一天一次请求

`stock_zt_pool_previous_em(date=X)` 直接给出「在 X-1 涨停的股票在 X 当天的表现」，
含 `昨日连板数`（分档）、`涨跌幅`（结果）、`昨日封板时间`、`所属行业`。历史结果不再变 →
落盘缓存，60 个交易日只需 60 次请求。

## 搬运适配（与 vibe-astock 原版的差异，最小化）

- akshare 缺失（mac 无 mootdx/akshare 时的原降级路径）→ `_fetch_prev_pool` 返回 None，
  `run_backtest` 返回 `{"available": False, "reason": ...}`，不伪装 0。
- 情绪分环境（vibe-astock 依赖 `emotion_metrics` 缓存）本仓库暂无该缓存层 → 分环境统一
  归「未知」（MVP：先出整体/封板曲线/分策略统计；情绪分档等 emotion 缓存层齐备再接）。
- 判涨停复用 vibe-astock 原口径：`现价 == 涨停价`（数据源直接给的事实，自动适配各板涨跌幅制度）。
"""

from __future__ import annotations

import json
import os
from statistics import mean, median
from typing import Callable, Optional

from duanxian import trade_calendar

# 回测结果与逐日样本缓存目录（跟着算它的东西走，与 web 层解耦）。
_CACHE_DIR = os.path.expanduser("~/.alphacopilot/cache/prev_pool")


def _atomic_write_json(path: str, obj: object) -> None:
    """原子落盘：先写临时文件再 rename，避免半截写坏缓存。失败静默（缓存只是加速）。"""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:  # noqa: BLE001  写盘失败不影响返回
        pass

# 早/晚封板时间界（HHMMSS）。⚠️ 比的是数据源的**最后封板时间**：10:00 前"最终封住"
# = 早盘封板且此后没再炸开，比单纯"首封早"更强的信号。
_EARLY_SEAL = "100000"
_LATE_SEAL = "143000"


def _fetch_prev_pool(date: str) -> Optional[list[dict]]:
    """取「前一交易日涨停股在 date 当天的表现」，数据定稿后落盘缓存。取数失败返回 None。"""
    is_past = trade_calendar.is_settled(date)   # 含"今天且已收盘"——语料过期不候
    path = os.path.join(_CACHE_DIR, f"{date}.json")
    if is_past and os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:  # noqa: BLE001  缓存坏了当没有
            pass

    try:
        import akshare as ak

        df = ak.stock_zt_pool_previous_em(date=date.replace("-", ""))
    except Exception:  # noqa: BLE001  mac 无 akshare / 数据源不可达 → 原降级
        return None
    if df is None or not len(df):
        return None

    rows = []
    for _, r in df.iterrows():
        try:
            rows.append({
                "code": str(r["代码"]).zfill(6),
                "name": str(r["名称"]),
                "ret": float(r["涨跌幅"]),
                "prev_boards": int(r["昨日连板数"]),
                "seal_time": str(r.get("昨日封板时间", "")),
                "sector": str(r.get("所属行业", "")),
                # 判涨停用「现价==涨停价」，自动适配各板涨跌幅制度
                "close": float(r["最新价"]) if r.get("最新价") is not None else None,
                "limit_price": float(r["涨停价"]) if r.get("涨停价") is not None else None,
            })
        except (KeyError, ValueError, TypeError):
            continue  # 单行脏数据不拖累整天
    if not rows:
        return None
    if is_past:
        _atomic_write_json(path, rows)   # 写失败不影响返回
    return rows


# ---------------------------------------------------------------- 策略定义
def _is_early(row: dict) -> bool:
    t = (row.get("seal_time") or "").strip()
    return bool(t) and t <= _EARLY_SEAL


def _is_late(row: dict) -> bool:
    t = (row.get("seal_time") or "").strip()
    return bool(t) and t >= _LATE_SEAL


STRATEGIES: dict[str, dict] = {
    "首板打板": {
        "desc": "昨日首次涨停的全部个股，今天持有到收盘",
        "filter": lambda r, _c: r["prev_boards"] == 1,
    },
    "首板·早封": {
        "desc": "昨日首板且 10:00 前**最终封板**（早盘封住且此后没再炸开）",
        "filter": lambda r, _c: r["prev_boards"] == 1 and _is_early(r),
    },
    "首板·尾盘封": {
        "desc": "昨日首板但 14:30 后才**最终封板**（含尾盘偷袭与全天反复炸板后回封）",
        "filter": lambda r, _c: r["prev_boards"] == 1 and _is_late(r),
    },
    "首板·涨停数前二行业": {
        "desc": "昨日首板且属于当日涨停家数最多的两个**行业**（注：行业≠题材）",
        "filter": lambda r, c: (r["prev_boards"] == 1 and r["sector"]
                                and r["sector"] in c["main_sectors"]),
    },
    "连板接力": {
        "desc": "昨日已 2 板及以上的个股，今天持有到收盘",
        "filter": lambda r, _c: r["prev_boards"] >= 2,
    },
    "高标接力": {
        "desc": "昨日 3 板及以上的高位标，今天持有到收盘",
        "filter": lambda r, _c: r["prev_boards"] >= 3,
    },
    "全体涨停": {
        "desc": "昨日涨停的全部个股（基准线，用来对照其它策略有没有超额）",
        "filter": lambda _r, _c: True,
    },
}

_MAIN_SECTOR_TOP = 2


def _day_context(rows: list[dict]) -> dict:
    """当天的群体上下文：涨停家数最多的前 N 个行业（主线）。"""
    counts: dict[str, int] = {}
    for r in rows:
        s = (r.get("sector") or "").strip()
        if s:
            counts[s] = counts.get(s, 0) + 1
    top = sorted(counts, key=lambda k: counts[k], reverse=True)[:_MAIN_SECTOR_TOP]
    return {"main_sectors": set(top), "sector_counts": counts}


# 封板时间分档（HHMMSS 上界，含）。分档而不给可调阈值：把整条曲线摆出来，悬崖一眼看见。
SEAL_BUCKETS: list[tuple[str, str]] = [
    ("开盘秒板", "093500"),
    ("9:35-10:00", "100000"),
    ("10:00-11:00", "110000"),
    ("11:00-14:00", "140000"),
    ("14:00后", "150500"),
]


def _is_limit_up(row: dict) -> Optional[bool]:
    """判该票次日收盘是否又涨停：现价==涨停价（数据源直接给的事实）。缺字段返回 None。"""
    close = row.get("close")
    limit = row.get("limit_price")
    if close is None or limit is None:
        return None
    return abs(close - limit) < 1e-6


def _stats(rets: list[float], rows: Optional[list[dict]] = None) -> dict:
    """一组收益的统计。样本为空返回 None 字段，不伪装成 0。"""
    if not rets:
        return {"sample": 0, "win_rate": None, "avg": None, "median": None,
                "best": None, "worst": None, "limit_up_rate": None}
    lur = None
    if rows is not None and len(rows) == len(rets):
        judged = [_is_limit_up(row) for row in rows]
        ok = [j for j in judged if j is not None]
        lur = round(sum(1 for j in ok if j) / len(ok), 3) if ok else None
    return {
        "sample": len(rets),
        "win_rate": round(sum(1 for r in rets if r > 0) / len(rets), 3),
        "avg": round(mean(rets), 2),
        "median": round(median(rets), 2),
        "best": round(max(rets), 2),
        "worst": round(min(rets), 2),
        "limit_up_rate": lur,
    }


def seal_time_curve(per_day: dict[str, list[dict]]) -> list[dict]:
    """首板按**最后封板时间**分档的收益曲线 —— "什么时候把板封住值多少钱"。

    只统计首板（连板股的封板时间含义不同，混在一起会污染结论）。
    """
    buckets: dict[str, list[dict]] = {name: [] for name, _ in SEAL_BUCKETS}
    unknown: list[dict] = []
    for rows in per_day.values():
        for r in rows:
            if r["prev_boards"] != 1:
                continue
            t = (r.get("seal_time") or "").strip()
            if not t:
                unknown.append(r)
                continue
            for name, upper in SEAL_BUCKETS:
                if t <= upper:
                    buckets[name].append(r)
                    break
            else:
                buckets[SEAL_BUCKETS[-1][0]].append(r)

    out = [{"bucket": name, **_stats([x["ret"] for x in rs], rs)}
           for name, rs in buckets.items()]
    if unknown:
        out.append({"bucket": "封板时间缺失",
                    **_stats([x["ret"] for x in unknown], unknown)})
    return out


def run_backtest(days: int = 30, strategies: Optional[list[str]] = None) -> dict:
    """跑涨停样本统计。

    Args:
        days: 回看多少个已收盘交易日。
        strategies: 只跑指定策略；None = 全部。
    """
    names = [n for n in (strategies or list(STRATEGIES)) if n in STRATEGIES]
    if not names:
        return {"available": False, "reason": "没有有效策略"}

    dates = trade_calendar.last_trade_dates(days)
    if len(dates) < 5:
        return {"available": False, "reason": f"可用交易日不足（{len(dates)}/5）"}

    per_day: dict[str, list[dict]] = {}
    missing = []
    for d in dates:
        rows = _fetch_prev_pool(d)
        if rows is None:
            missing.append(d)
            continue
        per_day[d] = rows
    if len(per_day) < 5:
        return {"available": False,
                "reason": f"取数成功天数不足（{len(per_day)}/{len(dates)}）"
                          "——mac 无 akshare 时此页降级，属预期",
                "missing_days": missing}

    ctx_by_day = {d: _day_context(rows) for d, rows in per_day.items()}

    results = {}
    for name in names:
        f: Callable[[dict, dict], bool] = STRATEGIES[name]["filter"]
        all_rows: list[dict] = []
        daily = []
        equity = 100.0
        for d in sorted(per_day):
            ctx = ctx_by_day[d]
            hit = [r for r in per_day[d] if f(r, ctx)]
            rets = [r["ret"] for r in hit]
            all_rows.extend(hit)
            day_avg = round(mean(rets), 2) if rets else None
            if day_avg is not None:
                equity *= (1 + day_avg / 100)   # 等权每日满仓，日频复利
            daily.append({"date": d, "sample": len(rets), "avg": day_avg,
                          "equity": round(equity, 2)})
        results[name] = {
            "desc": STRATEGIES[name]["desc"],
            "overall": _stats([r["ret"] for r in all_rows], all_rows),
            "daily": daily,
            "final_equity": round(equity, 2),
        }

    return {
        "available": True,
        # ⚠️ 让调用方（尤其前端）必须面对这层口径，别把它当"策略收益"
        "layer": "market_phenomenon",
        "sample_caveat": (
            "样本 = 昨日**收盘**留在涨停池里的票（事后名单）。"
            "冲板未封住的、排队未成交的、一字板买不进的都不在内 —— "
            "真实打板的期望必然低于这里的数字。这是市场现象统计，不是策略回测。"
        ),
        "days_requested": days,
        "days_used": len(per_day),
        "date_from": min(per_day),
        "date_to": max(per_day),
        "missing_days": missing,   # ⚠️ 不静默截断：取数失败的日子明说
        "seal_curve": seal_time_curve(per_day),
        "strategies": results,
    }
