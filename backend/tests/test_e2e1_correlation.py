"""T36 E2E-1 相关性场景 —— keyless（mock 模型驱动真实 agent + run_python + artifact 投递）。

M2 capstone。链路（全程无真实 key）：
  用户「分析白酒板块与沪深300 相关性」
   → mock 模型首轮返回 tool_call: mcp__research__run_python(code=用 alpha.chart.heatmap
     产相关性热力图 chart.json + 写 manifest.json)
   → dsh 真实执行我们的 run_python（Seatbelt 沙箱）→ 产出落 workspace/runs/<run_id>/
   → tool 结果回流，mock 第二轮返回文字结论
   → turn 结束：session_manager 扫描 runs/ 摄取 manifest → artifact 落库 + 挂消息 + 事件
  验收：SSE 见 text_delta（结论）+ artifact/attached；GET messages 里 assistant 消息
        挂着一个 kind=chart 的 artifact，payload 是 heatmap option（series[0].type=heatmap）。

用真实 uvicorn（SSE 长驻流不能用 ASGITransport）。
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

# agent 在沙箱里跑的代码：用 alpha.chart.heatmap 产相关性热力图 + 写 manifest.json。
_AGENT_CODE = r"""
import json
from alpha import chart

labels = ["茅台", "五粮液", "泸州老窖", "洋河", "古井贡", "沪深300"]
matrix = [
    [1.00, 0.82, 0.78, 0.71, 0.66, 0.55],
    [0.82, 1.00, 0.80, 0.69, 0.63, 0.52],
    [0.78, 0.80, 1.00, 0.72, 0.61, 0.50],
    [0.71, 0.69, 0.72, 1.00, 0.58, 0.48],
    [0.66, 0.63, 0.61, 0.58, 1.00, 0.45],
    [0.55, 0.52, 0.50, 0.48, 0.45, 1.00],
]
option = chart.heatmap(labels, matrix, title="白酒板块与沪深300 相关性（近一年）")
with open("chart.json", "w", encoding="utf-8") as f:
    json.dump(option, f, ensure_ascii=False)

manifest = {
    "run_id": "e2e1",
    "code_ref": "code.py",
    "artifacts": [
        {"id": "a1", "kind": "chart", "title": "白酒相关性热力图", "path": "chart.json",
         "inputs": {"symbols": labels}},
    ],
}
with open("manifest.json", "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False)
print("HEATMAP_DONE")
"""

_CONCLUSION = "白酒板块内部相关性高（0.6~0.8），与沪深300 相关性中等（约0.5）。以上为客观数据，不构成投资建议。"


def _tool_call_chunks(call_id, name, arguments):
    return [
        {"choices": [{"delta": {"role": "assistant", "content": None}}]},
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "id": call_id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)},
        }]}}]},
        {"choices": [{"delta": {"content": ""}, "finish_reason": "tool_calls"}]},
    ]


def _text_chunks(text):
    chunks = [{"choices": [{"delta": {"role": "assistant", "content": None}}]}]
    for piece in text:
        chunks.append({"choices": [{"delta": {"content": piece}}]})
    chunks.append({"choices": [{"delta": {"content": ""}, "finish_reason": "stop"}]})
    return chunks


def _mock_correlation_model():
    """首轮 tool_call run_python；见到 tool 结果后返回文字结论。"""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("content-length", "0"))
            body = json.loads(self.rfile.read(n))
            messages = body.get("messages", [])
            latest = messages[-1] if messages else {}
            has_tool_result = any(
                isinstance(m, dict) and m.get("role") == "tool" for m in messages
            )
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.end_headers()
            if has_tool_result or (isinstance(latest, dict) and latest.get("role") == "tool"):
                chunks = _text_chunks(_CONCLUSION)
            else:
                chunks = _tool_call_chunks(
                    "call-e2e1", "mcp__research__run_python", {"code": _AGENT_CODE}
                )
            for c in chunks:
                self.wfile.write(f"data: {json.dumps(c)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

        def log_message(self, *_):
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/v1"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.mark.skipif(__import__("sys").platform != "darwin",
                    reason="run_python 沙箱依赖 macOS sandbox-exec")
async def test_e2e1_correlation_heatmap_in_chat_stream():
    server, base = _mock_correlation_model()
    try:
        with tempfile.TemporaryDirectory(prefix="e2e1-") as tmp:
            app = create_app(db_path=":memory:", workspace_root=Path(tmp),
                             base_url=base, api_key="sk-mock")
            port = _free_port()
            srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                                log_level="error"))
            task = asyncio.create_task(srv.serve())
            for _ in range(100):
                if srv.started:
                    break
                await asyncio.sleep(0.05)

            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}",
                                         trust_env=False) as client:
                sid = (await client.post("/api/sessions")).json()["session_id"]
                await client.post(
                    f"/api/sessions/{sid}/messages",
                    json={"content": "分析近一年白酒板块 5 只标的与沪深300 的相关性"},
                )

                # 收 SSE 到 message/committed；记录事件类型 + 结论文本 + 是否 artifact/attached
                seen_types: set[str] = set()
                deltas: list[str] = []

                async def read():
                    async with client.stream("GET", f"/api/sessions/{sid}/stream") as resp:
                        cur = None
                        async for line in resp.aiter_lines():
                            if line.startswith("event:"):
                                cur = line.split("event:", 1)[1].strip()
                                seen_types.add(cur)
                            elif line.startswith("data:") and cur == "text_delta":
                                d = json.loads(line[5:].strip())
                                t = d.get("text")
                                if isinstance(t, str):
                                    deltas.append(t)
                            if cur == "message/committed":
                                break

                await asyncio.wait_for(read(), timeout=90)

                # 结论文字逐字出现
                conclusion = "".join(deltas)
                assert "相关性" in conclusion, f"结论未含相关性: {conclusion!r}"
                assert "不构成投资建议" in conclusion  # 合规口径
                # artifact 被摄取并挂载（事件）
                assert "artifact/attached" in seen_types, f"事件: {seen_types}"

                # GET messages：assistant 消息挂着 heatmap chart artifact
                msgs = (await client.get(f"/api/sessions/{sid}/messages")).json()
                assistant = [m for m in msgs if m["role"] == "assistant"][-1]
                arts = assistant["artifacts"]
                assert len(arts) >= 1
                chart_art = next(a for a in arts if a["kind"] == "chart")
                assert chart_art["payload"]["series"][0]["type"] == "heatmap"

            srv.should_exit = True
            await task
            app.state.manager.close_all()
    finally:
        server.shutdown()
