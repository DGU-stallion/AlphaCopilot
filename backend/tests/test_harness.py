"""DshProvider 适配层测试 —— keyless（mock OpenAI SSE 端点，无需真实 key）。

DoD：
- 并发两个会话互不干扰：两个 DshProvider 各自跑一个 turn，各自拿到自己那句流式回复。
- 进程泄漏：close() 后子进程回收（is_alive() → False）。
- 事件归一化：只产出中立 AgentEvent kind（text_delta / turn_end），不泄漏 dsh wire 形状。

复用 M0 spike 的 mock 手法：起一个假的 /v1 OpenAI 兼容 SSE 端点，把回复逐字拆成
content 增量，driver 从 on_notification 收到并翻译为 text_delta。
"""

import asyncio
import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from agent.provider import (
    EVENT_TEXT_DELTA,
    EVENT_TURN_END,
    ProviderSpec,
)
from agent.providers.dsh import DshProvider, _cordis_without_thinking, _is_deepseek_official

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


def _spec(tmp: Path, base_url: str) -> ProviderSpec:
    ws = tmp / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    return ProviderSpec(
        workspace=ws,
        system_prompt="测试合规 persona。",
        base_url=base_url,
        api_key="sk-mock",
        request_timeout_seconds=90.0,
    )


async def _collect(provider: DshProvider, prompt: str):
    kinds = []
    final = None
    async for ev in provider.astream(prompt):
        kinds.append(ev.kind)
        if ev.kind == EVENT_TURN_END:
            final = ev.payload["final_text"]
    return kinds, final


async def test_single_turn_streams_neutral_events():
    with tempfile.TemporaryDirectory(prefix="dsh-single-") as tmp:
        server, base = _make_mock_server(lambda msgs: "白酒板块是消费龙头。")
        try:
            p = DshProvider(_spec(Path(tmp), base))
            await asyncio.to_thread(p.start)
            kinds, final = await _collect(p, "白酒板块怎么样？")
            assert final == "白酒板块是消费龙头。"
            # 只应出现中立 kind：逐字 text_delta + 结束 turn_end；无 dsh wire 词汇。
            assert EVENT_TEXT_DELTA in kinds
            assert EVENT_TURN_END in kinds
            assert all(k in {EVENT_TEXT_DELTA, EVENT_TURN_END} for k in kinds)
            p.close()
            assert p.is_alive() is False
        finally:
            server.shutdown()


async def test_two_sessions_do_not_interfere():
    """并发两个会话，各自 mock 端点回不同内容，验证互不串台。"""
    with tempfile.TemporaryDirectory(prefix="dsh-concur-") as tmp:
        srvA, baseA = _make_mock_server(lambda msgs: "回复A：贵州茅台。")
        srvB, baseB = _make_mock_server(lambda msgs: "回复B：五粮液。")
        try:
            pA = DshProvider(_spec(Path(tmp) / "A", baseA))
            pB = DshProvider(_spec(Path(tmp) / "B", baseB))
            await asyncio.gather(
                asyncio.to_thread(pA.start),
                asyncio.to_thread(pB.start),
            )
            # 两个 dsh session_id 必须不同（避免 id-collision）。
            assert pA._dsh_session_id != pB._dsh_session_id

            (kindsA, finalA), (kindsB, finalB) = await asyncio.gather(
                _collect(pA, "问A"),
                _collect(pB, "问B"),
            )
            assert finalA == "回复A：贵州茅台。"
            assert finalB == "回复B：五粮液。"

            pA.close()
            pB.close()
            assert pA.is_alive() is False
            assert pB.is_alive() is False
        finally:
            srvA.shutdown()
            srvB.shutdown()


async def test_close_is_idempotent_and_kills_process():
    with tempfile.TemporaryDirectory(prefix="dsh-leak-") as tmp:
        server, base = _make_mock_server(lambda msgs: "ok")
        try:
            p = DshProvider(_spec(Path(tmp), base))
            await asyncio.to_thread(p.start)
            assert p.is_alive() is True
            p.close()
            assert p.is_alive() is False
            p.close()  # 幂等，不抛
            assert p.is_alive() is False
        finally:
            server.shutdown()


# ---- 模型参数归一化（纯单元，不起子进程）----

def test_non_official_base_url_is_not_deepseek_official():
    assert _is_deepseek_official(None) is True
    assert _is_deepseek_official("https://api.deepseek.com") is True
    assert _is_deepseek_official("https://apihub.agnes-ai.com/v1") is False


def test_cordis_normalization_strips_thinking_lines():
    src = (
        "- id: llm-deepseek\n"
        "  config:\n"
        "    thinking: enabled\n"
        "    reasoningEffort: max\n"
        "- id: other\n"
    )
    out = _cordis_without_thinking(src)
    assert "thinking" not in out
    assert "reasoningEffort" not in out
    assert "id: llm-deepseek" in out
    assert "id: other" in out
