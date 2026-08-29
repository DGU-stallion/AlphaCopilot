#!/usr/bin/env python3
"""G4 + G1-C keyless 验证：mock 模型端点 → 捕获 model-visible → 驱动真实工具执行。

原理（借用 deepseek-harness/scripts/smoke-python-runtime.py 的 keyless 手法）：
  起一个假的 OpenAI-兼容 SSE 端点，把 DEEPSEEK_BASE_URL 指过去。dsh runtime 发来的
  第一条 request body 里：
    - messages[system] = 组装后的 system prompt  → 验「合规 prompt 可见」(G4-合规)
    - tools[]           = 广告给模型的工具 schema → 验「get_quote 可见」(G1 工具可见)
                          以及 skill 工具是否出现   → 验「skills 可见」(G4-skills)
  mock 首轮返回一个对 mcp__research__get_quote 的 tool_call，驱动 runtime 真实执行我们的
  MCP 工具（走网络取茅台报价）→ 第二轮 tool 结果回来后 mock 收尾 → 验 G1-C 真实调用。

全程无需真实 DEEPSEEK_API_KEY（用假 key + 本地 mock 端点）。
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
CORDIS = HERE / "cordis.yml"
SKILLS_DIR = (Path(__file__).resolve().parents[3]
              / "packages/dsh-alphacopilot-desk/skills")

captured: dict[str, object] = {"first_body": None, "tool_result_seen": False, "quote_price": None}


def _tool_call_chunks(call_id, name, arguments):
    return [
        {"choices": [{"delta": {"role": "assistant", "content": None, "reasoning_content": ""}}]},
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "id": call_id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)},
        }]}}]},
        {"choices": [{"delta": {"content": ""}, "finish_reason": "tool_calls"},],
         "usage": {"prompt_tokens": 3, "completion_tokens": 3}},
    ]


def _text_chunks(text):
    return [
        {"choices": [{"delta": {"role": "assistant", "content": None, "reasoning_content": ""}}]},
        {"choices": [{"delta": {"content": text}}]},
        {"choices": [{"delta": {"content": ""}, "finish_reason": "stop"}],
         "usage": {"prompt_tokens": 3, "completion_tokens": 3}},
    ]


class MockModel(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(n))
        messages = body.get("messages", [])
        latest = messages[-1] if messages else {}

        # 首轮：记录 model-visible（system prompt + tools）
        if captured["first_body"] is None:
            captured["first_body"] = body

        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()

        # 若最新是 tool 结果 → G1-C 真实调用回来了，收尾
        if isinstance(latest, dict) and latest.get("role") == "tool":
            captured["tool_result_seen"] = True
            content = latest.get("content")
            text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            if "600519" in text:
                captured["quote_result_text"] = text[:300]
            chunks = _text_chunks("已获取数据。")
        else:
            # 首轮：让模型调用我们的 MCP 工具
            chunks = _tool_call_chunks("g4-call-1", "mcp__research__get_quote", {"codes": ["600519"]})

        for c in chunks:
            self.wfile.write(f"data: {json.dumps(c)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def log_message(self, *_):
        return


def main() -> int:
    print("=" * 60)
    print("G4 + G1-C: keyless model-visible 捕获 + 真实工具执行")
    print("=" * 60)

    server = HTTPServer(("127.0.0.1", 0), MockModel)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"mock model endpoint: http://127.0.0.1:{port}/v1")

    os.environ["G1_MCP_PY"] = sys.executable
    os.environ["G1_MCP_SERVER"] = str(G1_DIR / "mcp_server_min.py")
    os.environ["G4_SKILLS_DIR"] = str(SKILLS_DIR)
    print(f"skills dir: {SKILLS_DIR} ({len(list(SKILLS_DIR.glob('*.md')))} md files)")

    from deepseek_harness import DeepSeekHarness, DeepSeekHarnessConfig

    with tempfile.TemporaryDirectory(prefix="g4-") as tmp:
        tmp = Path(tmp).resolve()
        (tmp / "ws").mkdir(); (tmp / "s").mkdir()
        cfg = DeepSeekHarnessConfig(
            model="deepseek-v4-flash",
            cwd=str(tmp / "ws"),
            session_root=str(tmp / "s"),
            cordis=str(CORDIS),
            base_url=f"http://127.0.0.1:{port}/v1",
            api_key="sk-mock-keyless",
            request_timeout_seconds=90.0,
        )
        with DeepSeekHarness(cfg) as h:
            result = h.run("查询贵州茅台 600519 的最新股价。", session_id="g4")
            final = result.final_response

    server.shutdown()

    # ---- 断言 ----
    body = captured["first_body"] or {}
    sys_msgs = [m for m in body.get("messages", []) if isinstance(m, dict) and m.get("role") == "system"]
    sys_text = "\n".join(
        (m.get("content") if isinstance(m.get("content"), str)
         else json.dumps(m.get("content"), ensure_ascii=False))
        for m in sys_msgs
    )
    tool_names = {
        t.get("function", {}).get("name")
        for t in body.get("tools", []) if isinstance(t, dict)
    }

    print("-" * 60)
    # G1 工具可见
    quote_visible = "mcp__research__get_quote" in tool_names
    print(f"[1] MCP 工具可见: {'PASS' if quote_visible else 'FAIL'} "
          f"(get_quote {'∈' if quote_visible else '∉'} tools; 共 {len(tool_names)} 个)")
    # G4 skills 可见（skill 工具存在，或 system 里出现 skill 目录）
    skill_tool_visible = "skill" in tool_names
    skills_in_sys = any(name in sys_text for name in
                        ["candlestick", "technical", "fundamental", "risk", "sentiment", "skill"])
    skills_visible = skill_tool_visible or skills_in_sys
    print(f"[2] skills 可见: {'PASS' if skills_visible else 'FAIL'} "
          f"(skill 工具={skill_tool_visible}, system 含skill目录={skills_in_sys})")
    # G4 合规 prompt 可见
    compliance_markers = ["不推荐", "不预测", "买卖时机", "不承诺收益", "不打分"]
    hit = [k for k in compliance_markers if k in sys_text]
    compliance_visible = len(hit) >= 2
    print(f"[3] 合规 prompt 可见: {'PASS' if compliance_visible else 'FAIL'} (命中: {hit})")
    # G1-C 真实工具执行
    call_executed = captured.get("tool_result_seen") and "quote_result_text" in captured
    print(f"[4] 真实工具执行(G1-C): {'PASS' if call_executed else 'FAIL'} "
          f"(tool结果回流={captured.get('tool_result_seen')})")
    if "quote_result_text" in captured:
        print(f"    工具结果摘要: {captured['quote_result_text'][:120]!r}")

    print("-" * 60)
    all_ok = quote_visible and skills_visible and compliance_visible and call_executed
    print(f"G4+G1-C 结论: {'PASS — 全部四项成立' if all_ok else 'FAIL — 见上方'}")
    print(f"  final_response: {final[:80]!r}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
