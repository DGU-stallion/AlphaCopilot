"""mcpserver — 我们的 MCP server：run_python / publish_artifact / create_page / search_docs。

工具层零业务逻辑：校验 → 调 alpha.* → JSON 化 → 截断 ≤6000 字符。

命名说明：目录名用 mcpserver 而非 PLAN/AGENTS 里概念上的 "mcp"，因为顶层包名 `mcp`
会与我们依赖的 PyPI `mcp` SDK（本 server 自身要 `from mcp.server.fastmcp import FastMCP`）
发生 import 遮蔽冲突。概念仍称 "MCP 层"，包名为 mcpserver。
"""
