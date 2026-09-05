"""T28 会话 API + SSE 测试 —— keyless（mock 模型端点驱动真实 agent turn）。

DoD：
- 消息落库：POST 用户消息后，turn 结束时 GET messages 里有 user + assistant。
- SSE 推流：GET /stream 收到 text_delta 增量 + turn_end。
- 断线重连：带 Last-Event-ID，从该 id 之后补发（不重复、不丢）。

说明：SSE 流用**真实 uvicorn 服务器**测（httpx.ASGITransport 会缓冲流式响应到生成器
结束，而我们的 SSE 生成器为多轮会话长驻不结束，故不能用 ASGITransport 测流）。
"""

import asyncio
import json
import socket
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx
import pytest
import uvicorn

from api.app import create_app
from api.session_manager import SessionRuntime


def _text_chunks(text: str):
    chunks = [{"choices": [{"delta": {"role": "assistant", "content": None,
                                      "reasoning_content": ""}}]}]
    for piece in text:
        chunks.append({"choices": [{"delta": {"content": piece}}]})
    chunks.append({"choices": [{"delta": {"content": ""}, "finish_reason": "stop"}],
                   "usage": {"prompt_tokens": 3, "completion_tokens": 3}})
    return chunks


def _mock_model(reply="白酒板块是消费板块龙头之一。"):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("content-length", "0"))
            self.rfile.read(n)
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.end_headers()
            for c in _text_chunks(reply):
                self.wfile.write(f"data: {json.dumps(c)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

        def log_message(self, *_):
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/v1"


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
    server, base = _mock_model("白酒板块是消费板块龙头之一。")
    try:
        with tempfile.TemporaryDirectory(prefix="t28-") as tmp:
            app = create_app(db_path=":memory:", workspace_root=Path(tmp),
                             base_url=base, api_key="sk-mock")
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
    finally:
        server.shutdown()


async def test_stream_reconnect_from_last_event_id():
    server, base = _mock_model("结论文本。")
    try:
        with tempfile.TemporaryDirectory(prefix="t28-recon-") as tmp:
            app = create_app(db_path=":memory:", workspace_root=Path(tmp),
                             base_url=base, api_key="sk-mock")
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
    finally:
        server.shutdown()
