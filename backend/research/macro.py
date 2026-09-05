"""宏观看板取数层：大宗商品 / 汇率（腾讯 gtimg）+ 美债收益率曲线（财政部 CSV）。

每一类都自洽降级：取不到就返回 {"available": False, "reason": ...}，
**不给半份数据、不拿占位顶替**（同 overseas.py 的口径）。

数据源均免费、无 key：
  · 商品 / 汇率 走腾讯 gtimg（同 overseas.py 的 http://qt.gtimg.cn/q=）；
  · 美债走美国财政部官方每日 CSV（走系统代理即可通，偶发超时 → try/except 降级）。
"""

from __future__ import annotations

import csv
import io
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Optional

_TENCENT = "http://qt.gtimg.cn/q="
# 腾讯行情要 Referer 才稳定回数（实测主 agent 确认），沿用 overseas.py 的 UA 再加 Referer
_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com"}

# 大宗商品（hf_ 命名空间，逗号分隔字段）。字段位见文件内注释。
# (腾讯代码, 展示名)
_COMMODITIES = (
    ("hf_CL", "纽约原油"),
    ("hf_OIL", "布伦特原油"),
    ("hf_GC", "COMEX黄金"),
    ("hf_XAU", "伦敦金"),
    ("hf_SI", "白银"),
)
# hf_ 逗号数组字段位
_HF_PRICE, _HF_PCT = 0, 1

# 汇率（fx 命名空间，~ 分隔字段）。(腾讯代码, 展示名)
_FOREX = (
    ("fxUSDCNY", "美元/人民币"),
    ("fxEURUSD", "欧元/美元"),
    ("fxUSDJPY", "美元/日元"),
    ("fxGBPUSD", "英镑/美元"),
    ("fxUSDHKD", "美元/港币"),
)
# fx ~ 数组字段位：[3]现价 [13]涨跌幅%（实测；[12]为涨跌额，腾讯直接给 %，不用自算）
_FX_PRICE, _FX_PCT = 3, 13

# 美债关键期限：CSV 列名 → 展示名
_TREASURY_TENORS = (
    ("2 Yr", "2年"),
    ("5 Yr", "5年"),
    ("10 Yr", "10年"),
    ("30 Yr", "30年"),
)


def _num(v: str) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fetch(symbols: list[str]) -> dict[str, list[str]]:
    """批量取腾讯行情，返回 {腾讯代码: 字段数组}。整批失败返回空 dict。

    腾讯行只按 `;` 分隔，形如 `v_hf_CL="63.20,-0.35,...";`。取键时按 `v_` 之后、
    `=` 之前的整段作为代码（hf_ / fx 都不含下划线歧义，直接切 `v_` 前缀即可）。
    """
    if not symbols:
        return {}
    try:
        req = urllib.request.Request(_TENCENT + ",".join(symbols), headers=_HEADERS)
        raw = urllib.request.urlopen(req, timeout=12).read().decode("gbk", "ignore")
    except Exception:  # noqa: BLE001  取不到就整块标不可用，不给半份数据
        return {}
    out: dict[str, list[str]] = {}
    for line in raw.split(";"):
        if "=" not in line or '"' not in line:
            continue
        # v_hf_CL="..." / v_fxUSDCNY="..."：取 v_ 之后、= 之前的代码
        key = line.split("=", 1)[0].strip()
        if key.startswith("v_"):
            key = key[2:]
        payload = line.split('"', 2)
        if len(payload) < 2:
            continue
        out[key] = payload[1].split(",") if key.startswith("hf_") else payload[1].split("~")
    return out


def commodities() -> dict:
    """大宗商品快照：原油 / 布伦特 / 黄金 / 伦敦金 / 白银。"""
    raw = _fetch([s for s, _ in _COMMODITIES])
    rows = []
    for sym, name in _COMMODITIES:
        f = raw.get(sym)
        if not f or len(f) <= _HF_PCT:
            continue
        price, pct = _num(f[_HF_PRICE]), _num(f[_HF_PCT])
        if price is None or pct is None:
            continue
        rows.append({"name": name, "price": round(price, 2), "change_pct": round(pct, 2)})
    if not rows:
        return {"available": False, "reason": "腾讯大宗商品行情取数失败"}
    return {"available": True, "items": rows}


def forex() -> dict:
    """汇率快照：涨跌幅取腾讯直接给的 % 字段。"""
    raw = _fetch([s for s, _ in _FOREX])
    rows = []
    for sym, name in _FOREX:
        f = raw.get(sym)
        if not f or len(f) <= _FX_PCT:
            continue
        price, pct = _num(f[_FX_PRICE]), _num(f[_FX_PCT])
        if price is None:
            continue
        rows.append({"name": name, "price": round(price, 4),
                     "change_pct": round(pct, 2) if pct is not None else None})
    if not rows:
        return {"available": False, "reason": "腾讯汇率行情取数失败"}
    return {"available": True, "items": rows}


def _treasury_latest_row() -> Optional[dict]:
    """财政部每日收益率曲线 CSV，返回最新一日的行 dict（列名 '1 Mo'..'30 Yr','Date'）。

    CSV 首行即最新日；跨年首几天当年 CSV 可能还没数据 → 回退到去年。取不到返回 None。
    """
    year = datetime.now(timezone.utc).year
    for y in (year, year - 1):
        url = (
            "https://home.treasury.gov/resource-center/data-chart-center/"
            f"interest-rates/daily-treasury-rates.csv/{y}/all"
            f"?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv"
        )
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            text = urllib.request.urlopen(req, timeout=12).read().decode("utf-8", "ignore")
        except Exception:  # noqa: BLE001  超时/网络问题 → 试下一个年份或降级
            continue
        rows = list(csv.DictReader(io.StringIO(text)))
        if rows:
            return rows[0]
    return None


def rates() -> dict:
    """美债收益率曲线关键期限：2Y / 5Y / 10Y / 30Y（百分数）。"""
    row = _treasury_latest_row()
    if not row:
        return {"available": False, "reason": "美国财政部收益率曲线取数失败（可能超时）"}
    items = []
    for col, name in _TREASURY_TENORS:
        v = _num(row.get(col, ""))
        if v is not None:
            items.append({"name": name, "yield_pct": round(v, 2)})
    if not items:
        return {"available": False, "reason": "收益率曲线字段缺失"}
    return {"available": True, "date": str(row.get("Date", "")), "items": items}


def crypto() -> dict:
    """加密货币（BTC）：腾讯 gtimg 无靠谱现货 BTC 价（usBTC 是 ETF 不是币价），
    暂不可用降级占位——**不伪造**，前端如实显示暂不可用。"""
    return {"available": False, "reason": "暂无靠谱免费现货 BTC 数据源"}
