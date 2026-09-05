#!/usr/bin/env python3
"""开发用 keyless mock 模型端点（仅供网页交互形态验收，非真实 LLM）。

对外提供 OpenAI 兼容的 /v1/chat/completions（SSE 流）。按**用户最后一句话**的关键词
分流出三种脚本化行为，让你在前端网页上试出承诺 A / D 的交互形态：

  含「相关」            → tool_call run_python：用 alpha.chart.heatmap 产相关性热力图
  含「回测」/「金叉」   → tool_call submit_backtest：提交回测 job（净值+回撤+指标）
  其它                  → 纯文字逐字回复

所有回复末尾带合规口径。工具结果回流后返回文字结论。
这是 B 方案（keyless）：内容是脚本化的，不是真实推理。
"""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8999

# —— 相关性场景：agent 执行的画图代码（沙箱内 import alpha）——
_HEATMAP_CODE = r"""
import json
from alpha import chart
labels = ["茅台", "五粮液", "泸州老窖", "洋河", "沪深300"]
matrix = [
    [1.00, 0.82, 0.78, 0.71, 0.55],
    [0.82, 1.00, 0.80, 0.69, 0.52],
    [0.78, 0.80, 1.00, 0.72, 0.50],
    [0.71, 0.69, 0.72, 1.00, 0.48],
    [0.55, 0.52, 0.50, 0.48, 1.00],
]
option = chart.heatmap(labels, matrix, title="白酒板块与沪深300 相关性（近一年）")
json.dump(option, open("chart.json","w",encoding="utf-8"), ensure_ascii=False)
manifest = {"run_id":"web","code_ref":"code.py","artifacts":[
    {"id":"a1","kind":"chart","title":"白酒相关性热力图","path":"chart.json"}]}
json.dump(manifest, open("manifest.json","w",encoding="utf-8"), ensure_ascii=False)
print("HEATMAP_DONE")
"""

# —— 回测场景：合成收盘价（先跌后涨，触发 20/60 金叉）——
_CLOSES = [100.0 - i for i in range(60)] + [40.0 + i * 1.5 for i in range(70)]

_CONCLUSION_CORR = "白酒板块内部相关性偏高（0.7~0.8），与沪深300 相关性中等（约0.5）。以上为客观数据，不构成投资建议。"
_CONCLUSION_BT = "已提交 20/60 金叉回测 job，完成后展示净值与回撤及关键指标。以上为客观回测，不构成投资建议。"
_CHAT = "我是 AlphaCopilot 投研助理。我可以做相关性分析、回测等；只做客观数据整理，不推荐买卖、不预测涨跌。你可以试试「分析白酒板块相关性」或「用20/60金叉回测茅台」。"


def _sse(chunks):
    return b"".join(f"data: {json.dumps(c)}\n\n".encode() for c in chunks) + b"data: [DONE]\n\n"


def _tool_call(call_id, name, args):
    return [
        {"choices": [{"delta": {"role": "assistant", "content": None}}]},
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "id": call_id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)},
        }]}}]},
        {"choices": [{"delta": {"content": ""}, "finish_reason": "tool_calls"}]},
    ]


def _text(text):
    out = [{"choices": [{"delta": {"role": "assistant", "content": None}}]}]
    for ch in text:
        out.append({"choices": [{"delta": {"content": ch}}]})
    out.append({"choices": [{"delta": {"content": ""}, "finish_reason": "stop"}]})
    return out


def _user_intent_text(messages):
    """拼接所有真实用户输入（跳过 dsh 注入的 <system-reminder> skill 目录），用于关键词分流。"""
    parts = []
    for m in messages:
        if not isinstance(m, dict) or m.get("role") != "user":
            continue
        c = m.get("content")
        if isinstance(c, str):
            text = c
        elif isinstance(c, list):
            text = " ".join(str(x.get("text", "")) for x in c if isinstance(x, dict))
        else:
            continue
        if "<system-reminder>" in text:
            continue
        parts.append(text)
    return " ".join(parts)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(n) or b"{}")
        messages = body.get("messages", [])
        has_tool_result = any(
            isinstance(m, dict) and m.get("role") == "tool" for m in messages
        )
        user = _user_intent_text(messages)

        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()

        if has_tool_result:
            # 工具跑完，回文字结论（按上一轮意图挑选口径）。
            joined = json.dumps(messages, ensure_ascii=False)
            if "submit_backtest" in joined or "job_id" in joined:
                chunks = _text(_CONCLUSION_BT)
            else:
                chunks = _text(_CONCLUSION_CORR)
        elif "回测" in user or "金叉" in user:
            chunks = _tool_call("c-bt", "mcp__research__submit_backtest",
                                {"closes": _CLOSES, "fast": 20, "slow": 60, "symbol": "茅台"})
        elif "相关" in user:
            chunks = _tool_call("c-corr", "mcp__research__run_python", {"code": _HEATMAP_CODE})
        else:
            chunks = _text(_CHAT)

        self.wfile.write(_sse(chunks))
        self.wfile.flush()

    def log_message(self, *_):
        return


def main():
    srv = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"[dev-mock] OpenAI-compatible mock at http://127.0.0.1:{PORT}/v1", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
