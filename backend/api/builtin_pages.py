"""内置展示页 spec（ADR-0007 决策 1/3）。

两个 kind=builtin 固定页，create_app 时经 register_builtin_pages 幂等 upsert 入库：
  correlation   相关性分析（三图：叠加走势 / 相关矩阵 / 滚动相关），analysis_ref 走白名单
  backtest      回测（指标 + 净值 + 回撤），支持多策略

注：盘面数据 / 每日复盘 / 涨停样本统计已改由前端直连专用端点
（/api/indices、/api/market/*、/api/backtest），不再走 page-spec render，
故对应 builtin spec 与 alpha.market / alpha.review 分析函数已移除。

import alpha.factor 触发 correlation.* 注册（注册在模块 import 副作用里），
否则 upsert_builtin_page → validate_spec 会因 fn 未在白名单而拒收。
"""

from __future__ import annotations

from typing import Any

import alpha.backtest_page  # noqa: F401 —— 触发 backtest.* 注册
import alpha.factor  # noqa: F401 —— 触发 correlation.* 注册
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
        {"name": "strategy", "type": "enum", "label": "策略", "default": "dual_ma",
         "choices": ["dual_ma"]},
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
    BACKTEST_SPEC,
)


def register_builtin_pages(store: Store) -> None:
    """幂等注册内置页：按 slug upsert（kind=builtin、status=published）。"""
    for spec in _BUILTIN_SPECS:
        store.pages.upsert_builtin_page(spec)
