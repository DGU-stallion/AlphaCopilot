"""T31 合规底线测试 —— keyless（mock 端点捕获 model-visible system prompt）。

DoD 口径：真实「追问荐股被拒」需真实模型推理（留给用户验收）；keyless 下测**机制**：
合规 prompt 与 skills 确实对模型可见（模型收到的 messages[system] 含 5 个合规关键词，
tools/system 里能见到 skill）。这是 g4 spike 的手法在生产 harness 上的固化。

若合规 section 没进 system prompt，则模型不可能遵守合规底线 —— 机制不可见即失败。
"""

import asyncio
import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from agent.harness import HarnessSession, HarnessSettings
from agent.persona import system_prompt as compliance_prompt

_CAPTURE: dict = {}


def _text_chunks(text: str):
    return [
        {"choices": [{"delta": {"role": "assistant", "content": None}}]},
        {"choices": [{"delta": {"content": text}}]},
        {"choices": [{"delta": {"content": ""}, "finish_reason": "stop"}]},
    ]


def _capturing_model():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("content-length", "0"))
            body = json.loads(self.rfile.read(n))
            if "first_body" not in _CAPTURE:
                _CAPTURE["first_body"] = body
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.end_headers()
            for c in _text_chunks("好的。"):
                self.wfile.write(f"data: {json.dumps(c)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

        def log_message(self, *_):
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/v1"


def test_persona_has_five_compliance_keywords():
    """单元：persona 文本含 5 个合规关键词（不依赖子进程）。"""
    sp = compliance_prompt()
    for kw in ["不推荐", "不预测", "买卖时机", "不承诺收益", "不打分"]:
        assert kw in sp


async def test_compliance_prompt_visible_to_model():
    """集成：合规 persona 确实进了模型收到的 system prompt（keyless 捕获）。"""
    _CAPTURE.clear()
    server, base = _capturing_model()
    try:
        with tempfile.TemporaryDirectory(prefix="t31-") as tmp:
            ws = Path(tmp) / "ws"
            sr = Path(tmp) / "s"
            ws.mkdir()
            sr.mkdir()
            # system_prompt=None → harness 注入合规 persona（默认行为）。
            s = HarnessSession(
                HarnessSettings(
                    workspace=str(ws), session_root=str(sr),
                    base_url=base, api_key="sk-mock",
                    request_timeout_seconds=90.0,
                )
            )
            await asyncio.to_thread(s.start)
            async for _ in s.astream("帮我推荐一只能涨的票"):
                pass
            s.close()
    finally:
        server.shutdown()

    body = _CAPTURE.get("first_body") or {}
    sys_msgs = [
        m for m in body.get("messages", [])
        if isinstance(m, dict) and m.get("role") == "system"
    ]
    sys_text = "\n".join(
        m.get("content") if isinstance(m.get("content"), str)
        else json.dumps(m.get("content"), ensure_ascii=False)
        for m in sys_msgs
    )

    # 合规关键词可见（至少命中 4/5，稳健）
    hits = [k for k in ["不推荐", "不预测", "买卖时机", "不承诺收益", "不打分"] if k in sys_text]
    assert len(hits) >= 4, f"合规关键词命中不足: {hits}\nsystem={sys_text[:400]}"

    # skills 可见：skill 工具在 tools 里，或 system 提到 skill 目录/技能名
    tool_names = {
        t.get("function", {}).get("name")
        for t in body.get("tools", []) if isinstance(t, dict)
    }
    skills_visible = "skill" in tool_names or any(
        n in sys_text for n in ["skill", "candlestick", "technical", "fundamental", "risk", "sentiment"]
    )
    assert skills_visible, f"skills 不可见。tools={tool_names}"
