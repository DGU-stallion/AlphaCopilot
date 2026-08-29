#!/usr/bin/env python3
"""G1 spike 专用最小 MCP server —— 只挂 get_quote，验证连通性。

现有 packages/dsh-alphacopilot-research/server.py 引用了尚未落地的 events 工具
（T11 未完成），会 import 失败。spike 只需验证「MCP server 可独立连通、
get_quote 工具可发现、（有网时）可调用」这一机制，因此这里用最小 server 隔离出
该验证面，不触碰现有产品代码。

T33 落地正式 run_python / MCP 时以此为参照，届时补齐 events 等工具。
"""

import json
import sys
from pathlib import Path

# 数据层：backend/research
_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO / "backend"))

from mcp.server.fastmcp import FastMCP

from research import astock

mcp = FastMCP("alphacopilot-research-g1")

_MAX_CHARS = 6000


def get_quote(codes: list[str]) -> dict:
    """实时行情快照。

    输入 A 股代码列表（如 ['600519']，6 位数字，自动识别沪深前缀），
    返回 {code: {name, price, change_pct, ...}} 映射。仅展示数据，不构成投资建议。
    """
    try:
        result = astock.tencent_quote(codes)
        text = json.dumps(result, ensure_ascii=False, default=str)
        if len(text) <= _MAX_CHARS:
            return {"data": result}
        return {"truncated": True, "head": text[:_MAX_CHARS]}
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


mcp.tool()(get_quote)


if __name__ == "__main__":
    mcp.run()
