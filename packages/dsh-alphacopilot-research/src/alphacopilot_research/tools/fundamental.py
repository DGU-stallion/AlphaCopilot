"""基本面/资金面工具封装：校验 → 调 research.astock → JSON 化 → 截断 ≤6000 字符。

零业务逻辑层；异常一律转 {"error": str}，由 MCP 框架回传 LLM。
覆盖：valuation / financials / margin_trading / stock_fund_flow_120d。
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


def get_valuation(code: str) -> dict:
    """单股完整估值（行情 + 一致预期 EPS + 前向 PE/PEG/PE 消化年数）。

    code 为 6 位 A 股代码。仅展示数据，不构成任何投资建议。
    """
    try:
        return _clip(astock.full_valuation(code))
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def get_financials(code: str) -> dict:
    """财务三表核心指标（营收/净利增速、ROE/ROIC、现金流、负债率）。

    code 为 6 位 A 股代码。仅展示数据，不构成任何投资建议。
    """
    try:
        return _clip(astock.financials(code))
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def get_margin_trading(code: str) -> dict:
    """融资融券余额与趋势（两融余额、融资净买入、融券余量）。

    code 为 6 位 A 股代码；依赖 akshare 可选包。仅展示数据。
    """
    try:
        return _clip(astock.margin_trading(code))
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def get_fund_flow(code: str) -> dict:
    """主力资金流向近 120 日（机构/游资/散户净流入、超大单/大单占比）。

    code 为 6 位 A 股代码。仅展示数据，不构成任何投资建议。
    """
    try:
        return _clip(astock.stock_fund_flow_120d(code))
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}
