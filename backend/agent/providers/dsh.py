"""dsh Agent Provider —— 与 dsh 的唯一耦合点（ADR-0007 决策 2）。

现 harness.py 的 HarnessSession 下沉于此，成为实现 agent.provider.AgentProvider 的
DshProvider。业务层只认 agent.provider 的中立抽象；所有 dsh 私有词汇
（cordis / session_root / text-delta / thinking / reasoningEffort）都被本模块吸收。

一会话一子进程 + 进程内固定一个 dsh session_id（沿用 T27/M0 结论，避免 id-collision）。

模型参数归一化（ADR-0007 决策 2 / 权衡）：cordis.yml 默认给 llm-deepseek 配了
thinking/reasoningEffort（deepseek 官方专用）。真实 agnes 端点走 openai-completions，
不认这两个字段（会 400）。DshProvider 在 start() 时按 base_url 是否 deepseek 官方
决定：非官方端点生成一份**去掉 thinking/reasoningEffort 两行**的临时 cordis，
使这两个字段完全不出现在 wire 上（serialize.js：thinking 未定义即不上 wire）。

零业务逻辑：不碰数据库，不校验产出。只「起进程 / 发 prompt / 流事件 / 关进程」。
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import tempfile
import threading
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from agent.provider import (
    EVENT_ERROR,
    EVENT_TEXT_DELTA,
    EVENT_TOOL_RESULT,
    EVENT_TOOL_STARTED,
    EVENT_TURN_END,
    AgentEvent,
    ProviderSpec,
)

# SDK 与 runtime 闭包路径（M0 已构建 carrier）。
_SDK_PATHS = [
    "/Users/a19150/Project/deepseek-harness/python/sdk/src",
    "/Users/a19150/Project/deepseek-harness/python/sdk-runtime/src",
]
for _p in _SDK_PATHS:
    if _p not in sys.path and Path(_p).exists():
        sys.path.insert(0, _p)

_REPO_ROOT = Path(__file__).resolve().parents[3]
# 生产 dsh 组合（合规 persona + skills + MCP）。dsh 私有配置定义在 agent 层内。
_DEFAULT_CORDIS = Path(__file__).resolve().parents[1] / "cordis.yml"
_DEFAULT_MCP_SERVER = _REPO_ROOT / "backend" / "mcpserver" / "server.py"
_DEFAULT_SKILLS_DIR = _REPO_ROOT / "skills"

# deepseek 官方端点前缀（仅这些端点启用 thinking/reasoningEffort）。
_DEEPSEEK_OFFICIAL_HOSTS = ("api.deepseek.com", "api.deepseek.cn")

# 非官方端点（openai-completions，如 agnes）的 max_tokens 上限。dsh 默认 256000
# 会被 agnes 以「max_tokens exceeds the limit of 65536」500 拒绝，故收敛到 65536。
_NON_OFFICIAL_MAX_TOKENS = 65536

# 队列结束哨兵。
_DONE = object()


def _is_deepseek_official(base_url: str | None) -> bool:
    """base_url 为空（=SDK 默认 deepseek 官方）或指向官方 host → 官方端点。"""
    if not base_url:
        return True
    return any(host in base_url for host in _DEEPSEEK_OFFICIAL_HOSTS)


def _cordis_without_thinking(cordis_text: str) -> str:
    """从 cordis.yml 文本删掉 llm-deepseek 下的 thinking / reasoningEffort 两行。

    非官方端点（openai-completions，如 agnes）不认这两个字段；删行后 serialize
    不会把 thinking 放上 wire（serialize.js: thinking 未定义 → {}）。
    只删这两行，其余组合原样保留（外科手术式）。
    """
    kept = [
        ln
        for ln in cordis_text.splitlines()
        if not re.match(r"\s*(thinking|reasoningEffort)\s*:", ln)
    ]
    return "\n".join(kept) + "\n"


class DshProvider:
    """dsh 运行时的 AgentProvider 实现。一实例 = 一会话 = 一子进程。"""

    def __init__(self, spec: ProviderSpec) -> None:
        self._spec = spec
        self._harness: Any = None
        self._dsh_session_id = f"conv-{uuid.uuid4().hex[:12]}"  # 全新 id，避免 collision
        self._lock = threading.Lock()  # 串行化 turn（同一进程同一时刻一个 turn）
        self._closed = False
        self._tmp_cordis: str | None = None  # 归一化后写出的临时 cordis 路径（若有）

    def start(self) -> None:
        """起子进程 + initialize。initialize 成功即证明 MCP 挂载完成。"""
        from deepseek_harness import DeepSeekHarness, DeepSeekHarnessConfig

        spec = self._spec
        mcp_server = str(_DEFAULT_MCP_SERVER)
        skills_dir = str(spec.skills_dir) if spec.skills_dir else str(_DEFAULT_SKILLS_DIR)
        # cordis.yml 的 !!js process.env.* 需要这些环境变量。
        os.environ["ALPHACOPILOT_MCP_PY"] = sys.executable
        os.environ["ALPHACOPILOT_MCP_SERVER"] = mcp_server
        os.environ["ALPHACOPILOT_SKILLS_DIR"] = skills_dir
        # 兼容旧 spike cordis 仍用的旧变量名（保持 spike 可跑）。
        os.environ.setdefault("G1_MCP_PY", sys.executable)
        os.environ.setdefault("G1_MCP_SERVER", mcp_server)
        # 合规底线：system_prompt 经 cordis persona 注入，对模型可见。
        os.environ["DSH_SYSTEM_PROMPT"] = spec.system_prompt

        # 模型参数归一化：非 deepseek 官方端点去掉 thinking/reasoningEffort，
        # 并把 max_tokens 收敛到端点上限内（dsh 默认 256000，agnes 上限 65536 → 会 500）。
        cordis_path = str(_DEFAULT_CORDIS)
        max_tokens: int | None = None
        if not _is_deepseek_official(spec.base_url):
            normalized = _cordis_without_thinking(_DEFAULT_CORDIS.read_text())
            fd, tmp = tempfile.mkstemp(prefix="cordis-agnes-", suffix=".yml")
            with os.fdopen(fd, "w") as f:
                f.write(normalized)
            self._tmp_cordis = tmp
            cordis_path = tmp
            max_tokens = _NON_OFFICIAL_MAX_TOKENS

        cfg = DeepSeekHarnessConfig(
            model=spec.model or "deepseek-v4-flash",
            max_tokens=max_tokens,
            cwd=str(spec.workspace),
            session_root=str(spec.workspace / ".sessions"),
            cordis=cordis_path,
            base_url=spec.base_url,
            api_key=spec.api_key,
            request_timeout_seconds=spec.request_timeout_seconds,
        )
        self._harness = DeepSeekHarness(cfg)
        self._harness.start()

    def astream(self, prompt: str) -> AsyncIterator[AgentEvent]:
        """发一个 prompt，异步产出归一化 AgentEvent，直到 turn_end。"""
        return self._astream(prompt)

    async def _astream(self, prompt: str) -> AsyncIterator[AgentEvent]:
        if self._harness is None:
            raise RuntimeError("DshProvider 未 start()")
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def on_notification(n: Any) -> None:
            if n.method != "session.event":
                return
            ev = n.payload.get("event", {})
            item = _translate(ev)
            if item is not None:
                loop.call_soon_threadsafe(queue.put_nowait, item)

        def run_turn() -> Any:
            with self._lock:
                return self._harness.run(
                    prompt,
                    session_id=self._dsh_session_id,
                    on_notification=on_notification,
                )

        async def driver() -> None:
            try:
                result = await asyncio.to_thread(run_turn)
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    AgentEvent(
                        kind=EVENT_TURN_END,
                        payload={
                            "final_text": result.final_response,
                            "finish_reason": result.finish_reason,
                        },
                    ),
                )
            except Exception as e:  # noqa: BLE001
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    AgentEvent(kind=EVENT_ERROR, payload={"error": f"{type(e).__name__}: {e}"}),
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, _DONE)

        task = asyncio.create_task(driver())
        try:
            while True:
                item = await queue.get()
                if item is _DONE:
                    break
                yield item
        finally:
            await task

    def close(self) -> None:
        """杀子进程 + 清理临时 cordis。幂等。"""
        if self._closed:
            return
        self._closed = True
        if self._harness is not None:
            self._harness.close()
            self._harness = None
        if self._tmp_cordis is not None:
            try:
                os.unlink(self._tmp_cordis)
            except OSError:
                pass
            self._tmp_cordis = None

    def is_alive(self) -> bool:
        """子进程是否存活 —— 用于进程泄漏测试。"""
        if self._harness is None:
            return False
        proc = getattr(self._harness.client, "_proc", None)
        return proc is not None


def _translate(ev: dict[str, Any]) -> AgentEvent | None:
    """把一条 dsh session.event 翻译成中立 AgentEvent；无关事件返回 None。

    dsh wire 形状（SessionEventMap）：
      assistant/chunk : data.chunk = {type:'text-delta', text:...}（只在 text-delta 取文本）
      tool/call       : data = {callId, name, arguments}
      tool/result     : data = {message, error?, meta?}
    """
    ev_type = ev.get("type")
    data = ev.get("data")
    if not isinstance(data, dict):
        data = {}

    if ev_type == "assistant/chunk":
        chunk = data.get("chunk")
        if isinstance(chunk, dict):
            ctype = chunk.get("type")
            if ctype == "text-delta":
                text = chunk.get("text")
                if isinstance(text, str) and text:
                    return AgentEvent(kind=EVENT_TEXT_DELTA, payload={"text": text})
            elif ctype == "finish":
                # finish 可能带 error（如 agnes 端点报错）；正常结束由 turn_end 承载。
                reason = chunk.get("reason")
                if isinstance(reason, dict) and reason.get("kind") == "error":
                    failure = reason.get("failure") or reason.get("error") or {}
                    msg = failure.get("message") if isinstance(failure, dict) else str(failure)
                    return AgentEvent(kind=EVENT_ERROR, payload={"error": msg or "finish error"})
        return None

    if ev_type == "tool/call":
        return AgentEvent(
            kind=EVENT_TOOL_STARTED,
            payload={"name": data.get("name", ""), "args": data.get("arguments", "")},
        )

    if ev_type == "tool/result":
        err = data.get("error")
        if err is not None:
            return AgentEvent(kind=EVENT_ERROR, payload={"error": str(err)})
        return AgentEvent(
            kind=EVENT_TOOL_RESULT,
            payload={"name": "", "result": data.get("message")},
        )

    return None
