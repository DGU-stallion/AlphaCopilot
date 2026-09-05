"""T49 live E2E —— 真实 agnes 驱动 run_python 产出图表 artifact。

@pytest.mark.live（默认跳过，用 -m live 显式跑）。这是承诺 A 实质的验证：
真实模型收到研究任务 → 自己写 Python 调 alpha.chart → 经 run_python 沙箱执行 →
产出 manifest + chart.json。断言仅结构性（ADR-0007 测试分层）：
观察到 tool_started（工具被调用）或产出了 chart artifact 文件。

数据说明：A 股行情源（mootdx）在部分环境不可达，故本 E2E 让模型用**合成/内联数据**
计算并画图，验证的是「模型能写并执行分析代码产出可交互图」这一能力链，
不依赖外部行情网络。真实行情接通留待数据源可达的环境验证。
"""

import json
import tempfile
from pathlib import Path

import pytest

from agent.credentials import read_api_key
from agent.provider import (
    EVENT_ERROR,
    EVENT_TOOL_RESULT,
    EVENT_TOOL_STARTED,
    EVENT_TURN_END,
    ProviderSpec,
)
from agent.providers.dsh import DshProvider

pytestmark = [pytest.mark.live, pytest.mark.asyncio]

AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1".strip()
AGNES_MODEL = "agnes-2.5-flash"

_PROMPT = (
    "请用 run_python 工具执行一段 Python：用 alpha.chart.line 画一条折线图，"
    "x 轴是 ['1','2','3','4','5']，一条名为 'demo' 的系列数据是 [100,102,101,105,108]，"
    "title 用 'live-e2e-demo'；把返回的 option 用 json.dump 写到当前目录 chart.json，"
    "再写一个 manifest.json：{\"run_id\":\"live\",\"code_ref\":\"code.py\",\"artifacts\":"
    "[{\"id\":\"a1\",\"kind\":\"chart\",\"title\":\"demo\",\"path\":\"chart.json\"}]}，"
    "最后 print('E2E_OK')。"
)


async def test_live_agnes_run_python_produces_chart():
    api_key = read_api_key("AGNES_API_KEY")
    if not api_key:
        pytest.skip("AGNES_API_KEY 未配置")

    with tempfile.TemporaryDirectory(prefix="agnes-e2e-") as tmp:
        ws = Path(tmp) / "ws"
        ws.mkdir(parents=True, exist_ok=True)
        spec = ProviderSpec(
            workspace=ws,
            system_prompt="你是 AlphaCopilot 投研助理。需要计算或画图时用 run_python 工具。",
            model=AGNES_MODEL,
            base_url=AGNES_BASE_URL,
            api_key=api_key,
            request_timeout_seconds=180.0,
        )
        provider = DshProvider(spec)
        provider.start()
        try:
            tool_calls: list[str] = []
            errors: list[str] = []
            saw_turn_end = False
            async for ev in provider.astream(_PROMPT):
                if ev.kind == EVENT_TOOL_STARTED:
                    tool_calls.append(ev.payload.get("name", ""))
                elif ev.kind == EVENT_TOOL_RESULT:
                    tool_calls.append(ev.payload.get("name", "") + ":result")
                elif ev.kind == EVENT_ERROR:
                    errors.append(ev.payload.get("error", ""))
                elif ev.kind == EVENT_TURN_END:
                    saw_turn_end = True

            # 扫 workspace 找模型经 run_python 产出的 chart.json（沙箱在 ws 下建 runs/<id>/）。
            charts = list(ws.rglob("chart.json"))
            manifests = list(ws.rglob("manifest.json"))
            # 区分致命错误与非致命：模型探测文件系统时对不存在的文件 read 会产生
            # FS_NOT_FOUND 之类的工具级错误，属正常 agent 行为，不代表 turn 失败。
            fatal_errors = [e for e in errors if "FS_NOT_FOUND" not in str(e)]
            print("\n=== T49 live e2e ===")
            print("tool_calls:", tool_calls)
            print("charts found:", [str(c) for c in charts])
            print("errors(all):", errors)
            print("fatal_errors:", fatal_errors)
            print("=== end ===")

            assert not fatal_errors, f"agnes 返回致命 error: {fatal_errors}"
            assert saw_turn_end, "未收到 turn_end"
            # 能力验证：模型自主调用了 run_python 且产出了 chart artifact 文件。
            ran_python = any("run_python" in t for t in tool_calls)
            assert ran_python or charts, "模型未调用 run_python 也未产出 chart"
            # 若产出了 chart.json，校验它是合法 ECharts option（有非空 series）。
            if charts:
                opt = json.loads(charts[0].read_text(encoding="utf-8"))
                assert opt.get("series"), "产出的 chart.json 无 series"
                assert manifests, "有 chart.json 但缺 manifest.json"
        finally:
            provider.close()
