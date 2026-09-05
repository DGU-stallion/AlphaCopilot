"""T42 真实 agnes 接通测试 —— @pytest.mark.live（默认跳过，用 -m live 显式跑）。

断言仅结构性（ADR-0007 测试分层）：非空 text_delta + 无 error + 有 turn_end。
不断言具体文案（真实模型输出不确定）。key 缺失时跳过（不算失败）。

agnes 端点走 openai-completions，不认 thinking/reasoningEffort —— 由 DshProvider
按 base_url 非 deepseek 官方自动去掉这两个字段（见 providers/dsh.py 归一化）。
"""

import tempfile
from pathlib import Path

import pytest

from agent.credentials import read_api_key
from agent.provider import (
    EVENT_ERROR,
    EVENT_TEXT_DELTA,
    EVENT_TURN_END,
    ProviderSpec,
)
from agent.providers.dsh import DshProvider

pytestmark = [pytest.mark.live, pytest.mark.asyncio]

# ~/.dsh/settings.yaml 里该值开头有字面制表符 \t，必须 .strip()。
AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1".strip()
AGNES_MODEL = "agnes-2.5-flash"


async def test_live_agnes_hello():
    api_key = read_api_key("AGNES_API_KEY")
    if not api_key:
        pytest.skip("AGNES_API_KEY 未配置（环境变量或 ~/.dsh/.credentials.yaml）")

    with tempfile.TemporaryDirectory(prefix="agnes-live-") as tmp:
        ws = Path(tmp) / "ws"
        ws.mkdir(parents=True, exist_ok=True)
        spec = ProviderSpec(
            workspace=ws,
            system_prompt="你是 AlphaCopilot 投研助理，用简洁中文回答。",
            model=AGNES_MODEL,
            base_url=AGNES_BASE_URL,
            api_key=api_key,
            request_timeout_seconds=120.0,
        )
        provider = DshProvider(spec)
        provider.start()
        try:
            text_parts: list[str] = []
            errors: list[str] = []
            saw_turn_end = False
            final_text = ""
            async for ev in provider.astream("你好，用一句话介绍你自己"):
                if ev.kind == EVENT_TEXT_DELTA:
                    text_parts.append(ev.payload.get("text", ""))
                elif ev.kind == EVENT_ERROR:
                    errors.append(ev.payload.get("error", ""))
                elif ev.kind == EVENT_TURN_END:
                    saw_turn_end = True
                    final_text = ev.payload.get("final_text", "")

            streamed = "".join(text_parts)
            # 打印真实输出供报告贴取。
            print("\n=== agnes live final_text ===")
            print(final_text or streamed)
            print("=== end ===")

            assert not errors, f"agnes 返回 error: {errors}"
            assert saw_turn_end, "未收到 turn_end"
            assert (streamed or final_text), "text_delta 为空"
        finally:
            provider.close()
