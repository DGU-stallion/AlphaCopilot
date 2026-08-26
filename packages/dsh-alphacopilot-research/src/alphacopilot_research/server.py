"""FastMCP stdio server: AlphaCopilot research 数据层 → dsh 工具。

运行方式：python -m alphacopilot_research.server（stdio transport）。
dsh patch 层 loader entry 指向本模块，工具公开名为
mcp__alphacopilot-research__<tool>。
"""

import sys
from pathlib import Path

# TODO(T08): 正式引用方式 —— 发布期改为对本地数据层的常规依赖
# （alphacopilot-research 包），移除 sys.path 注入；spike 从简，
# 直接把 monorepo 的 backend/ 目录塞进 import 路径。
_BACKEND = Path(__file__).resolve().parents[4] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from mcp.server.fastmcp import FastMCP

from alphacopilot_research.tools import quote

mcp = FastMCP("alphacopilot-research")

get_quote = mcp.tool()(quote.get_quote)
get_kline = mcp.tool()(quote.get_kline)


if __name__ == "__main__":
    mcp.run()
