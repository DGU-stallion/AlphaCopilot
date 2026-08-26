"""资金面工具封装：校验 → 调 research.astock → JSON 化 → 截断 ≤6000 字符。

零业务逻辑层；异常一律转 {"error": str}，由 MCP 框架回传 LLM。
覆盖：dragon_tiger_board / block_trade / holder_num_change / dividend_history。
"""

import json

from research import astock

_MAX_CHARS = 6000


def _clip(result) -> dict:
    """JSON 化并截断到 ≤6000 字符（超长时保留头部并附截断标记）。"""
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) <= _MAX_CHARS:
        return {"data": result}
    return {"truncated": True, "max_chars": _MAX_CHARS, "head": text[:_MAX_CHARS]}


def get_dragon_tiger(code: str, trade_date: str | None = None) -> dict:
    """龙虎榜上榜记录与席位净买。

    code 为 6 位 A 股代码；trade_date 为 YYYY-MM-DD（默认最近交易日）。
    仅展示数据，不构成任何投资建议。
    """
    try:
        return _clip(astock.dragon_tiger_board(code, trade_date=trade_date))
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def get_block_trade(code: str) -> dict:
    """大宗交易记录（成交价、折溢价、买卖双方）。

    code 为 6 位 A 股代码。仅展示数据。
    """
    try:
        return _clip(astock.block_trade(code))
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def get_holder_changes(code: str) -> dict:
    """股东户数变化趋势（筹码集中度指标）。

    code 为 6 位 A 股代码；依赖 akshare 可选包。仅展示数据。
    """
    try:
        return _clip(astock.holder_num_change(code))
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def get_dividend_history(code: str) -> dict:
    """分红历史（方案、除权日、股息率）。

    code 为 6 位 A 股代码。仅展示数据，不构成任何投资建议。
    """
    try:
        return _clip(astock.dividend_history(code))
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}
