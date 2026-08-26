"""注册所有 MCP 工具。

每工具对应一个 tools 子模块的顶层函数；MCP 层保持零业务逻辑。
"""

import sys
from pathlib import Path

# 开发期：直接把 monorepo 的 backend/ 目录塞进 import 路径；发布期改为正式依赖
_BACKEND = Path(__file__).resolve().parents[4] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from mcp.server.fastmcp import FastMCP

from alphacopilot_research.tools import events, fundamental, flows, quote

mcp = FastMCP("alphacopilot-research")

# 行情（2）
mcp.tool()(quote.get_quote)
mcp.tool()(quote.get_kline)

# 基本面（2）
mcp.tool()(fundamental.get_valuation)
mcp.tool()(fundamental.get_financials)

# 资金面（4）
mcp.tool()(fundamental.get_margin_trading)
mcp.tool()(fundamental.get_fund_flow)
mcp.tool()(flows.get_dragon_tiger)
mcp.tool()(flows.get_block_trade)
mcp.tool()(flows.get_holder_changes)
mcp.tool()(flows.get_dividend_history)

# 资讯/事件（2）
mcp.tool()(events.get_news)
mcp.tool()(events.get_announcements)
mcp.tool()(events.get_radar)


def main() -> None:
    """入口点：供 [project.scripts] 使用，便于测试与调试。"""
    mcp.run()


if __name__ == "__main__":
    main()
