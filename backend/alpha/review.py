"""alpha.review —— 每日复盘分析（ADR-0007 内置页 daily-review）。

产出 markdown block：A 股大盘指数 + 全球指数一屏概览。数据源用 HTTP 可达的
research.astock.index_quote（腾讯 gtimg）与 research.market.get_global_indices，
任一源不可用时优雅降级为「暂不可用」提示，不崩。

注册进 alpha.registry 白名单，供 page spec 的 analysis_ref.fn 引用。
"""

from __future__ import annotations

from typing import Any

from alpha.registry import register
from research import astock, market


def _fmt_pct(v: Any) -> str:
    try:
        f = float(v)
        sign = "+" if f > 0 else ""
        return f"{sign}{f:.2f}%"
    except (TypeError, ValueError):
        return "—"


@register("daily_review.summary", params=[])
def daily_review_summary() -> dict:
    """每日复盘概览，返回 markdown block payload（{text}）。

    内容：A 股大盘指数（上证/深证/创业板/沪深300）+ 全球主要指数。
    只陈述客观行情，不做买卖建议。数据源不可用的段落显示占位。
    """
    lines: list[str] = ["## 每日复盘", ""]

    # A 股大盘指数（腾讯 gtimg，HTTP 可达）。
    lines.append("### A 股大盘")
    try:
        indices = astock.index_quote()
    except Exception:  # noqa: BLE001
        indices = []
    if indices:
        lines.append("")
        lines.append("| 指数 | 最新 | 涨跌幅 |")
        lines.append("|---|---:|---:|")
        for it in indices:
            name = it.get("name", "—")
            price = it.get("price", "—")
            pct = _fmt_pct(it.get("change_pct"))
            lines.append(f"| {name} | {price} | {pct} |")
    else:
        lines.append("")
        lines.append("> 大盘指数暂不可用（非交易时段或数据源暂时不可达）。")

    # 全球主要指数（可用则展示，不可用降级）。
    lines.append("")
    lines.append("### 全球市场")
    try:
        gidx = market.get_global_indices()
    except Exception:  # noqa: BLE001
        gidx = []
    if gidx:
        lines.append("")
        lines.append("| 指数 | 最新 | 涨跌幅 |")
        lines.append("|---|---:|---:|")
        for it in gidx:
            name = it.get("name", "—")
            price = it.get("price", it.get("value", "—"))
            pct = _fmt_pct(it.get("change_pct", it.get("pct")))
            lines.append(f"| {name} | {price} | {pct} |")
    else:
        lines.append("")
        lines.append("> 全球指数暂不可用。")

    lines.append("")
    lines.append("---")
    lines.append("*以上为客观行情数据，不构成投资建议。*")

    return {"text": "\n".join(lines)}
