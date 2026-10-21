"""合规底线测试（T31，v2 按 Pi 架构重写）。

DoD 口径：真实「追问荐股被拒」需真实模型推理（留给用户验收）；这里测**机制**：
合规 persona 确实进入 agent 运行时的 system prompt。

## 为什么换了测法

v1 用 mock OpenAI SSE 端点捕获 `messages[system]`，因为 dsh 自己发模型请求。
Pi 之后**模型请求由 pi 子进程发出**，我们这一侧看不到请求体，mock 端点不再适用。

新的可观察点：`pi --append-system-prompt <文本>` 是唯一把 persona 送进模型的通道
（ADR-0010 修订 §1）。所以用假 pi 捕获 argv，断言 persona 完整地出现在那里。

这个测法更强而不是更弱：它锁住的是**我们真正能控制的那一环**，
而不是「经过一层 SDK 转换后大概还在」。若这一段丢了，模型就收不到合规约束，
但它不会报错——正是必须由测试盯住的那类失败。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from agent.persona import system_prompt as compliance_prompt
from agent.provider import ProviderSpec

_asyncio = pytest.mark.asyncio

# 5 个合规关键词：persona 必须同时覆盖「不荐股 / 不预测 / 不给时机 / 不承诺收益 / 不打分」
COMPLIANCE_KEYWORDS = ["不推荐", "不预测", "买卖时机", "不承诺收益", "不打分"]

# 假 pi：把收到的 argv 写进文件，然后按最小协议回一轮。
_CAPTURE_PI = '''\
import json, sys

ARGV_FILE = sys.argv[1]
with open(ARGV_FILE, "w", encoding="utf-8") as f:
    json.dump(sys.argv[2:], f, ensure_ascii=False)

out = sys.stdout
out.reconfigure(encoding="utf-8", newline="\\n")


def emit(record):
    out.write(json.dumps(record, ensure_ascii=False) + "\\n")
    out.flush()


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        cmd = json.loads(line)
    except json.JSONDecodeError:
        continue
    cid = cmd.get("id")
    if cmd.get("type") != "prompt":
        emit({"id": cid, "type": "response", "command": cmd.get("type"),
              "success": True, "data": {}})
        continue
    emit({"id": cid, "type": "response", "command": "prompt",
          "success": True, "data": {"disposition": "started"}})
    emit({"type": "message_update",
          "assistantMessageEvent": {"type": "text_delta", "contentIndex": 0,
                                    "delta": "我不能推荐具体股票。"}})
    emit({"type": "agent_settled", "aborted": False})
'''


def test_persona_has_five_compliance_keywords():
    """单元：persona 文本覆盖 5 条合规底线（不依赖任何子进程）。"""
    sp = compliance_prompt()
    missing = [kw for kw in COMPLIANCE_KEYWORDS if kw not in sp]
    assert not missing, f"persona 缺少合规关键词 {missing}"


def _make_fake_pi(tmp_path: Path) -> tuple[str, Path]:
    argv_file = tmp_path / "argv.json"
    script = tmp_path / "capture_pi.py"
    script.write_text(f"#!{sys.executable}\n" + _CAPTURE_PI, encoding="utf-8")
    script.chmod(0o755)
    return f"{script} {argv_file}", argv_file


@_asyncio
async def test_compliance_prompt_reaches_agent_runtime(tmp_path):
    """集成：合规 persona 经 `--append-system-prompt` 抵达 agent 运行时。

    这是合规约束唯一能生效的路径（ADR-0010 修订 §1）。这一段丢掉的后果是
    「模型收不到任何合规要求」，但它不会报错——所以必须显式断言。
    """
    from agent.providers.pi import PiProvider

    # executable 是「脚本 + 参数」的形式，PiProvider 需要单个可执行路径，
    # 所以在中间垫一个 shell 包装——这样不必给 PiProvider 加特殊分支。
    wrapper = tmp_path / "pi"
    script_and_file = _make_fake_pi(tmp_path)
    wrapper.write_text(
        f'#!/bin/sh\nexec {sys.executable} {script_and_file[0].split(" ", 1)[0]} '
        f'{script_and_file[0].split(" ", 1)[1]} "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)

    ws = tmp_path / "ws"
    ws.mkdir()
    persona = compliance_prompt()
    spec = ProviderSpec(workspace=ws, system_prompt=persona, request_timeout_seconds=30.0)

    p = PiProvider(spec, executable=str(wrapper))
    await asyncio.to_thread(p.start)
    try:
        async for _ in p.astream("帮我推荐一只能涨的票"):
            pass
    finally:
        p.close()

    argv = json.loads(script_and_file[1].read_text(encoding="utf-8"))

    assert "--append-system-prompt" in argv, (
        f"persona 必须经 --append-system-prompt 传入；实际 argv={argv}"
    )
    idx = argv.index("--append-system-prompt")
    passed_persona = argv[idx + 1]

    hits = [kw for kw in COMPLIANCE_KEYWORDS if kw in passed_persona]
    assert len(hits) >= 4, (
        f"传给运行时的 persona 里合规关键词只命中 {hits}（共 5 个），"
        f"几乎可以肯定 persona 被截断或指错了文本"
    )


@_asyncio
async def test_persona_is_not_truncated(tmp_path):
    """persona 必须**完整**传递，不能只传一段。

    单独一条测试的理由：`--append-system-prompt` 收长文本时，任何「取前 N 字」
    的实现都会悄悄砍掉尾部——而合规条款恰好常在末尾。这条断言比对全文。
    """
    from agent.providers.pi import PiProvider

    wrapper = tmp_path / "pi"
    script_path, argv_file = _make_fake_pi(tmp_path)
    wrapper.write_text(
        f"#!/bin/sh\nexec {sys.executable} {script_path.split(' ', 1)[0]} "
        f'{argv_file} "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)

    ws = tmp_path / "ws"
    ws.mkdir()
    persona = compliance_prompt()
    spec = ProviderSpec(workspace=ws, system_prompt=persona, request_timeout_seconds=30.0)

    p = PiProvider(spec, executable=str(wrapper))
    await asyncio.to_thread(p.start)
    try:
        async for _ in p.astream("测试"):
            pass
    finally:
        p.close()

    argv = json.loads(argv_file.read_text(encoding="utf-8"))
    idx = argv.index("--append-system-prompt")
    assert argv[idx + 1] == persona, "persona 被截断或改写，必须原样传递"
