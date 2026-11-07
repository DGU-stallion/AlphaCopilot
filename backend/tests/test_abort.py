"""中止一轮 turn 的契约测试（M1-4）—— 先红。

## 为什么要测这个

「停止生成」是聊天界面的基本能力，也是最容易做得**看起来能用但实际没停**的地方：
前端断了 SSE、按钮变灰，但子进程还在跑、模型还在花钱、消息最后照旧落库。
用户以为停了，agent 以为没人拦它。

所以这里测的不是「有个 abort 方法」，而是三个可观察后果：
1. 事件流以 `turn_end` 结束且 `finish_reason == "aborted"`
2. 已收到的文本仍然落库（不能因为中止就丢掉半句回复）
3. 中止之后这个会话还能继续用（不是一停就废）

## seam

契约层：`AgentProvider.abort()`。这是 provider 必须提供的能力，
业务层（`SessionManager`）和 HTTP 层（`POST /sessions/{id}/abort`）都只经它。
两个 adapter（假 pi / 真 pi）都要满足同一契约。

HTTP 层：`POST /sessions/{sid}/abort` 返回 2xx。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from agent.provider import (
    EVENT_TEXT_DELTA,
    EVENT_TURN_END,
    AgentProvider,
    ProviderSpec,
)

_asyncio = pytest.mark.asyncio


# 假 pi：收到 prompt 后先吐一段，然后**一直挂着**直到 stdin 被关或收到 abort。
# 这样才能真实模拟「模型正在生成时用户点了停止」。
_SLOW_PI = '''\
import json, sys

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
        continue

    cid = cmd.get("id")
    ctype = cmd.get("type")

    if ctype == "abort":
        # 真实的 pi 收到 abort 后会以 aborted=true 的 agent_settled 收尾
        emit({"id": cid, "type": "response", "command": "abort", "success": True, "data": {}})
        emit({"type": "agent_settled", "aborted": True})
        continue

    if ctype != "prompt":
        emit({"id": cid, "type": "response", "command": ctype, "success": True, "data": {}})
        continue

    emit({"id": cid, "type": "response", "command": "prompt",
          "success": True, "data": {"disposition": "started"}})
    emit({"type": "message_update",
          "assistantMessageEvent": {"type": "text_delta", "contentIndex": 0,
                                    "delta": "说到一半"}})
    # 不主动结束：等 abort 命令（或 stdin EOF）
'''


def _slow_pi(tmp_path: Path) -> str:
    path = tmp_path / "slow_pi.py"
    path.write_text(f"#!{sys.executable}\n" + _SLOW_PI, encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def _spec(tmp_path: Path) -> ProviderSpec:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    return ProviderSpec(workspace=ws, system_prompt="测试。", request_timeout_seconds=30.0)


async def _start(p) -> None:
    await asyncio.to_thread(p.start)


@_asyncio
async def test_abort_ends_turn_with_aborted_finish_reason(tmp_path):
    """abort() 之后，流必须以 `turn_end(finish_reason="aborted")` 收尾。"""
    from agent.providers.pi import PiProvider

    p = PiProvider(_spec(tmp_path), executable=_slow_pi(tmp_path))
    await _start(p)

    try:
        events: list = []

        async def consume():
            async for ev in p.astream("慢慢说"):
                events.append(ev)

        task = asyncio.create_task(consume())
        # 等第一个 delta 到（证明 turn 真的在跑），再中止
        await _wait_until(lambda: any(e.kind == EVENT_TEXT_DELTA for e in events))
        p.abort("用户点了停止")
        await asyncio.wait_for(task, timeout=10)

        kinds = [e.kind for e in events]
        assert EVENT_TEXT_DELTA in kinds, f"中止前应已收到文本；实际 {kinds}"

        ends = [e for e in events if e.kind == EVENT_TURN_END]
        assert len(ends) == 1, f"中止后应恰好一个 turn_end；实际 {len(ends)} 个"
        assert ends[0].payload["finish_reason"] == "aborted", (
            f"finish_reason 必须是 aborted（前端据此区分「用户停止」与「正常说完」）；"
            f"实际 {ends[0].payload}"
        )
    finally:
        p.close()


@_asyncio
async def test_abort_preserves_text_received_so_far(tmp_path):
    """中止时已收到的文本要保留在 `final_text` 里。

    用户按了停止，不等于「请把我说的话撤回」——半句回复应当留在界面上。
    丢掉它会让会话看起来像什么都没发生。
    """
    from agent.providers.pi import PiProvider

    p = PiProvider(_spec(tmp_path), executable=_slow_pi(tmp_path))
    await _start(p)

    try:
        events: list = []

        async def consume():
            async for ev in p.astream("慢慢说"):
                events.append(ev)

        task = asyncio.create_task(consume())
        await _wait_until(lambda: any(e.kind == EVENT_TEXT_DELTA for e in events))
        p.abort()
        await asyncio.wait_for(task, timeout=10)

        ends = [e for e in events if e.kind == EVENT_TURN_END]
        assert ends[0].payload["final_text"] == "说到一半", (
            f"已收到的文本必须保留；实际 {ends[0].payload.get('final_text')!r}"
        )
    finally:
        p.close()


@_asyncio
async def test_session_usable_after_abort(tmp_path):
    """中止后同一 provider 还能跑下一轮（不是一停就废）。

    这条防的是「abort 把进程杀了」这种简单粗暴的实现——它能让当前轮停下来，
    但会让会话在用户眼里直接死掉。
    """
    from agent.providers.pi import PiProvider

    p = PiProvider(_spec(tmp_path), executable=_slow_pi(tmp_path))
    await _start(p)

    try:
        events: list = []

        async def consume():
            async for ev in p.astream("第一轮"):
                events.append(ev)

        task = asyncio.create_task(consume())
        await _wait_until(lambda: any(e.kind == EVENT_TEXT_DELTA for e in events))
        p.abort()
        await asyncio.wait_for(task, timeout=10)

        assert p.is_alive(), "abort 不应杀掉进程"

        # 第二轮：只需证明「还能拿到正文」。假 pi 会再吐一段然后继续挂着
        # （模拟长时间生成），所以看到文本就主动跳出——不断言它自己收尾。
        second: list = []
        stream = p.astream("第二轮")
        try:
            async for ev in stream:
                second.append(ev)
                if ev.kind == EVENT_TEXT_DELTA:
                    break
        finally:
            await stream.aclose()

        assert any(e.kind == EVENT_TEXT_DELTA for e in second), (
            f"abort 后会话应仍可用（能再拿到正文）；第二轮收到 {[e.kind for e in second]}"
        )
    finally:
        p.close()


@_asyncio
async def test_abort_without_active_turn_is_harmless(tmp_path):
    """没有进行中的 turn 时 abort 不抛异常（幂等 / 可重入）。"""
    from agent.providers.pi import PiProvider

    p = PiProvider(_spec(tmp_path), executable=_slow_pi(tmp_path))
    await _start(p)
    try:
        p.abort()  # 不应抛
        assert p.is_alive()
    finally:
        p.close()


def test_protocol_declares_abort():
    """`AgentProvider` 契约里必须有 abort —— 业务层只认这个 Protocol。"""
    assert hasattr(AgentProvider, "abort"), (
        "AgentProvider 必须声明 abort()：中止能力是 provider 契约的一部分，"
        "不是 PiProvider 的私有扩展"
    )


async def _wait_until(pred, timeout: float = 10.0, interval: float = 0.02) -> None:
    """等条件成立，超时抛错。用于「等事件出现再动作」这类同步点。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if pred():
            return
        await asyncio.sleep(interval)
    raise AssertionError("等待条件超时")


# --------------------------------------------------------------------------
# HTTP 层：POST /sessions/{sid}/abort
# --------------------------------------------------------------------------


def test_abort_endpoint_exists_and_is_idempotent(tmp_path):
    """中止端点必须存在，且在没有进行中 turn 时也不报错。

    前端「停止」按钮可能因为竞态比 turn 结束晚一点到达。这时返回 404 会让
    界面闪一个无意义的错误，所以约定：没有 turn 在跑也算成功。
    """
    from fastapi.testclient import TestClient

    from api.app import create_app

    app = create_app(db_path=":memory:", workspace_root=tmp_path)
    with TestClient(app) as client:
        sid = client.post("/api/sessions").json()["session_id"]

        # 从未发过消息：runtime 还不存在，也必须 200
        r = client.post(f"/api/sessions/{sid}/abort")
        assert r.status_code == 200, f"中止端点应存在且宽容；实际 {r.status_code} {r.text[:200]}"
        assert r.json()["ok"] is True

        # 再调一次（幂等）
        assert client.post(f"/api/sessions/{sid}/abort").status_code == 200


def test_abort_endpoint_404s_for_unknown_session(tmp_path):
    """不存在的会话要 404 —— 区分「没有 turn 可停」和「根本没有这个会话」。"""
    from fastapi.testclient import TestClient

    from api.app import create_app

    app = create_app(db_path=":memory:", workspace_root=tmp_path)
    with TestClient(app) as client:
        assert client.post("/api/sessions/nope/abort").status_code == 404
