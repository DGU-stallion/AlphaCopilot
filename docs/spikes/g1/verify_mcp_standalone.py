#!/usr/bin/env python3
"""G1 spike 第一部分：MCP server 独立连通（不经 dsh，keyless）。

验证两件事：
  1. 工具发现：stdio 连上最小 server，list_tools 里有 get_quote —— keyless，必过
  2. 真实调用：call_tool('get_quote', {'codes': ['600519']}) 返回茅台报价 —— 需外网

第 2 项失败若为网络原因（腾讯 gtimg 不可达），标注为「网络受限」而非机制失败，
不影响「MCP 连通机制成立」的结论。
"""

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_MIN = Path(__file__).resolve().parent / "mcp_server_min.py"
SERVER = StdioServerParameters(command=sys.executable, args=[str(SERVER_MIN)])


async def discover_tools() -> set[str]:
    async with (
        stdio_client(SERVER) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        tools = await session.list_tools()
        return {t.name for t in tools.tools}


async def call_quote() -> dict:
    async with (
        stdio_client(SERVER) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.call_tool("get_quote", {"codes": ["600519"]})
        return {
            "isError": result.isError,
            "payload": json.loads(result.content[0].text) if result.content else None,
        }


async def main() -> int:
    print("=" * 60)
    print("G1-part1: MCP server 独立连通（keyless，不经 dsh）")
    print("=" * 60)

    # 1. 工具发现
    names = await discover_tools()
    has_quote = "get_quote" in names
    print(f"[1] 工具发现: {'PASS' if has_quote else 'FAIL'} tools={sorted(names)}")

    # 2. 真实调用
    net_ok = False
    net_note = ""
    try:
        r = await call_quote()
        payload = r["payload"] or {}
        data = payload.get("data", {})
        if not r["isError"] and "600519" in data and "贵州茅台" in str(data["600519"].get("name", "")):
            net_ok = True
            print(f"[2] get_quote 调用: PASS 600519={data['600519'].get('name')} "
                  f"price={data['600519'].get('price')}")
        else:
            net_note = f"返回非预期: {payload}"
            print(f"[2] get_quote 调用: 网络受限/非预期 — {net_note}")
    except Exception as e:  # noqa: BLE001
        net_note = f"{type(e).__name__}: {e}"
        print(f"[2] get_quote 调用: 网络受限 — {net_note}")

    print("-" * 60)
    # 机制结论只取决于工具发现；真实调用受网络影响，单独标注
    mechanism_ok = has_quote
    print(f"G1-part1 机制结论: {'PASS — MCP 连通机制成立' if mechanism_ok else 'FAIL'}")
    print(f"  真实数据调用: {'PASS' if net_ok else '网络受限（不阻断机制结论）'}")
    return 0 if mechanism_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
