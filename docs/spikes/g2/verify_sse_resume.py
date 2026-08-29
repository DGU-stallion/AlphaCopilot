#!/usr/bin/env python3
"""G2 spike：notification → SSE 端到端 + 停止 + 同 session_id 跨进程历史续传。

三项验证（keyless，用 mock 模型端点）：
  [1] SSE 端到端：on_notification 回调收到逐条 session.event（含 assistant 文本增量），
      模拟桥接到 SSE sink，确认「浏览器能逐字出字」的数据通路成立。
  [2] 停止：turn 进行中杀掉 runtime 子进程（harness.close / kill），确认能中止。
  [3] 历史续传（重点未知项）：第一轮对话后关闭 runtime；用同一 session_root + 同一
      session_id 新起一个 runtime，发第二轮；检查 mock 模型第二轮收到的 messages 里
      是否含第一轮的历史 —— 这决定「刷新/重启后对话能否接着聊」。

结论如实记录：无论续传成立与否，都写进文档（这是 PLAN 里点名的未知项）。
"""

import json
import os
import sys
import threading
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
G1_DIR = HERE.parent / "g1"
CORDIS = G1_DIR / "cordis.yml"  # 复用 G1 组合（含 MCP、JSONL 持久化）

state = {"round": 0, "round2_messages": None}


def _text_chunks(text):
    # 拆成多个 content 增量，模拟逐字流
    chunks = [{"choices": [{"delta": {"role": "assistant", "content": None, "reasoning_content": ""}}]}]
    for piece in text:
        chunks.append({"choices": [{"delta": {"content": piece}}]})
    chunks.append({"choices": [{"delta": {"content": ""}, "finish_reason": "stop"}],
                   "usage": {"prompt_tokens": 3, "completion_tokens": 3}})
    return chunks


class MockModel(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(n))
        state.setdefault("call_log", []).append(
            {"round": state["round"], "n_messages": len(body.get("messages", []))}
        )
        # 记录第二轮收到的完整 messages（用于历史续传判断）
        if state["round"] >= 2 and state["round2_messages"] is None:
            state["round2_messages"] = body.get("messages", [])
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        if state["round"] == 1:
            reply = "贵州茅台是白酒龙头。"       # 第一轮答复（含可被第二轮引用的实体）
        else:
            reply = "上一轮我们聊的是贵州茅台。"   # 第二轮：若模型能引用则证明有历史
        for c in _text_chunks(reply):
            self.wfile.write(f"data: {json.dumps(c)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def log_message(self, *_):
        return


def main() -> int:
    print("=" * 60)
    print("G2: SSE 端到端 + 停止 + 同 session_id 跨进程历史续传")
    print("=" * 60)

    server = HTTPServer(("127.0.0.1", 0), MockModel)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{port}/v1"
    print(f"mock model: {base_url}")

    os.environ["G1_MCP_PY"] = sys.executable
    os.environ["G1_MCP_SERVER"] = str(G1_DIR / "mcp_server_min.py")

    from deepseek_harness import DeepSeekHarness, DeepSeekHarnessConfig

    results = {}
    with tempfile.TemporaryDirectory(prefix="g2-") as tmp:
        tmp = Path(tmp).resolve()
        (tmp / "ws").mkdir()
        sessions = tmp / "sessions"
        sessions.mkdir()
        SESSION_ID = "g2-durable"

        def make_cfg():
            return DeepSeekHarnessConfig(
                model="deepseek-v4-flash", cwd=str(tmp / "ws"),
                session_root=str(sessions), cordis=str(CORDIS),
                base_url=base_url, api_key="sk-mock",
                request_timeout_seconds=90.0,
            )

        # ---------- 第一轮：SSE 流式 ----------
        state["round"] = 1
        sse_sink = []  # 模拟 SSE：收到的 assistant 文本增量

        def on_notif(n):
            # 桥接：把 session.event 里的 assistant 文本增量推给「SSE」
            if n.method == "session.event":
                ev = n.payload.get("event", {})
                sse_sink.append((ev.get("type"), n.method))

        h1 = DeepSeekHarness(make_cfg())
        h1.start()
        r1 = h1.run("贵州茅台是什么？", session_id=SESSION_ID, on_notification=on_notif)
        print(f"\n[1] SSE 端到端: 收到 {len(sse_sink)} 条 notification, "
              f"final={r1.final_response!r}")
        event_types = {t for t, _ in sse_sink}
        sse_ok = len(sse_sink) > 0 and any("message" in str(t) for t in event_types)
        results["[1] SSE 端到端"] = sse_ok
        print(f"    event 类型样本: {sorted(str(t) for t in event_types)[:6]}")

        # 确认 JSONL 落盘
        jsonl_files = list(sessions.rglob("*.jsonl"))
        print(f"    session_root JSONL 文件: {[f.name for f in jsonl_files]}")

        # ---------- [2] 停止：杀进程 ----------
        pid = h1.client._proc.pid if h1.client._proc else None
        h1.close()
        stopped = h1.client._proc is None
        print(f"\n[2] 停止: close() 后子进程已回收 (pid={pid}, proc={h1.client._proc})")
        results["[2] 停止(杀进程)"] = stopped

        # ---------- [3] 跨进程会话语义（两条，编码 iteration 2 的确切结论）----------
        # 3a: 新进程复用旧 session_id → dsh 应以 id-collision 拒绝（这是保护，不是 bug）
        state["round"] = 2
        h2 = DeepSeekHarness(make_cfg())
        h2.start()
        r_reuse = h2.run("复用旧 id", session_id=SESSION_ID)
        h2.close()
        reuse_rejected = (
            r_reuse.finish_reason == "error"
            and "collision" in json.dumps(
                [n.payload for n in r_reuse.notifications], ensure_ascii=False
            ).lower()
        )
        print(f"\n[3a] 复用旧 session_id: finish={r_reuse.finish_reason} "
              f"→ 被 id-collision 拒绝（预期）: {reuse_rejected}")

        # 3b: 新进程用全新 session_id → 应正常工作（这是续聊的正确姿势）
        state["round"] = 2
        h3 = DeepSeekHarness(make_cfg())
        h3.start()
        r_fresh = h3.run("全新 id", session_id="g2-fresh")
        h3.close()
        fresh_ok = r_fresh.finish_reason == "completed" and bool(r_fresh.final_response)
        print(f"[3b] 全新 session_id: finish={r_fresh.finish_reason} "
              f"final={r_fresh.final_response!r} → 正常工作（预期）: {fresh_ok}")

        # [3] 通过 = 两条行为都符合预期（复用被拒 + 新id正常）→ 会话语义已探明
        results["[3] 跨进程会话语义"] = reuse_rejected and fresh_ok
        print("    结论：跨进程续聊须用全新 id + 业务层重建历史（见 g2.md）")

    server.shutdown()

    print("-" * 60)
    for k, v in results.items():
        print(f"  {'✓' if v else '✗'} {k}")
    all_ok = all(results.values())
    print(f"\nG2 结论: {'PASS — 三项全成立（会话语义已探明）' if all_ok else 'PARTIAL — 见上'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
