"""行情/K线工具封装：校验 → 调 research.astock → JSON 化 → 截断 ≤6000 字符。

零业务逻辑层；异常一律转 {"error": str}，由 MCP 框架回传 LLM。
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


def get_quote(codes: list[str]) -> dict:
    """实时行情快照。

    输入 A 股代码列表（如 ['600519', '000001']，6 位数字，自动识别沪深前缀），
    返回 {code: {name, price, change_pct, ...}} 映射；未知代码返回错误信息条目。
    仅展示数据，不构成任何投资建议。
    """
    try:
        return _clip(astock.tencent_quote(codes))
    except Exception as e:  # noqa: BLE001 — spike 约定：异常转 {"error": ...}
        return {"error": f"{type(e).__name__}: {e}"}


def get_kline(code: str, category: int = 4, offset: int = 60) -> dict:
    """K 线序列。

    code 为 6 位 A 股代码；category：4=日、5=周、6=月、11=60分钟；
    offset 为返回根数（默认 60）。返回 [{open/close/high/low/volume...}, ...]。
    依赖 mootdx 可选包，缺失时报错说明。
    仅展示数据，不构成任何投资建议。
    """
    try:
        return _clip(astock.kline(code, category=category, offset=offset))
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}
