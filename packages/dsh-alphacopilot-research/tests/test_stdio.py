"""独立连通性测试：不经 dsh，直接 stdio spawn 本 server。

网络依赖：get_quote 走腾讯 gtimg 接口，需外网；失败时输出原始错误，
标注网络原因也算有效结论。
"""

import json
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = StdioServerParameters(
    command=sys.executable,
    args=["-m", "alphacopilot_research.server"],
)


async def _list_tools():
    async with (
        stdio_client(SERVER) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        return await session.list_tools()


async def _call_quote():
    async with (
        stdio_client(SERVER) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        return await session.call_tool("get_quote", {"codes": ["600519"]})


@pytest.mark.asyncio
async def test_list_tools_contains_both():
    tools = await _list_tools()
    names = {t.name for t in tools.tools}
    assert {"get_quote", "get_kline"} <= names


@pytest.mark.asyncio
async def test_call_get_quote_moutai():
    result = await _call_quote()
    assert not result.isError, f"call_tool 报错: {result.content}"
    payload = json.loads(result.content[0].text)
    data = payload.get("data", {})
    assert "600519" in data, f"返回缺 600519: {payload}"
    entry = data["600519"]
    assert "贵州茅台" in str(entry.get("name", "")), f"名称不符: {entry}"
    assert "price" in entry, f"缺 price 字段: {entry}"
