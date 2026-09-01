"""会话编排 —— 把 HarnessSession 的事件流桥到 SSE，并把消息落库（T28）。

职责：
- 每个产品会话映射一个存活的 HarnessSession（一会话一子进程，见 T27）。
- 用户发消息 → 落库 user message → 触发 agent turn → 流事件写入 per-session ring
  buffer（带单调递增 event_id）→ 订阅者（SSE）实时收到 → turn 结束落库 assistant message。
- SSE 断线重连：客户端带 Last-Event-ID，从 buffer 里补发之后的事件。

零 dsh 细节泄漏：只依赖 agent.harness 的 HarnessSession / StreamEvent 抽象。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.harness import HarnessSession, HarnessSettings, StreamEvent
from api.store import Store


@dataclass
class BufferedEvent:
    id: int
    type: str
    data: dict[str, Any]


@dataclass
class SessionRuntime:
    """一个会话的运行态：harness 子进程 + 事件 buffer + 订阅者。"""

    harness: HarnessSession
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
    """管理所有会话运行态。业务层唯一持有 harness 的地方。"""

    def __init__(self, store: Store, settings_factory, jobs=None) -> None:
        self._store = store
        self._settings_factory = settings_factory  # (session_id) -> HarnessSettings
        self._jobs = jobs  # JobQueue（可选；agent submit_backtest 请求在 turn 末入队）
        self._runtimes: dict[str, SessionRuntime] = {}

    def create_session(self, title: str = "") -> str:
        return self._store.create_session(title)

    async def _ensure_runtime(self, session_id: str) -> SessionRuntime:
        rt = self._runtimes.get(session_id)
        if rt is not None and rt.harness.is_process_alive():
            return rt
        settings: HarnessSettings = self._settings_factory(session_id)
        harness = HarnessSession(settings)
        await asyncio.to_thread(harness.start)
        rt = SessionRuntime(harness=harness, workspace=settings.workspace)
        self._runtimes[session_id] = rt
        return rt

    def get_runtime(self, session_id: str) -> SessionRuntime | None:
        return self._runtimes.get(session_id)

    async def send_message(self, session_id: str, content: str) -> str:
        """落库 user message，触发 agent turn（后台流事件），返回 user message id。

        turn 在后台任务里跑；事件实时进 buffer；assistant 消息在 turn 结束时落库。
        """
        self._store.add_message(session_id, "user", content)
        rt = await self._ensure_runtime(session_id)
        asyncio.create_task(self._run_turn(session_id, rt, content))
        return session_id

    async def _run_turn(
        self, session_id: str, rt: SessionRuntime, prompt: str
    ) -> None:
        assistant_text_parts: list[str] = []
        final_text = ""
        async for ev in rt.harness.astream(prompt):
            if ev.type == "turn/final":
                final_text = ev.payload.get("final_response", "")
                rt._emit("turn/final", ev.payload)
            elif ev.type == "turn/error":
                rt._emit("turn/error", ev.payload)
            else:
                # assistant/chunk 等：透传给 SSE。
                rt._emit(ev.type, ev.payload)
                if ev.type == "assistant/chunk":
                    piece = _extract_chunk_text(ev.payload)
                    if piece:
                        assistant_text_parts.append(piece)
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
                self._jobs.on_complete(
                    jid, lambda run_dir, m=mid: self._ingest_job_artifacts(rt, run_dir, m)
                )
        rt._emit("message/committed", {"message_id": mid, "content": text})

    def _ingest_job_artifacts(self, rt: SessionRuntime, run_dir: str, message_id: str) -> None:
        """job 成功后：把其 run_dir 的 manifest 摄取为 artifact 挂到消息，并发事件。"""
        from api.artifacts import ManifestError, ingest_run

        try:
            aids = ingest_run(self._store, run_dir, message_id)
        except ManifestError as e:
            rt._emit("artifact/rejected", {"run": str(run_dir), "error": str(e)})
            return
        for aid in aids:
            art = self._store.get_artifact(aid)
            rt._emit("artifact/attached", {
                "artifact_id": aid,
                "kind": art["kind"] if art else None,
                "title": art["title"] if art else "",
            })

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

    def close_session(self, session_id: str) -> None:
        rt = self._runtimes.pop(session_id, None)
        if rt is not None:
            rt.harness.close()

    def close_all(self) -> None:
        for sid in list(self._runtimes):
            self.close_session(sid)


def _extract_chunk_text(payload: dict[str, Any]) -> str:
    """从 dsh assistant/chunk event 取增量文本。

    实测 dsh 形状：payload['data']['chunk'] = {'type':'text-delta','text':...}。
    只在 text-delta 时取 text；block-start/end/finish 无文本。
    """
    data = payload.get("data")
    if isinstance(data, dict):
        chunk = data.get("chunk")
        if isinstance(chunk, dict) and chunk.get("type") == "text-delta":
            t = chunk.get("text")
            if isinstance(t, str):
                return t
    return ""
