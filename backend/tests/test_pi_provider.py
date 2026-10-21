"""PiProvider 契约测试（M1-1）—— 先红，驱动 M1-2 的实现。

## 为什么先写契约测试

Pi 走 `pi --mode rpc` 子进程，协议是 **JSONL over stdio**（官方文档 rpc.md / json.md）。
这条边界最容易出的 bug 不是崩溃，而是**字段名弄错后静默丢事件**——
agent 看起来「变笨了」，但没有任何测试会红。所以这里不测「能跑通」，
而是**逐字段断言**每类中立事件都被正确映射。

## seam

外层 seam 是 `agent.provider.AgentProvider`（start / astream / close / is_alive）——
业务层只认它，不认 Pi。这些测试全部通过该 Protocol 观察行为，不碰 PiProvider 的
任何私有方法，因此实现可以整个重写而测试不变。

内层 seam 是**子进程边界**。这里用一个假 pi 脚本顶替真 `pi` 二进制：
它按真实协议读 stdin 命令、往 stdout 写 JSONL 记录。这让我们能在无模型、
无 key、无网络的情况下断言协议映射，且测试跑在毫秒级。

## 协议事实来源（不要在实现时「凭印象」改）

- `docs/rpc.md`（pi 1.3.0）：命令 `{"id","type":"prompt","message"}` →
  `{"id","type":"response","command":"prompt","success":true,"data":{"disposition":"started"}}`
- `docs/json.md`：
  - 文本增量：`{"type":"message_update","assistantMessageEvent":{"type":"text_delta","contentIndex":0,"delta":"..."}}`
  - 工具开始：`{"type":"tool_execution_start","toolCallId","toolName","args"}`
  - 工具结束：`{"type":"tool_execution_end","toolCallId","toolName","result","isError"}`
  - 一轮结束：`{"type":"agent_settled","aborted":false}`
- 不要等 `agent_end` 就判定结束：retry / compaction / steering 可能还在后面。
  必须是 `agent_settled`。
"""

from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

import pytest

from agent.provider import (
    EVENT_ERROR,
    EVENT_TEXT_DELTA,
    EVENT_TOOL_RESULT,
    EVENT_TOOL_STARTED,
    EVENT_TURN_END,
    AgentProvider,
    McpServerSpec,
    ProviderSpec,
)

pytestmark = pytest.mark.asyncio


# --------------------------------------------------------------------------
# 假 pi 进程：按真实 JSONL 协议说话
# --------------------------------------------------------------------------

# 剧本通过环境变量传给假 pi，避免为每个场景生成一个文件。
_SCRIPT_HEADER = '''\
import json, os, sys

SCRIPT = json.loads(os.environ["FAKE_PI_SCRIPT"])
out = sys.stdout
out.reconfigure(encoding="utf-8", newline="\\n")


def emit(record):
    out.write(json.dumps(record, ensure_ascii=False) + "\\n")
    out.flush()


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        cmd = json.loads(line)
    except json.JSONDecodeError:
        emit({"type": "response", "command": "parse", "success": False,
              "error": "Failed to parse command"})
        continue

    cid = cmd.get("id")
    if cmd.get("type") != "prompt":
        # get_state 等：回一个成功响应，证明命令相关性可用
        emit({"id": cid, "type": "response", "command": cmd.get("type"),
              "success": True, "data": {}})
        continue

    emit({"id": cid, "type": "response", "command": "prompt",
          "success": True, "data": {"disposition": "started"}})

    for record in SCRIPT:
        # 剧本可声明 exit_after / raise_stderr 等特殊动作
        if record.get("__action__") == "exit":
            sys.exit(record.get("code", 1))
        emit(record)
'''


def _write_fake_pi(dirpath: Path, script: list[dict]) -> Path:
    """把假 pi 写成可执行脚本，返回路径。"""
    path = dirpath / "fake_pi.py"
    path.write_text(_SCRIPT_HEADER, encoding="utf-8")
    return path


def _spec(tmp: Path, fake_pi: Path, script: list[dict], **kw) -> tuple[ProviderSpec, dict]:
    """构造 ProviderSpec + 环境变量。"""
    from agent.providers.pi import PiProvider  # noqa: F401  (M1-2 前应 ImportError)

    ws = tmp / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    spec = ProviderSpec(
        workspace=ws,
        system_prompt="测试用合规 persona。",
        mcp_servers=[McpServerSpec(name="ac", command="python3", args=["-m", "mcpserver"])],
        request_timeout_seconds=30.0,
        **kw,
    )
    env = {
        "FAKE_PI_SCRIPT": __import__("json").dumps(script, ensure_ascii=False),
        "FAKE_PI_EXECUTABLE": str(fake_pi),
        "PYTHON": sys.executable,
    }
    return spec, env


async def _collect(provider: AgentProvider, prompt: str) -> list:
    """消费整轮事件，返回列表（不在此处断言，便于逐条检查）。"""
    events = []
    async for ev in provider.astream(prompt):
        events.append(ev)
    return events


# 剧本：一段文本 + 一次工具调用 + 正常结束
_BASIC_SCRIPT = [
    {"type": "message_start"},
    {
        "type": "message_update",
        "usage": {"input": 10, "output": 3, "totalTokens": 13},
        "assistantMessageEvent": {"type": "text_delta", "contentIndex": 0, "delta": "白酒"},
    },
    {
        "type": "message_update",
        "usage": {"input": 10, "output": 3, "totalTokens": 13},
        "assistantMessageEvent": {"type": "text_delta", "contentIndex": 0, "delta": "是消费龙头。"},
    },
    {"type": "tool_execution_start", "toolCallId": "c1", "toolName": "get_quote",
     "args": {"code": "600519"}},
    {"type": "tool_execution_end", "toolCallId": "c1", "toolName": "get_quote",
     "result": {"content": [{"type": "text", "text": "1331.88"}], "details": {}},
     "isError": False},
    {"type": "message_end"},
    {"type": "agent_end", "messages": [], "willRetry": False},
    {"type": "agent_settled", "aborted": False},
]


# --------------------------------------------------------------------------
# 契约：5 类中立事件
# --------------------------------------------------------------------------


async def test_text_delta_is_mapped_with_delta_text(tmp_path):
    """`message_update.assistantMessageEvent.delta` → `AgentEvent.payload["text"]`。

    断言 payload 的具体键，而不只是 kind——字段名写错时事件会「在但为空」，
    kind 断言抓不到这种 bug。
    """
    spec, env = _spec(tmp_path, _write_fake_pi(tmp_path, _BASIC_SCRIPT), _BASIC_SCRIPT)
    from agent.providers.pi import PiProvider

    p = PiProvider(spec, executable=env["FAKE_PI_EXECUTABLE"], env=env)
    await _collect_async_start(p)
    try:
        events = await _collect(p, "白酒板块怎么样？")
    finally:
        p.close()

    deltas = [e for e in events if e.kind == EVENT_TEXT_DELTA]
    assert [e.payload["text"] for e in deltas] == ["白酒", "是消费龙头。"], (
        f"text_delta 的 payload['text'] 未正确取自 delta 字段；实际："
        f"{[e.payload for e in deltas]}"
    )


async def test_tool_started_and_result_are_mapped(tmp_path):
    """`tool_execution_start/end` → `tool_started` / `tool_result`。

    payload 必须带 `name`（业务层靠它识别是哪个工具），result 带原始 result。
    """
    spec, env = _spec(tmp_path, _write_fake_pi(tmp_path, _BASIC_SCRIPT), _BASIC_SCRIPT)
    from agent.providers.pi import PiProvider

    p = PiProvider(spec, executable=env["FAKE_PI_EXECUTABLE"], env=env)
    await _collect_async_start(p)
    try:
        events = await _collect(p, "查茅台报价")
    finally:
        p.close()

    started = [e for e in events if e.kind == EVENT_TOOL_STARTED]
    assert len(started) == 1, f"期望 1 个 tool_started，实际 {len(started)}"
    assert started[0].payload["name"] == "get_quote", (
        f"payload['name'] 应取 toolName；实际 {started[0].payload}"
    )
    assert started[0].payload["args"] == {"code": "600519"}

    results = [e for e in events if e.kind == EVENT_TOOL_RESULT]
    assert len(results) == 1
    assert results[0].payload["name"] == "get_quote"
    assert "1331.88" in str(results[0].payload["result"])


async def test_turn_end_carries_accumulated_final_text(tmp_path):
    """`agent_settled` → `turn_end`，且 `final_text` 是整轮文本的拼接。

    业务层（和前端）靠 `turn_end.final_text` 落库整条回复，所以它必须是
    **累积**的完整文本，不是最后一段 delta。
    """
    spec, env = _spec(tmp_path, _write_fake_pi(tmp_path, _BASIC_SCRIPT), _BASIC_SCRIPT)
    from agent.providers.pi import PiProvider

    p = PiProvider(spec, executable=env["FAKE_PI_EXECUTABLE"], env=env)
    await _collect_async_start(p)
    try:
        events = await _collect(p, "白酒板块怎么样？")
    finally:
        p.close()

    ends = [e for e in events if e.kind == EVENT_TURN_END]
    assert len(ends) == 1, f"必须且只能有一个 turn_end，实际 {len(ends)}"
    assert ends[0].payload["final_text"] == "白酒是消费龙头。", (
        f"final_text 应为累积全文；实际 {ends[0].payload.get('final_text')!r}"
    )
    # turn_end 必须是最后一个事件
    assert events[-1].kind == EVENT_TURN_END, (
        f"turn_end 必须在末尾，实际末尾是 {events[-1].kind}"
    )


async def test_agent_end_alone_does_not_finish_the_turn(tmp_path):
    """只发 `agent_end` 不发 `agent_settled` 时，不得提前收尾。

    这是最容易写错的地方：`agent_end` 只代表「一次底层 run 结束」，
    后面还可能跟 retry / compaction / steering。等错了会截断回复。
    """
    script = [
        {"type": "message_update",
         "assistantMessageEvent": {"type": "text_delta", "contentIndex": 0, "delta": "前半"}},
        {"type": "agent_end", "messages": [], "willRetry": False},
        # —— 没有 agent_settled ——
        {"type": "message_update",
         "assistantMessageEvent": {"type": "text_delta", "contentIndex": 0, "delta": "后半"}},
        {"type": "agent_settled", "aborted": False},
    ]
    spec, env = _spec(tmp_path, _write_fake_pi(tmp_path, script), script)
    from agent.providers.pi import PiProvider

    p = PiProvider(spec, executable=env["FAKE_PI_EXECUTABLE"], env=env)
    await _collect_async_start(p)
    try:
        events = await _collect(p, "x")
    finally:
        p.close()

    texts = [e.payload["text"] for e in events if e.kind == EVENT_TEXT_DELTA]
    assert texts == ["前半", "后半"], (
        f"在 agent_end 处提前收尾会丢掉 agent_end 之后的事件；实际 {texts}"
    )
    ends = [e for e in events if e.kind == EVENT_TURN_END]
    assert ends[0].payload["final_text"] == "前半后半"


async def test_aborted_settle_reports_finish_reason(tmp_path):
    """`agent_settled.aborted = true` → `turn_end.finish_reason = "aborted"`。

    前端要据此把「用户主动停止」与「正常说完」区分开，否则停止后界面显示
    一句像正常结束的话。
    """
    script = [
        {"type": "message_update",
         "assistantMessageEvent": {"type": "text_delta", "contentIndex": 0, "delta": "说到一半"}},
        {"type": "agent_settled", "aborted": True},
    ]
    spec, env = _spec(tmp_path, _write_fake_pi(tmp_path, script), script)
    from agent.providers.pi import PiProvider

    p = PiProvider(spec, executable=env["FAKE_PI_EXECUTABLE"], env=env)
    await _collect_async_start(p)
    try:
        events = await _collect(p, "x")
    finally:
        p.close()

    ends = [e for e in events if e.kind == EVENT_TURN_END]
    assert len(ends) == 1
    assert ends[0].payload["finish_reason"] == "aborted", (
        f"aborted 未映射到 finish_reason；实际 {ends[0].payload}"
    )
    assert ends[0].payload["final_text"] == "说到一半", "被中断时也应保留已收到的文本"


# --------------------------------------------------------------------------
# 契约：进程生命周期
# --------------------------------------------------------------------------


async def test_close_is_idempotent_and_reaps_process(tmp_path):
    """close() 幂等；调用后 is_alive() 为 False（进程不泄漏）。"""
    spec, env = _spec(tmp_path, _write_fake_pi(tmp_path, _BASIC_SCRIPT), _BASIC_SCRIPT)
    from agent.providers.pi import PiProvider

    p = PiProvider(spec, executable=env["FAKE_PI_EXECUTABLE"], env=env)
    await _collect_async_start(p)
    assert p.is_alive() is True, "start 后应存活"

    await _collect(p, "x")
    p.close()
    p.close()  # 幂等：第二次不得抛
    assert p.is_alive() is False, "close 后应已回收"


async def test_provider_satisfies_the_protocol(tmp_path):
    """PiProvider 必须满足 AgentProvider Protocol（业务层只认它）。"""
    spec, env = _spec(tmp_path, _write_fake_pi(tmp_path, _BASIC_SCRIPT), _BASIC_SCRIPT)
    from agent.providers.pi import PiProvider

    p = PiProvider(spec, executable=env["FAKE_PI_EXECUTABLE"], env=env)
    assert isinstance(p, AgentProvider), (
        "PiProvider 未满足 AgentProvider Protocol——业务层会无法通过中立接口使用它"
    )
    await _collect_async_start(p)
    try:
        await _collect(p, "x")
    finally:
        p.close()


# --------------------------------------------------------------------------
# 辅助：start 是同步阻塞的（起子进程），放到线程里避免卡事件循环
# --------------------------------------------------------------------------


async def _collect_async_start(provider) -> None:
    import asyncio

    await asyncio.to_thread(provider.start)
