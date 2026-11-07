"""T28 会话 API + SSE 测试 —— 注入假 provider 驱动完整 turn（无网络、无模型、无凭据）。

DoD：
- 消息落库：POST 用户消息后，turn 结束时 GET messages 里有 user + assistant。
- SSE 推流：GET /stream 收到 text_delta 增量 + turn_end。
- 断线重连：带 Last-Event-ID，从该 id 之后补发（不重复、不丢）。

说明：SSE 流用**真实 uvicorn 服务器**测（httpx.ASGITransport 会缓冲流式响应到生成器
结束，而我们的 SSE 生成器为多轮会话长驻不结束，故不能用 ASGITransport 测流）。

v2 换 Pi 后，v1 的「mock OpenAI HTTP 端点」手法失效了：Pi 自己发模型请求，
我们这一侧拦不到请求体。改为经 `create_app(provider_factory=...)` 注入一个
假 provider —— 这测的仍是 API + 会话编排，而 provider 的实现本来就不该被这些
测试关心（同一个 AgentProvider seam）。
"""

import asyncio
import socket
import tempfile
from pathlib import Path

import httpx
import uvicorn

from agent.provider import AgentEvent
from api.app import create_app
from api.session_manager import SessionRuntime


class _FakeProvider:
    """满足 AgentProvider 契约的假 provider：按剧本产事件，不启动任何子进程。"""

    def __init__(self, reply: str, *, fail: bool = False) -> None:
        self._reply = reply
        self._fail = fail
        self.aborted = False
        self.closed = False

    def start(self) -> None:
        return

    def abort(self, reason: str = "") -> None:
        self.aborted = True

    def close(self) -> None:
        self.closed = True
        return

    def is_alive(self) -> bool:
        return not self.closed

    async def astream(self, prompt: str):
        from agent.provider import EVENT_ERROR, EVENT_TEXT_DELTA, EVENT_TURN_END

        if self._fail:
            yield AgentEvent(kind=EVENT_ERROR, payload={"error": "假 provider 故意失败"})
            yield AgentEvent(kind=EVENT_TURN_END,
                             payload={"final_text": "", "finish_reason": "error"})
            return

        # 逐字吐，模拟流式（顺带验证 SSE 增量确实逐条推出去）
        for ch in self._reply:
            yield AgentEvent(kind=EVENT_TEXT_DELTA, payload={"text": ch})
        yield AgentEvent(
            kind=EVENT_TURN_END,
            payload={"final_text": self._reply, "finish_reason": "stop"},
        )


def _fake_factory(reply: str, *, fail: bool = False):
    """返回一个 provider_factory：每个 session_id 一个假 provider + 独立 workspace。"""

    def factory(session_id: str):
        ws = Path(tempfile.mkdtemp(prefix=f"ws-{session_id[:8]}-"))
        return _FakeProvider(reply, fail=fail), ws

    return factory


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _RunningApp:
    """在后台跑一个真实 uvicorn 服务器，供 SSE 流式测试。"""

    def __init__(self, app):
        self.app = app
        self.port = _free_port()
        self._server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="error")
        )
        self._task = None

    async def __aenter__(self):
        self._task = asyncio.create_task(self._server.serve())
        for _ in range(100):
            if self._server.started:
                break
            await asyncio.sleep(0.05)
        return self

    async def __aexit__(self, *exc):
        self._server.should_exit = True
        if self._task:
            await self._task
        self.app.state.manager.close_all()

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{self.port}", trust_env=False
        )


# ---------- 纯单元：SessionRuntime buffer / reconnect（不起子进程，快）----------

def test_runtime_buffer_and_reconnect():
    rt = SessionRuntime(provider=object())  # buffer 逻辑不触及 provider
    rt._emit("text_delta", {"text": "a"})
    rt._emit("text_delta", {"text": "b"})
    rt._emit("turn_end", {"final_text": "ab"})
    assert [e.id for e in rt.events] == [1, 2, 3]

    # 重连从 id=1 之后 → 收到 2,3
    q = rt.subscribe(last_event_id=1)
    got = []
    while not q.empty():
        got.append(q.get_nowait())
    assert [e.id for e in got] == [2, 3]

    # 新客户端（None）→ 全量补发 1,2,3（避免错过已缓冲事件）
    q2 = rt.subscribe(last_event_id=None)
    got2 = []
    while not q2.empty():
        got2.append(q2.get_nowait())
    assert [e.id for e in got2] == [1, 2, 3]

    # live 推送到达所有订阅者
    rt._emit("message/committed", {"message_id": "m-1"})
    assert q.get_nowait().type == "message/committed"


# ---------- 集成：真实 agent turn 经 API（起子进程 + uvicorn，keyless）----------

async def _wait_turn(app, sid, timeout=40):
    async def _w():
        while True:
            rt = app.state.manager.get_runtime(sid)
            if rt and any(e.type == "turn_end" for e in rt.events):
                return
            await asyncio.sleep(0.25)
    await asyncio.wait_for(_w(), timeout=timeout)


async def test_message_persistence_and_sse_stream():
    with tempfile.TemporaryDirectory(prefix="t28-") as tmp:
        app = create_app(
            db_path=":memory:",
            workspace_root=Path(tmp),
            provider_factory=_fake_factory("白酒板块是消费板块龙头之一。"),
        )
        async with _RunningApp(app) as running:
            async with running.client() as client:
                sid = (await client.post("/api/sessions")).json()["session_id"]
                r = await client.post(f"/api/sessions/{sid}/messages",
                                      json={"content": "白酒板块怎么样？"})
                assert r.status_code == 200

                async def read_stream():
                    events = []
                    async with client.stream("GET", f"/api/sessions/{sid}/stream") as resp:
                        assert resp.status_code == 200
                        async for line in resp.aiter_lines():
                            if line.startswith("event:"):
                                events.append(line.split("event:", 1)[1].strip())
                                if events[-1] == "turn_end":
                                    break
                    return events

                events = await asyncio.wait_for(read_stream(), timeout=40)
                assert "text_delta" in events
                assert "turn_end" in events

                msgs = (await client.get(f"/api/sessions/{sid}/messages")).json()
                roles = [m["role"] for m in msgs]
                assert "user" in roles and "assistant" in roles
                assistant = [m for m in msgs if m["role"] == "assistant"][-1]
                assert "白酒" in assistant["content"]


async def test_stream_reconnect_from_last_event_id():
    with tempfile.TemporaryDirectory(prefix="t28-recon-") as tmp:
        app = create_app(
            db_path=":memory:",
            workspace_root=Path(tmp),
            provider_factory=_fake_factory("结论文本。"),
        )
        async with _RunningApp(app) as running:
            async with running.client() as client:
                sid = (await client.post("/api/sessions")).json()["session_id"]
                await client.post(f"/api/sessions/{sid}/messages",
                                  json={"content": "问一句"})
                await _wait_turn(app, sid)
                rt = app.state.manager.get_runtime(sid)
                assert rt is not None and len(rt.events) >= 2
                total = len(rt.events)
                mid_id = rt.events[len(rt.events) // 2].id

                async def read_after():
                    ids = []
                    async with client.stream(
                        "GET", f"/api/sessions/{sid}/stream",
                        headers={"Last-Event-ID": str(mid_id)},
                    ) as resp:
                        async for line in resp.aiter_lines():
                            if line.startswith("id:"):
                                ids.append(int(line.split("id:", 1)[1].strip()))
                                if len(ids) >= (total - mid_id):
                                    break
                    return ids

                ids = await asyncio.wait_for(read_after(), timeout=20)
                assert ids == list(range(mid_id + 1, total + 1))
