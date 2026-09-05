"""内置展示页 spec（T45，ADR-0007 决策 1/3）。

两个 kind=builtin 固定页，create_app 时经 register_builtin_pages 幂等 upsert 入库：
  correlation   相关性分析（三图：叠加走势 / 相关矩阵 / 滚动相关），analysis_ref 走白名单
  daily-review  每日复盘（先 markdown 占位，避免依赖未注册 fn；定时刷新待后续任务）

import alpha.factor 触发 correlation.* 注册（注册在模块 import 副作用里），
否则 upsert_builtin_page → validate_spec 会因 fn 未在白名单而拒收。
"""

from __future__ import annotations

from typing import Any

import alpha.backtest_page  # noqa: F401 —— 触发 backtest.* 注册
import alpha.factor  # noqa: F401 —— 触发 correlation.* 注册
import alpha.market  # noqa: F401 —— 触发 market.* / limit_up.* 注册
import alpha.review  # noqa: F401 —— 触发 daily_review.summary 注册
from api.store import Store

CORRELATION_SPEC: dict[str, Any] = {
    "slug": "correlation",
    "title": "相关性分析",
    "kind": "builtin",
    "status": "published",
    "layout": "grid",
    "params": [
        {
            "name": "symbols",
            "type": "symbol_list",
            "label": "标的",
            "default": ["600519", "000858", "000568", "002304"],
            "max": 8,
        },
        {"name": "window", "type": "int", "label": "滚动窗口", "default": 60, "min": 5, "max": 250},
        {"name": "range", "type": "date_range", "label": "区间", "default": "1y"},
    ],
    "blocks": [
        {"kind": "chart", "span": 2, "analysis_ref": {"fn": "correlation.overlay"}},
        {"kind": "chart", "span": 1, "analysis_ref": {"fn": "correlation.matrix"}},
        {"kind": "chart", "span": 1, "analysis_ref": {"fn": "correlation.rolling"}},
    ],
    "refresh": {"mode": "manual"},
}

DAILY_REVIEW_SPEC: dict[str, Any] = {
    "slug": "daily-review",
    "title": "每日复盘",
    "kind": "builtin",
    "status": "published",
    "layout": "stack",
    "blocks": [
        {"kind": "markdown", "span": 3, "analysis_ref": {"fn": "daily_review.summary"}},
    ],
    "refresh": {"mode": "on_open"},
}

MARKET_SPEC: dict[str, Any] = {
    "slug": "market",
    "title": "盘面数据",
    "kind": "builtin",
    "status": "published",
    "layout": "grid",
    "blocks": [
        {"kind": "metric", "span": 3, "analysis_ref": {"fn": "market.breadth"}},
        {"kind": "table", "span": 1, "analysis_ref": {"fn": "market.index"}},
        {"kind": "table", "span": 2, "analysis_ref": {"fn": "market.turnover"}},
    ],
    "refresh": {"mode": "on_open"},
}

LIMIT_UP_STATS_SPEC: dict[str, Any] = {
    "slug": "limit-up-stats",
    "title": "涨停样本统计",
    "kind": "builtin",
    "status": "published",
    "layout": "grid",
    "blocks": [
        {"kind": "metric", "span": 3, "analysis_ref": {"fn": "limit_up.summary"}},
        {"kind": "chart", "span": 2, "analysis_ref": {"fn": "limit_up.ladder"}},
        {"kind": "table", "span": 1, "analysis_ref": {"fn": "limit_up.industry"}},
    ],
    "refresh": {"mode": "on_open"},
}

BACKTEST_SPEC: dict[str, Any] = {
    "slug": "backtest",
    "title": "回测",
    "kind": "builtin",
    "status": "published",
    "layout": "grid",
    "params": [
        {"name": "symbol", "type": "str", "label": "标的", "default": "600519"},
        {"name": "fast", "type": "int", "label": "快线", "default": 20, "min": 2, "max": 120},
        {"name": "slow", "type": "int", "label": "慢线", "default": 60, "min": 3, "max": 250},
        {"name": "range", "type": "date_range", "label": "区间", "default": "1y"},
    ],
    "blocks": [
        {"kind": "metric", "span": 3, "analysis_ref": {"fn": "backtest.metrics"}},
        {"kind": "chart", "span": 2, "analysis_ref": {"fn": "backtest.equity"}},
        {"kind": "chart", "span": 1, "analysis_ref": {"fn": "backtest.drawdown"}},
    ],
    "refresh": {"mode": "manual"},
}

_BUILTIN_SPECS = (
    CORRELATION_SPEC,
    DAILY_REVIEW_SPEC,
    MARKET_SPEC,
    LIMIT_UP_STATS_SPEC,
    BACKTEST_SPEC,
)


def register_builtin_pages(store: Store) -> None:
    """幂等注册内置页：按 slug upsert（kind=builtin、status=published）。"""
    for spec in _BUILTIN_SPECS:
        store.pages.upsert_builtin_page(spec)
