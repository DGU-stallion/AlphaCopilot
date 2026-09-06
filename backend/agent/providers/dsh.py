"""dsh Agent Provider —— 与 dsh 的唯一耦合点（ADR-0007 决策 2）。

现 harness.py 的 HarnessSession 下沉于此，成为实现 agent.provider.AgentProvider 的
DshProvider。业务层只认 agent.provider 的中立抽象；所有 dsh 私有词汇
（profile / patches / cordis / session_root / text-delta / thinking）都被本模块吸收。

一会话一子进程 + 进程内固定一个 dsh session_id（沿用 T27/M0 结论，避免 id-collision）。

组合方式（对齐当前 dsh SDK 签名）：SDK 不再收 `cordis=`/`session_root=`，改用
`profile=` + `patches=`(tuple) + `dsh_home=` + `env`。生产组合 = 独立的 `sdk-minimal`
profile（自带 JSON-RPC server + llm-deepseek + agent + JSONL 会话，persona 读
`DSH_SYSTEM_PROMPT`）叠加一份本模块生成的 **patch**：挂 skills 服务 + skill 工具、
挂我们的 MCP server（run_python/get_quote/submit_backtest），并**停用持久 bash**
（合规底线 ADR-0007 决策 2：代码仅经 MCP 执行）。会话持久化根由 dsh_home 管理。

零业务逻辑：不碰数据库，不校验产出。只「起进程 / 发 prompt / 流事件 / 关进程」。
"""

from __future__ import annotations

import asyncio
import os
import sys
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
# 生产 dsh 组合（合规 persona + skills + MCP）。dsh 私有配置定义在**项目专属 profile**内
# （~/.dsh/profiles/alphacopilot-prod/{package.json,cordis.patch.yml}，方案 B），
# 业务层只经 env 注入路径变量。
_DEFAULT_MCP_SERVER = _REPO_ROOT / "backend" / "mcpserver" / "server.py"
_DEFAULT_SKILLS_DIR = _REPO_ROOT / "skills"

# 项目专属 profile（方案 B）：~/.dsh/profiles/alphacopilot-prod。
# = bundle @deepseek-ai/dsh-sdk-minimal（自洽基座）+ cordis.patch.yml（停 bash + pi-ai
# 注册 openai-completions/agnes 路由 + 会话根改 DSH_SESSION_ROOT + skills + 我们的 MCP）。
_PROD_PROFILE = "alphacopilot-prod"
_DSH_HOME = str(Path.home() / ".dsh")

# agnes 端点（openai-completions）。profile 内 pi-ai 路由的 baseURL 读 AGNES_BASE_URL。
_AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"

# deepseek 官方端点前缀（这些端点用内置 deepseek-official provider；其余走 openai-completions）。
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


def _provider_for(base_url: str | None) -> str:
    """按端点选 dsh provider：官方 deepseek → deepseek-official；其余 → openai-completions。"""
    return "deepseek-official" if _is_deepseek_official(base_url) else "openai-completions"


class DshProvider:
    """dsh 运行时的 AgentProvider 实现。一实例 = 一会话 = 一子进程。"""

    def __init__(self, spec: ProviderSpec) -> None:
        self._spec = spec
        self._harness: Any = None
        self._dsh_session_id = f"conv-{uuid.uuid4().hex[:12]}"  # 全新 id，避免 collision
        self._lock = threading.Lock()  # 串行化 turn（同一进程同一时刻一个 turn）
        self._closed = False
        self._dsh_home: str | None = None  # dsh home（~/.dsh，profile 从此处找）

    def start(self) -> None:
        """起子进程 + initialize。initialize 成功即证明 MCP 挂载 + skills 服务就绪。

        对齐当前 dsh SDK 签名：profile=alphacopilot-prod（项目专属 profile，方案 B）
        + dsh_home=~/.dsh（profile 从 <dsh_home>/profiles/ 找）+ env（persona / MCP /
        skills / agnes 路由 / 代理 注入）。provider 按端点选：官方→deepseek-official，
        非官方（agnes）→openai-completions。
        """
        from deepseek_harness import DeepSeekHarness, DeepSeekHarnessConfig

        spec = self._spec
        mcp_server = str(_DEFAULT_MCP_SERVER)
        skills_dir = str(spec.skills_dir) if spec.skills_dir else str(_DEFAULT_SKILLS_DIR)

        # node carrier 解析发生在 spawn 前的**父进程**，读 os.environ（cfg.env 太晚）；
        # exe carrier 未构建的开发环境必须走 node。不覆盖调用方已显式设定的模式。
        os.environ.setdefault("DSH_RUNTIME_MODE", "node")

        dsh_home = _DSH_HOME
        Path(dsh_home).mkdir(parents=True, exist_ok=True)
        self._dsh_home = dsh_home

        # 会话持久化根：本会话 workspace 下（profile 的 sessions row 读 DSH_SESSION_ROOT），
        # 避免与 ~/.dsh/sessions 里其它 profile 的 .jsonl.zstd 会话在 compression 上冲突。
        session_root = str(spec.workspace / ".sessions")

        # profile 内 !!js process.env.* 需要这些变量；persona 承载合规底线（模型可见）。
        env: dict[str, str] = {
            "DSH_RUNTIME_MODE": os.environ.get("DSH_RUNTIME_MODE", "node"),
            "DSH_HOME": dsh_home,
            "DSH_SYSTEM_PROMPT": spec.system_prompt,
            "DSH_SESSION_ROOT": session_root,
            "DSH_CWD": str(spec.workspace),
            "ALPHACOPILOT_MCP_PY": sys.executable,
            "ALPHACOPILOT_MCP_SERVER": mcp_server,
            "ALPHACOPILOT_SKILLS_DIR": skills_dir,
            "AGNES_BASE_URL": spec.base_url or _AGNES_BASE_URL,
            "DSH_TELEMETRY_DISABLED": "1",
            # agnes（境外）走 http(s) 代理；socks 的 all_proxy dsh 不支持会警告直连，置空避免干扰。
            "all_proxy": "",
            "ALL_PROXY": "",
        }
        for proxy_var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
            val = os.environ.get(proxy_var)
            if val:
                env[proxy_var] = val

        # 非 deepseek 官方端点把 max_tokens 收敛到端点上限内（agnes 上限 65536）。
        max_tokens: int | None = None
        if not _is_deepseek_official(spec.base_url):
            max_tokens = _NON_OFFICIAL_MAX_TOKENS

        cfg = DeepSeekHarnessConfig(
            provider=_provider_for(spec.base_url),
            model=spec.model or "agnes-2.5-flash",
            max_tokens=max_tokens,
            cwd=str(spec.workspace),
            profile=_PROD_PROFILE,
            dsh_home=dsh_home,
            env=env,
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
        # 当前 SDK（sdk-minimal）多数情况把整段回复放在单条 assistant/message 里，
        # 不逐字发 assistant/chunk。为让 SSE 也拿到 text_delta（而非只在 turn_end 收全文），
        # 若本轮没出现任何 chunk 增量，就把 assistant/message 的整段文本作为一条 text_delta 发出。
        # 若 runtime 确实逐字发 chunk（streaming），则以 chunk 为准、跳过 message 全文（避免重复）。
        saw_chunk = {"v": False}

        def on_notification(n: Any) -> None:
            if n.method != "session.event":
                return
            ev = n.payload.get("event", {})
            if ev.get("type") == "assistant/chunk":
                item = _translate(ev)
                if item is not None:
                    if item.kind == EVENT_TEXT_DELTA:
                        saw_chunk["v"] = True
                    loop.call_soon_threadsafe(queue.put_nowait, item)
                return
            if ev.get("type") == "assistant/message":
                if not saw_chunk["v"]:
                    text = _message_text(ev)
                    if text:
                        loop.call_soon_threadsafe(
                            queue.put_nowait,
                            AgentEvent(kind=EVENT_TEXT_DELTA, payload={"text": text}),
                        )
                return
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
        """杀子进程。幂等。（profile 常驻磁盘，无临时文件需清理。）"""
        if self._closed:
            return
        self._closed = True
        if self._harness is not None:
            self._harness.close()
            self._harness = None

    def is_alive(self) -> bool:
        """子进程是否存活 —— 用于进程泄漏测试。"""
        if self._harness is None:
            return False
        proc = getattr(self._harness.client, "_proc", None)
        return proc is not None


def _message_text(ev: dict[str, Any]) -> str:
    """从一条 assistant/message 事件提取整段文本。

    wire 形状：data.message.content = [{type:'text', text:...}, ...]（少数变体把
    content 直接放在 data 下）。拼接所有 text block。
    """
    data = ev.get("data")
    if not isinstance(data, dict):
        return ""
    message = data.get("message")
    owner = message if isinstance(message, dict) else data
    content = owner.get("content")
    if not isinstance(content, list):
        return ""
    parts = [
        str(block.get("text") or "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "".join(parts)


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
