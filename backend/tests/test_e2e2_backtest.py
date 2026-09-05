"""T40 E2E-2 回测场景 —— keyless（mock 驱动 submit_backtest job → 净值+回撤+指标 artifact）。

M3 capstone。链路（无真实 key）：
  用户「20/60 金叉在茅台回测」
   → mock 首轮 tool_call: mcp__research__submit_backtest(closes=合成先跌后涨序列,
     fast=20, slow=60, symbol=茅台) → 工具写 jobs/<id>.json 立即返回 {job_id}
   → mock 第二轮文字结论
   → turn 结束：ingest_job_requests 入队 → JobQueue 异步跑 alpha.backtest → 产净值/回撤/
     指标 artifact + manifest → on_complete 摄取并挂到 assistant 消息 → 发 artifact/attached
  验收：job 状态 succeeded；assistant 消息挂着净值(chart)+回撤(chart)+指标(metric) artifact。

真实 uvicorn（SSE 长驻 + 后台 job 需真实事件循环）。
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

# 合成收盘价：先跌 60 天再涨 70 天 → 必然产生 20/60 金叉与持仓变化。
_CLOSES = [100.0 - i for i in range(60)] + [40.0 + i * 1.5 for i in range(70)]
_CONCLUSION = "已提交 20/60 金叉回测 job。完成后将展示净值与回撤。以上为客观回测，不构成投资建议。"


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


def _mock_backtest_model():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("content-length", "0"))
            body = json.loads(self.rfile.read(n))
            messages = body.get("messages", [])
            has_tool_result = any(
                isinstance(m, dict) and m.get("role") == "tool" for m in messages
            )
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.end_headers()
            if has_tool_result:
                chunks = _text_chunks(_CONCLUSION)
            else:
                chunks = _tool_call_chunks(
                    "call-e2e2", "mcp__research__submit_backtest",
                    {"closes": _CLOSES, "fast": 20, "slow": 60, "symbol": "茅台"},
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


@pytest.mark.skip(reason="agent 接入推迟至 S5（ADR-0008）；dsh SDK DeepSeekHarnessConfig 签名待对齐，代码保留")
@pytest.mark.skipif(__import__("sys").platform != "darwin",
                    reason="agent turn 依赖 dsh runtime（macOS carrier）")
async def test_e2e2_backtest_job_attaches_equity_drawdown_metric():
    server, base = _mock_backtest_model()
    try:
        with tempfile.TemporaryDirectory(prefix="e2e2-") as tmp:
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
                    json={"content": "用 20/60 金叉在茅台回测近三年，画净值和回撤"},
                )

                # 轮询 assistant 消息，等 job 完成后 artifact 挂上（job 异步）。
                async def wait_artifacts():
                    for _ in range(240):
                        msgs = (await client.get(f"/api/sessions/{sid}/messages")).json()
                        asst = [m for m in msgs if m["role"] == "assistant"]
                        if asst and len(asst[-1].get("artifacts", [])) >= 3:
                            return asst[-1]
                        await asyncio.sleep(0.5)
                    return None

                assistant = await asyncio.wait_for(wait_artifacts(), timeout=120)
                assert assistant is not None, "job artifact 未在超时内挂到消息"

                arts = assistant["artifacts"]
                kinds = [a["kind"] for a in arts]
                titles = [a["title"] for a in arts]
                # 净值 + 回撤（两个 chart）+ 指标（metric）
                assert kinds.count("chart") >= 2, kinds
                assert "metric" in kinds, kinds
                assert any("净值" in t for t in titles), titles
                assert any("回撤" in t for t in titles), titles
                # 净值 chart 是 line option
                equity = next(a for a in arts if a["kind"] == "chart" and "净值" in a["title"])
                assert equity["payload"]["series"][0]["type"] == "line"

                # job 在 store 里 succeeded
                jobs_rows = app.state.store.conn.execute(
                    "SELECT status, result FROM job"
                ).fetchall()
                assert any(r["status"] == "succeeded" for r in jobs_rows), \
                    [dict(r) for r in jobs_rows]

            srv.should_exit = True
            await task
            app.state.manager.close_all()
    finally:
        server.shutdown()
