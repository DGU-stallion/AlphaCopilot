"""job 订阅链路测试（M1-8）。

## 缺的是什么

job 是异步的：agent 提交后 turn 立刻结束，回测在后台跑几秒。当前实现里
job 完成时只做了一件事——摄取 artifact 挂到消息上。但**没有向会话的 SSE 流
发任何事件**。

后果：前端只知道「有个 job 提交了」（收到 `job/submitted`），不知道它什么时候
完成、成功还是失败。用户看着一个转圈的加载条，而 artifact 其实已经到了
——只是没有任何东西触发前端去重新拉取。

## 这条链路要能观察到的三件事

1. `job/submitted` —— 已入队
2. `job/completed` —— 成功，artifact 已挂好（前端据此刷新）
3. `job/failed` —— 失败，带原因（否则前端只能一直等）

第 2、3 条是这次要补的。它们必须发到**会话的**事件流（`SessionRuntime._emit`），
而不是 job 自己的流——因为用户盯的是对话，不是某个 job id。
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from agent.provider import AgentEvent
from api.app import create_app

_asyncio = pytest.mark.asyncio

# 合成收盘价：先跌后涨 → 必然产生金叉
_CLOSES = [100.0 - i for i in range(60)] + [40.0 + i * 1.5 for i in range(70)]


class _JobSubmitter:
    """假 provider：写 job 请求文件后吐结论。"""

    def __init__(self, workspace: Path, *, valid: bool = True) -> None:
        self._ws = workspace
        self._valid = valid
        self._closed = False

    def start(self) -> None:
        return

    def abort(self, reason: str = "") -> None:
        return

    def close(self) -> None:
        self._closed = True

    def is_alive(self) -> bool:
        return not self._closed

    async def astream(self, prompt: str):
        from agent.provider import EVENT_TEXT_DELTA, EVENT_TURN_END

        jobs_dir = self._ws / "jobs"
        jobs_dir.mkdir(parents=True, exist_ok=True)
        params = (
            {"closes": _CLOSES, "fast": 20, "slow": 60, "symbol": "茅台"}
            if self._valid
            # 非法参数：closes 只有 1 个点 → 回测引擎会抛错
            else {"closes": [1.0], "fast": 20, "slow": 60}
        )
        (jobs_dir / "j.json").write_text(
            json.dumps({"kind": "backtest", "params": params}, ensure_ascii=False),
            encoding="utf-8",
        )
        yield AgentEvent(kind=EVENT_TEXT_DELTA, payload={"text": "已提交回测。"})
        yield AgentEvent(
            kind=EVENT_TURN_END,
            payload={"final_text": "已提交回测。", "finish_reason": "stop"},
        )


async def _wait_for_event(rt, ev_type: str, timeout: float = 60.0):
    """等某类事件出现在 runtime 的事件缓冲里，返回该事件。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        for e in rt.events:
            if e.type == ev_type:
                return e
        await asyncio.sleep(0.1)
    return None


@_asyncio
async def test_job_completion_emits_event_on_session_stream():
    """job 成功后必须往**会话**事件流发 `job/completed`。

    前端盯的是对话，不是某个 job id。没有这个事件，artifact 到了界面上也不会刷新。
    """
    with tempfile.TemporaryDirectory(prefix="m18-") as tmp:

        def factory(session_id: str):
            ws = Path(tmp) / session_id / "ws"
            ws.mkdir(parents=True, exist_ok=True)
            return _JobSubmitter(ws), ws

        app = create_app(
            db_path=":memory:", workspace_root=Path(tmp), provider_factory=factory
        )
        sid = app.state.store.create_session()
        await app.state.manager.send_message(sid, "回测茅台")

        rt = app.state.manager.get_runtime(sid)
        assert rt is not None

        submitted = await _wait_for_event(rt, "job/submitted", timeout=30)
        assert submitted is not None, (
            f"没有 job/submitted 事件；实际事件：{[e.type for e in rt.events]}"
        )

        completed = await _wait_for_event(rt, "job/completed", timeout=60)
        assert completed is not None, (
            "job 完成后没有往会话流发 job/completed。\n"
            "前端因此不知道何时可以刷新 artifact——界面会一直转圈。\n"
            f"实际事件：{[e.type for e in rt.events]}"
        )
        assert completed.data.get("job_id"), f"job/completed 应带 job_id：{completed.data}"

        app.state.manager.close_all()


@_asyncio
async def test_job_failure_emits_event_with_reason():
    """job 失败必须发 `job/failed` 并带原因。

    失败时如果不发事件，前端只会一直等——比报错更糟，因为连「出错了」都不知道。
    """
    with tempfile.TemporaryDirectory(prefix="m18f-") as tmp:

        def factory(session_id: str):
            ws = Path(tmp) / session_id / "ws"
            ws.mkdir(parents=True, exist_ok=True)
            return _JobSubmitter(ws, valid=False), ws

        app = create_app(
            db_path=":memory:", workspace_root=Path(tmp), provider_factory=factory
        )
        sid = app.state.store.create_session()
        await app.state.manager.send_message(sid, "回测（非法参数）")

        rt = app.state.manager.get_runtime(sid)
        assert rt is not None

        failed = await _wait_for_event(rt, "job/failed", timeout=60)
        assert failed is not None, (
            "job 失败时没有发 job/failed。前端只能无限等待，比报错更糟。\n"
            f"实际事件：{[e.type for e in rt.events]}"
        )
        assert failed.data.get("error"), f"job/failed 应带 error：{failed.data}"

        app.state.manager.close_all()


@_asyncio
async def test_completed_event_carries_artifact_ids():
    """`job/completed` 要带 artifact id，前端才能直接定位而不是全量重拉。"""
    with tempfile.TemporaryDirectory(prefix="m18a-") as tmp:

        def factory(session_id: str):
            ws = Path(tmp) / session_id / "ws"
            ws.mkdir(parents=True, exist_ok=True)
            return _JobSubmitter(ws), ws

        app = create_app(
            db_path=":memory:", workspace_root=Path(tmp), provider_factory=factory
        )
        sid = app.state.store.create_session()
        await app.state.manager.send_message(sid, "回测")

        rt = app.state.manager.get_runtime(sid)
        completed = await _wait_for_event(rt, "job/completed", timeout=60)
        assert completed is not None

        aids = completed.data.get("artifact_ids") or []
        assert len(aids) >= 3, (
            f"回测应产出净值/回撤/指标三件 artifact；job/completed 里只有 {aids}"
        )

        app.state.manager.close_all()
