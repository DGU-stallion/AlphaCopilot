"""会话编排 —— 把 provider 的事件流桥到 SSE，并把消息落库（T28）。

职责：
- 每个产品会话映射一个存活的 AgentProvider 实例（一会话一运行时，见 ADR-0006 决策 5）。
- 用户发消息 → 落库 user message → 触发 agent turn → 流事件写入 per-session ring
  buffer（带单调递增 event_id）→ 订阅者（SSE）实时收到 → turn 结束落库 assistant message。
- SSE 断线重连：客户端带 Last-Event-ID，从 buffer 里补发之后的事件。

零 provider 细节泄漏：只依赖 agent.provider 的 AgentProvider / AgentEvent 中立契约，
不 import 任何具体 provider 实现，不出现任何运行时的私有词汇。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.provider import (
    EVENT_TEXT_DELTA,
    EVENT_TURN_END,
    AgentProvider,
)
from api.store import Store


@dataclass
class BufferedEvent:
    id: int
    type: str
    data: dict[str, Any]


@dataclass
class SessionRuntime:
    """一个会话的运行态：provider 运行时 + 事件 buffer + 订阅者。"""

    provider: AgentProvider
    workspace: str = ""  # 该会话 sandbox 根（其下 runs/<run_id>/）
    events: list[BufferedEvent] = field(default_factory=list)
    _subscribers: list[asyncio.Queue] = field(default_factory=list)
    _next_id: int = 1
    _ingested_runs: set[str] = field(default_factory=set)

    def _emit(self, ev_type: str, data: dict[str, Any]) -> BufferedEvent:
        be = BufferedEvent(id=self._next_id, type=ev_type, data=data)
        self._next_id += 1
        self.events.append(be)
        for q in list(self._subscribers):
            q.put_nowait(be)
        return be

    def subscribe(self, last_event_id: int | None = None) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        # 补发历史：
        #   last_event_id=None  → 全量补发（新客户端渲染整轮，避免错过已缓冲事件而挂起）
        #   last_event_id=N     → 只补 N 之后（断线重连续传）
        floor = last_event_id if last_event_id is not None else 0
        for be in self.events:
            if be.id > floor:
                q.put_nowait(be)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)


class SessionManager:
    """管理所有会话运行态。业务层唯一持有 provider 的地方。"""

    def __init__(self, store: Store, provider_factory, jobs=None) -> None:
        self._store = store
        self._provider_factory = provider_factory  # (session_id) -> AgentProvider
        # 在跑的 turn 任务。必须留引用：否则关服务时无处 cancel，
        # turn 会在库关掉之后醒来写库，抛 ProgrammingError 且消息丢失。
        self._turn_tasks: set[asyncio.Task] = set()
        self._jobs = jobs  # JobQueue（可选；agent submit_backtest 请求在 turn 末入队）
        self._runtimes: dict[str, SessionRuntime] = {}

    def create_session(self, title: str = "") -> str:
        return self._store.create_session(title)

    async def _ensure_runtime(self, session_id: str) -> SessionRuntime:
        rt = self._runtimes.get(session_id)
        if rt is not None and rt.provider.is_alive():
            return rt
        provider, workspace = self._provider_factory(session_id)
        await asyncio.to_thread(provider.start)

        # 会话续接：把运行时实际用的 session id 存下来。
        #
        # 首次启动时 id 是 Pi 自己生成的（我们没给），只有 start() 之后才知道；
        # 业务层必须把它落到库里，否则下次启动无从续接 —— agent 会「界面有历史、
        # 自己却失忆」。provider_factory 负责把存下的 id 填回 spec（见 app.py），
        # 这里负责把新 id 读出来写回库。
        runtime_sid = getattr(provider, "session_id", None)
        if runtime_sid:
            current = self._store.get_session(session_id) or {}
            if current.get("runtime_session_id") != runtime_sid:
                self._store.set_runtime_session_id(session_id, runtime_sid)

        rt = SessionRuntime(provider=provider, workspace=str(workspace))
        self._runtimes[session_id] = rt
        return rt

    def get_runtime(self, session_id: str) -> SessionRuntime | None:
        return self._runtimes.get(session_id)

    async def send_message(self, session_id: str, content: str) -> str:
        """落库 user message，触发 agent turn（后台流事件），返回 session id。

        turn 在后台任务里跑；事件实时进 buffer；assistant 消息在 turn 结束时落库。
        """
        self._store.add_message(session_id, "user", content)
        rt = await self._ensure_runtime(session_id)
        task = asyncio.create_task(self._run_turn(session_id, rt, content))
        self._turn_tasks.add(task)
        task.add_done_callback(self._turn_tasks.discard)
        return session_id

    async def _run_turn(
        self, session_id: str, rt: SessionRuntime, prompt: str
    ) -> None:
        assistant_text_parts: list[str] = []
        final_text = ""
        async for ev in rt.provider.astream(prompt):
            rt._emit(ev.kind, ev.payload)
            if ev.kind == EVENT_TEXT_DELTA:
                piece = ev.payload.get("text", "")
                if piece:
                    assistant_text_parts.append(piece)
            elif ev.kind == EVENT_TURN_END:
                final_text = ev.payload.get("final_text", "")
        text = final_text or "".join(assistant_text_parts)
        mid = self._store.add_message(session_id, "assistant", text)
        # turn 结束：扫描 workspace/runs/ 里新出现的 manifest.json，校验后落库并挂到本条消息。
        self._ingest_new_artifacts(rt, mid)
        # turn 结束：扫描 agent 写的 job 请求文件（workspace/jobs/），入队异步执行；
        # job 完成后把其产出 artifact 摄取并挂到本条 assistant 消息。
        if self._jobs is not None and rt.workspace:
            jids = self._jobs.ingest_job_requests(rt.workspace, session_id=session_id)
            for jid in jids:
                rt._emit("job/submitted", {"job_id": jid})
                # 成功/失败两条路都要发事件到**会话**流（不是 job 流）。
                # 用户盯的是对话，不是某个 job id —— 只发 job/submitted 的话，
                # artifact 到了界面上也不会刷新，用户干等着。
                self._jobs.on_complete(
                    jid,
                    lambda run_dir, m=mid, j=jid: self._ingest_job_artifacts(
                        rt, run_dir, m, jid=j
                    ),
                )
                self._jobs.on_failed(
                    jid,
                    lambda err, j=jid: rt._emit(
                        "job/failed", {"job_id": j, "error": err}
                    ),
                )
        rt._emit("message/committed", {"message_id": mid, "content": text})

    def _ingest_job_artifacts(
        self, rt: SessionRuntime, run_dir: str, message_id: str, *, jid: str = ""
    ) -> None:
        """job 成功后：把其 run_dir 的 manifest 摄取为 artifact 挂到消息，并发事件。

        `server_stamped=True`：这个 run_dir 是 **JobQueue 自己跑出来的**
        （`alpha.backtest.*` 的结果），不是 agent 交来的，所以它的
        `kind: "deterministic"` 声明是真的，应当保留 —— 这正是「盖章权归服务端」
        里服务端该用的那条路径（ADR-0012「已决 1」）。

        对比：`_ingest_new_artifacts` 扫的是 agent 自己写进 runs/ 的目录，
        那里必须保持默认 False，其 deterministic 声明会被降级。
        """
        from api.artifacts import ManifestError, ingest_run

        try:
            aids = ingest_run(self._store, run_dir, message_id, server_stamped=True)
        except ManifestError as e:
            rt._emit("artifact/rejected", {"run": str(run_dir), "error": str(e)})
            rt._emit("job/failed", {"job_id": jid, "error": str(e)})
            return
        for aid in aids:
            art = self._store.get_artifact(aid)
            rt._emit("artifact/attached", {
                "artifact_id": aid,
                "kind": art["kind"] if art else None,
                "title": art["title"] if art else "",
            })
        # job 完成的标志事件：带 artifact id，前端可据此刷新而不是全量重拉。
        rt._emit("job/completed", {"job_id": jid, "artifact_ids": aids})

    def _ingest_new_artifacts(self, rt: SessionRuntime, message_id: str) -> None:
        """扫描该会话 workspace 下未入库的 run 目录，校验 manifest 后落库并挂消息。

        非法 manifest 被业务层拒绝（ManifestError），跳过该 run，不影响其余。
        """
        if not rt.workspace:
            return
        runs_dir = Path(rt.workspace) / "runs"
        if not runs_dir.is_dir():
            return
        # 延迟导入，避免 api.artifacts <-> session_manager 循环。
        from api.artifacts import ManifestError, ingest_run

        for run_path in sorted(runs_dir.iterdir()):
            if not run_path.is_dir() or run_path.name in rt._ingested_runs:
                continue
            if not (run_path / "manifest.json").exists():
                continue
            rt._ingested_runs.add(run_path.name)
            try:
                aids = ingest_run(self._store, run_path, message_id)
            except ManifestError as e:
                rt._emit("artifact/rejected", {"run": run_path.name, "error": str(e)})
                continue
            for aid in aids:
                art = self._store.get_artifact(aid)
                rt._emit("artifact/attached", {
                    "artifact_id": aid,
                    "kind": art["kind"] if art else None,
                    "title": art["title"] if art else "",
                })

    def abort_turn(self, session_id: str, reason: str = "") -> bool:
        """中止该会话进行中的 turn。返回是否确实有 runtime 被中止。

        中止是 provider 契约的一部分（见 `AgentProvider.abort`），这里只做路由；
        是否「真的停下来了」由 provider 决定，`finish_reason == "aborted"`
        是它给前端的证据。
        """
        rt = self.get_runtime(session_id)
        if rt is None:
            return False
        rt.provider.abort(reason)
        return True

    def close_session(self, session_id: str) -> None:
        rt = self._runtimes.pop(session_id, None)
        if rt is not None:
            rt.provider.close()

    def close_all(self) -> None:
        """关闭所有会话运行时。

        注意：本方法**不能**自己 await（调用方是同步的 lifespan 清理）。
        在跑的 turn 由 `aclose_all` 负责取消并等待；这里只做同步部分。
        直接调本方法而库里还有 turn 在跑时，请改用 `await aclose_all()`。
        """
        for sid in list(self._runtimes):
            self.close_session(sid)

    async def aclose_all(self) -> None:
        """关闭所有运行时，并**等在跑的 turn 收尾**。

        为什么必须等：turn 收尾要写库（assistant 消息 + artifact）。
        不等的话，调用方关掉 sqlite 之后 turn 才醒来，抛
        `ProgrammingError: Cannot operate on a closed database`，
        用户看到的是「消息发出去了但没存下来」。

        先 cancel 再 await：cancel 让它别再继续跑（provider 会收到 close），
        await 确保它真的停下来了，之后关库才是安全的。
        """
        tasks = [t for t in self._turn_tasks if not t.done()]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.close_all()
