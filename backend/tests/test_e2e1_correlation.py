"""E2E-1 相关性场景 —— artifact 摄取链路（无网络、无模型、无凭据）。

## 这条测试到底在验什么

它验的是**业务层**这一段：agent 产出落到 `workspace/runs/<id>/` 之后，
`session_manager` 会不会扫描、校验、把 artifact 落库、挂到消息、发事件。
这是「对话即研究」的产品闭环里最容易出错的一环（漏扫、校验过严/过松、
事件没发、挂错消息），而且出错时不会崩——只是界面上一片空白。

## v1 → v2 的测法变化

v1 用 mock OpenAI SSE 端点，让「模型」返回一个 `run_python` 的 tool_call，
再真的执行。Pi 之后我们拦不到模型请求，也不该在业务层测试里跑真模型。

所以现在直接注入一个假 provider：它收到 prompt 后**自己执行**agent 本该执行的
那段代码（写 chart.json + manifest.json），然后吐结论文字。
这样跳过的是「模型是否愿意调工具」这个不确定环节（那是模型能力问题，
不该由 CI 断言），保留的是我们要守的确定性链路。

真链路（真模型 → 真调 MCP 工具 → 真执行 → 真产物）在 M1-3 已用真 pi 验证过。
"""

from __future__ import annotations

import asyncio
import json
import socket
import tempfile
from pathlib import Path

import httpx
import uvicorn

from agent.provider import AgentEvent
from api.app import create_app

# agent 在 workspace 里跑的代码：用 alpha.chart.heatmap 产热力图 + 写 manifest.json。
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

# provenance：这是 agent 自己写代码算的（走 run_python），属于 agent 轨。
# 即使这里谎称 deterministic 也会被服务端降级 —— 见 tests/test_provenance.py。
manifest = {
    "run_id": "e2e1",
    "code_ref": "code.py",
    "artifacts": [
        {"id": "a1", "kind": "chart", "title": "白酒相关性热力图", "path": "chart.json",
         "inputs": {"symbols": labels},
         "provenance": {"kind": "agent", "runId": "e2e1", "codeHash": "sha256:e2e1",
                        "dataAsOf": "2025-12-31"}},
    ],
}
with open("manifest.json", "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False)
print("HEATMAP_DONE")
"""

_CONCLUSION = (
    "白酒板块内部相关性高（0.6~0.8），与沪深300 相关性中等（约0.5）。"
    "以上为客观数据，不构成投资建议。"
)


class _ProducingProvider:
    """假 provider：在 workspace 里真实执行 _AGENT_CODE，然后吐结论。

    「执行」这一步不省：artifact 摄取的前提就是 runs/<id>/ 下真有文件。
    如果这里只 mock 出一条 tool_result 事件，测到的就只是「事件转发」，
    而不是「产物被找到并校验落库」——后者才是这条 E2E 的意义。
    """

    def __init__(self, workspace: Path, code: str, conclusion: str) -> None:
        self._workspace = workspace
        self._code = code
        self._conclusion = conclusion
        self._closed = False

    def start(self) -> None:
        return

    def abort(self, reason: str = "") -> None:
        return

    def close(self) -> None:
        self._closed = True

    def is_alive(self) -> bool:
        return not self._closed

    async def astream(self, prompt: str):
        from agent.provider import EVENT_TEXT_DELTA, EVENT_TURN_END

        run_dir = self._workspace / "runs" / "e2e1"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "code.py").write_text(self._code, encoding="utf-8")

        proc = await asyncio.create_subprocess_exec(
            __import__("sys").executable,
            str(run_dir / "code.py"),
            cwd=str(run_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_backend_env(),
        )
        stdout, stderr = await proc.communicate()
        assert proc.returncode == 0, f"agent 代码执行失败: {stderr.decode()[:500]}"
        assert b"HEATMAP_DONE" in stdout

        for ch in self._conclusion:
            yield AgentEvent(kind=EVENT_TEXT_DELTA, payload={"text": ch})
        yield AgentEvent(
            kind=EVENT_TURN_END,
            payload={"final_text": self._conclusion, "finish_reason": "stop"},
        )


def _backend_env() -> dict:
    """让子进程能 import alpha/research。"""
    import os
    import sys

    env = dict(os.environ)
    backend = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = backend + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHON"] = sys.executable
    return env


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def test_e2e1_correlation_heatmap_in_chat_stream():
    """端到端：agent 产出热力图 → 摄取 → 挂到消息 → SSE 事件 → 前端可取到 option。"""
    with tempfile.TemporaryDirectory(prefix="e2e1-") as tmp:

        def factory(session_id: str):
            ws = Path(tmp) / session_id / "ws"
            ws.mkdir(parents=True, exist_ok=True)
            return _ProducingProvider(ws, _AGENT_CODE, _CONCLUSION), ws

        app = create_app(
            db_path=":memory:", workspace_root=Path(tmp), provider_factory=factory
        )
        port = _free_port()
        srv = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
        )
        task = asyncio.create_task(srv.serve())
        for _ in range(100):
            if srv.started:
                break
            await asyncio.sleep(0.05)

        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}", trust_env=False
        ) as client:
            sid = (await client.post("/api/sessions")).json()["session_id"]
            await client.post(
                f"/api/sessions/{sid}/messages",
                json={"content": "分析近一年白酒板块 5 只标的与沪深300 的相关性"},
            )

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

            conclusion = "".join(deltas)
            assert "相关性" in conclusion, f"结论未含相关性: {conclusion!r}"
            assert "不构成投资建议" in conclusion, "结论缺合规口径"

            assert "artifact/attached" in seen_types, f"未发 artifact 事件，实际: {seen_types}"

            msgs = (await client.get(f"/api/sessions/{sid}/messages")).json()
            assistant = [m for m in msgs if m["role"] == "assistant"][-1]
            arts = assistant["artifacts"]
            assert len(arts) >= 1, f"assistant 消息没挂 artifact：{assistant}"

            chart_art = next(a for a in arts if a["kind"] == "chart")
            assert json.loads(chart_art["provenance"])["kind"] == "agent", (
                "agent 自己写代码算的图应带 AI 角标（provenance.kind=agent），"
                f"实际 {chart_art.get('provenance')}"
            )
            assert chart_art["payload"]["series"][0]["type"] == "heatmap", (
                f"chart payload 不是 heatmap option：{str(chart_art['payload'])[:300]}"
            )

        srv.should_exit = True
        await task
        app.state.manager.close_all()


def test_agent_code_produces_valid_manifest_on_its_own(tmp_path):
    """单元：_AGENT_CODE 独立跑就能产出合法 manifest。

    单独一条的理由：上面那条 E2E 失败时，很难分清是「agent 代码本身有问题」
    还是「摄取链路有问题」。这条把第一个变量单独钉住。
    """
    run_dir = tmp_path / "runs" / "e2e1"
    run_dir.mkdir(parents=True)
    (run_dir / "code.py").write_text(_AGENT_CODE, encoding="utf-8")

    import subprocess

    r = subprocess.run(
        [__import__("sys").executable, "code.py"],
        cwd=run_dir,
        capture_output=True,
        text=True,
        env=_backend_env(),
        timeout=60,
    )
    assert r.returncode == 0, f"执行失败: {r.stderr[:500]}"
    assert "HEATMAP_DONE" in r.stdout

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_id"] == "e2e1"
    assert manifest["artifacts"][0]["kind"] == "chart"

    option = json.loads((run_dir / "chart.json").read_text(encoding="utf-8"))
    assert option["series"][0]["type"] == "heatmap"
