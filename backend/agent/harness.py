"""dsh 适配层 —— 与 dsh 的唯一耦合点（T27）。

职责：把 dsh 的 Python SDK（阻塞式 `run(prompt, on_notification=cb)`）包成
asyncio 友好的「一会话一子进程」流式接口，供 api 层的 SSE 端点消费。

设计约束（源自 M0 spike 结论）：
- G1：SDK 用自写 cordis.yml 起 runtime 子进程，挂我们的 MCP server。
- G2：同一子进程内、同一 dsh session_id 连发多轮，session 内记忆可用；
      但**跨进程复用磁盘上已存在的 session_id 会被 dsh 以 id-collision 拒绝**。
      因此：一个会话 = 一个存活的子进程 + 一个进程内固定的 dsh session_id；
      进程结束后若要续聊，由业务层从自己的 DB 重建上下文喂入新子进程（新 id）。
- 线程 + 队列 → asyncio：`run()` 是阻塞调用且回调在其内部线程触发，
      用 `loop.call_soon_threadsafe` 把 notification 投递进 asyncio.Queue，
      对外暴露 `async for` 事件流。

零业务逻辑：不碰数据库，不校验产出。只负责「起进程 / 发 prompt / 流事件 / 关进程」。
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# SDK 与 runtime 闭包路径（M0 已构建 carrier）。
_SDK_PATHS = [
    "/Users/a19150/Project/deepseek-harness/python/sdk/src",
    "/Users/a19150/Project/deepseek-harness/python/sdk-runtime/src",
]
for _p in _SDK_PATHS:
    if _p not in sys.path and Path(_p).exists():
        sys.path.insert(0, _p)

_REPO_ROOT = Path(__file__).resolve().parents[2]
# 默认复用 G1 spike 的 cordis 组合（已验证可挂 MCP + JSONL 持久化）。
_DEFAULT_CORDIS = _REPO_ROOT / "docs" / "spikes" / "g1" / "cordis.yml"
_DEFAULT_MCP_SERVER = _REPO_ROOT / "docs" / "spikes" / "g1" / "mcp_server_min.py"


@dataclass
class HarnessSettings:
    """一会话子进程的运行参数。keyless 测试可传 base_url/api_key 指向 mock 端点。"""

    workspace: str
    session_root: str
    model: str = "deepseek-v4-flash"
    cordis: str = str(_DEFAULT_CORDIS)
    mcp_python: str = sys.executable
    mcp_server: str = str(_DEFAULT_MCP_SERVER)
    system_prompt: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    request_timeout_seconds: float = 120.0


@dataclass
class StreamEvent:
    """归一化后的对外事件。type 取自 dsh session.event 的 event.type，或适配层元事件。"""

    type: str
    payload: dict[str, Any]


# 队列结束哨兵。
_DONE = object()


class HarnessSession:
    """一个会话对应一个 dsh 子进程；进程内固定一个 dsh session_id。"""

    def __init__(self, settings: HarnessSettings) -> None:
        self._settings = settings
        self._harness: Any = None
        self._dsh_session_id = f"conv-{uuid.uuid4().hex[:12]}"  # 全新 id，避免 collision
        self._lock = threading.Lock()  # 串行化 turn（一个进程同一时刻只跑一个 turn）
        self._closed = False

    @property
    def dsh_session_id(self) -> str:
        return self._dsh_session_id

    def start(self) -> None:
        """起子进程 + initialize。initialize 成功即证明 MCP 挂载完成（G1-B）。"""
        from deepseek_harness import DeepSeekHarness, DeepSeekHarnessConfig

        s = self._settings
        # cordis.yml 的 !!js process.env.* 需要这些环境变量。
        os.environ.setdefault("G1_MCP_PY", s.mcp_python)
        os.environ.setdefault("G1_MCP_SERVER", s.mcp_server)
        if s.system_prompt:
            os.environ["DSH_SYSTEM_PROMPT"] = s.system_prompt

        cfg = DeepSeekHarnessConfig(
            model=s.model,
            cwd=s.workspace,
            session_root=s.session_root,
            cordis=s.cordis,
            base_url=s.base_url,
            api_key=s.api_key,
            request_timeout_seconds=s.request_timeout_seconds,
        )
        self._harness = DeepSeekHarness(cfg)
        self._harness.start()

    async def astream(self, prompt: str):
        """发一个 prompt，异步产出归一化 StreamEvent，直到 turn 结束。

        用法：
            async for ev in session.astream("你好"):
                ...  # ev.type in {assistant/chunk, assistant/message, ...}
        turn 的最终结果通过末尾一条 type='turn/final' 的元事件带出（含 final_response）。
        """
        if self._harness is None:
            raise RuntimeError("HarnessSession 未 start()")
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def on_notification(n: Any) -> None:
            # 只转发 session.event；其余（request/header 等）忽略。
            if n.method == "session.event":
                ev = n.payload.get("event", {})
                item = StreamEvent(type=ev.get("type", "unknown"), payload=ev)
                loop.call_soon_threadsafe(queue.put_nowait, item)

        def run_turn() -> Any:
            with self._lock:
                return self._harness.run(
                    prompt,
                    session_id=self._dsh_session_id,
                    on_notification=on_notification,
                )

        # 在线程池跑阻塞的 run()，结束后投递哨兵 + final 元事件。
        async def driver() -> None:
            try:
                result = await asyncio.to_thread(run_turn)
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    StreamEvent(
                        type="turn/final",
                        payload={
                            "final_response": result.final_response,
                            "finish_reason": result.finish_reason,
                        },
                    ),
                )
            except Exception as e:  # noqa: BLE001
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    StreamEvent(type="turn/error", payload={"error": f"{type(e).__name__}: {e}"}),
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
        """杀子进程（G2 已验证：close 后子进程回收）。幂等。"""
        if self._closed:
            return
        self._closed = True
        if self._harness is not None:
            self._harness.close()
            self._harness = None

    def is_process_alive(self) -> bool:
        """子进程是否存活 —— 用于进程泄漏测试。"""
        if self._harness is None:
            return False
        proc = getattr(self._harness.client, "_proc", None)
        return proc is not None
