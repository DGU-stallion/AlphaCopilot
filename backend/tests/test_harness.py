"""T27 dsh 适配层测试 —— keyless（mock OpenAI SSE 端点，无需真实 key）。

DoD：
- 并发两个会话互不干扰：两个 HarnessSession 各自跑一个 turn，各自拿到自己那句流式回复。
- 进程泄漏测试：close() 后子进程回收（is_process_alive() → False）。

复用 G2 spike 的 mock 手法：起一个假的 /v1 OpenAI 兼容 SSE 端点，把回复逐字拆成
content 增量，driver 从 on_notification 收到 assistant/chunk。
"""

import asyncio
import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from agent.harness import HarnessSession, HarnessSettings

pytestmark = pytest.mark.asyncio


def _text_chunks(text: str):
    chunks = [{"choices": [{"delta": {"role": "assistant", "content": None,
                                      "reasoning_content": ""}}]}]
    for piece in text:
        chunks.append({"choices": [{"delta": {"content": piece}}]})
    chunks.append({"choices": [{"delta": {"content": ""}, "finish_reason": "stop"}],
                   "usage": {"prompt_tokens": 3, "completion_tokens": 3}})
    return chunks


def _make_mock_server(reply_for):
    """reply_for: callable(prompt_messages) -> reply string. 每会话一台，隔离回复。"""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("content-length", "0"))
            body = json.loads(self.rfile.read(n))
            reply = reply_for(body.get("messages", []))
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


def _settings(tmp: Path, base_url: str) -> HarnessSettings:
    ws = tmp / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    sr = tmp / "sessions"
    sr.mkdir(parents=True, exist_ok=True)
    return HarnessSettings(
        workspace=str(ws), session_root=str(sr),
        base_url=base_url, api_key="sk-mock",
        request_timeout_seconds=90.0,
    )


async def _collect(session: HarnessSession, prompt: str):
    types = []
    final = None
    async for ev in session.astream(prompt):
        types.append(ev.type)
        if ev.type == "turn/final":
            final = ev.payload["final_response"]
    return types, final


async def test_single_turn_streams_and_finalizes():
    with tempfile.TemporaryDirectory(prefix="t27-single-") as tmp:
        server, base = _make_mock_server(lambda msgs: "白酒板块是消费龙头。")
        try:
            s = HarnessSession(_settings(Path(tmp), base))
            await asyncio.to_thread(s.start)
            types, final = await _collect(s, "白酒板块怎么样？")
            assert final == "白酒板块是消费龙头。"
            # 流里应有逐字增量（assistant/chunk）与最终元事件。
            assert any("chunk" in t or "message" in t for t in types)
            assert "turn/final" in types
            s.close()
            assert s.is_process_alive() is False
        finally:
            server.shutdown()


async def test_two_sessions_do_not_interfere():
    """并发两个会话，各自 mock 端点回不同内容，验证互不串台。"""
    with tempfile.TemporaryDirectory(prefix="t27-concur-") as tmp:
        srvA, baseA = _make_mock_server(lambda msgs: "回复A：贵州茅台。")
        srvB, baseB = _make_mock_server(lambda msgs: "回复B：五粮液。")
        try:
            sA = HarnessSession(_settings(Path(tmp) / "A", baseA))
            sB = HarnessSession(_settings(Path(tmp) / "B", baseB))
            await asyncio.gather(
                asyncio.to_thread(sA.start),
                asyncio.to_thread(sB.start),
            )
            # 两个 dsh session_id 必须不同（避免 id-collision）。
            assert sA.dsh_session_id != sB.dsh_session_id

            (typesA, finalA), (typesB, finalB) = await asyncio.gather(
                _collect(sA, "问A"),
                _collect(sB, "问B"),
            )
            assert finalA == "回复A：贵州茅台。"
            assert finalB == "回复B：五粮液。"

            sA.close()
            sB.close()
            assert sA.is_process_alive() is False
            assert sB.is_process_alive() is False
        finally:
            srvA.shutdown()
            srvB.shutdown()


async def test_close_is_idempotent_and_kills_process():
    with tempfile.TemporaryDirectory(prefix="t27-leak-") as tmp:
        server, base = _make_mock_server(lambda msgs: "ok")
        try:
            s = HarnessSession(_settings(Path(tmp), base))
            await asyncio.to_thread(s.start)
            assert s.is_process_alive() is True
            s.close()
            assert s.is_process_alive() is False
            s.close()  # 幂等，不抛
            assert s.is_process_alive() is False
        finally:
            server.shutdown()
