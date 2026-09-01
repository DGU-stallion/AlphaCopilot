"""FastAPI 应用 —— 会话 REST + SSE（T28）。

端点：
  POST /sessions                    -> {session_id}
  GET  /sessions                    -> [session...]
  GET  /sessions/{id}/messages      -> [message...]（前端从我们的 DB 重建对话，不读 dsh JSONL）
  POST /sessions/{id}/messages      -> 落库 user + 触发 agent turn（后台流）
  GET  /sessions/{id}/stream        -> SSE：assistant/chunk 等事件逐条推；支持 Last-Event-ID 重连
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.harness import HarnessSettings
from api.jobs import JobQueue
from api.session_manager import SessionManager
from api.store import Store

_REPO_ROOT = Path(__file__).resolve().parents[2]


class MessageIn(BaseModel):
    content: str


def _default_settings_factory(workspace_root: Path, base_url=None, api_key=None):
    def factory(session_id: str) -> HarnessSettings:
        ws = workspace_root / session_id / "ws"
        sr = workspace_root / session_id / "sessions"
        ws.mkdir(parents=True, exist_ok=True)
        sr.mkdir(parents=True, exist_ok=True)
        return HarnessSettings(
            workspace=str(ws),
            session_root=str(sr),
            base_url=base_url,
            api_key=api_key,
        )

    return factory


def create_app(
    db_path: str = ":memory:",
    workspace_root: Path | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> FastAPI:
    store = Store(db_path)
    ws_root = workspace_root or Path(tempfile.mkdtemp(prefix="alphacopilot-ws-"))
    jobs = JobQueue(store, ws_root)
    manager = SessionManager(
        store, _default_settings_factory(ws_root, base_url=base_url, api_key=api_key),
        jobs=jobs,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        manager.close_all()
        store.close()

    app = FastAPI(title="AlphaCopilot API", version="0.2.0", lifespan=lifespan)
    app.state.store = store
    app.state.manager = manager
    app.state.jobs = jobs

    # 所有会话接口挂在 /api 下（前端 vite 代理转发 /api/* 到本服务）。
    router = APIRouter(prefix="/api")

    @router.post("/sessions")
    def create_session(title: str = "") -> dict:
        sid = manager.create_session(title)
        return {"session_id": sid}

    @router.get("/sessions")
    def list_sessions() -> list:
        return store.list_sessions()

    @router.get("/sessions/{sid}/messages")
    def list_messages(sid: str) -> list:
        if store.get_session(sid) is None:
            raise HTTPException(404, "session not found")
        msgs = store.list_messages(sid)
        # 附上每条消息挂载的 artifact（前端 block 渲染器据此渲染图/表/markdown）。
        for m in msgs:
            m["artifacts"] = store.list_artifacts_for_message(m["id"])
        return msgs

    @router.get("/artifacts/{aid}")
    def get_artifact(aid: str) -> dict:
        art = store.get_artifact(aid)
        if art is None:
            raise HTTPException(404, "artifact not found")
        return art

    class BacktestIn(BaseModel):
        closes: list[float]
        fast: int = 20
        slow: int = 60
        symbol: str = ""
        dates: list[str] | None = None

    @router.post("/jobs/backtest")
    async def submit_backtest_job(body: BacktestIn) -> dict:
        jid = jobs.submit_backtest(body.model_dump())
        return {"job_id": jid, "status": "queued"}

    @router.get("/jobs/{jid}")
    def get_job(jid: str) -> dict:
        job = store.get_job(jid)
        if job is None:
            raise HTTPException(404, "job not found")
        return job

    @router.get("/jobs/{jid}/stream")
    async def job_stream(
        jid: str,
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        start_id = int(last_event_id) if last_event_id and last_event_id.isdigit() else None

        async def gen():
            q = jobs.subscribe(jid, last_id=start_id)
            try:
                while True:
                    try:
                        ev = await asyncio.wait_for(q.get(), timeout=15.0)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    payload = json.dumps(ev.data, ensure_ascii=False)
                    yield f"id: {ev.id}\nevent: {ev.type}\ndata: {payload}\n\n"
                    if ev.type in ("succeeded", "failed"):
                        break
            finally:
                jobs.unsubscribe(jid, q)

        return StreamingResponse(gen(), media_type="text/event-stream")

    @router.post("/sessions/{sid}/messages")
    async def post_message(sid: str, body: MessageIn) -> dict:
        if store.get_session(sid) is None:
            raise HTTPException(404, "session not found")
        await manager.send_message(sid, body.content)
        return {"ok": True}

    @router.get("/sessions/{sid}/stream")
    async def stream(
        sid: str,
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        if store.get_session(sid) is None:
            raise HTTPException(404, "session not found")
        rt = manager.get_runtime(sid)
        start_id = int(last_event_id) if last_event_id and last_event_id.isdigit() else None

        async def gen():
            if rt is None:
                # 尚无运行态（还没发消息）：保持连接，发一个心跳注释。
                yield ": waiting\n\n"
                return
            q = rt.subscribe(last_event_id=start_id)
            try:
                while True:
                    # 不用 request.is_disconnected()：在 ASGI 传输下它会消费 receive
                    # 通道并可能立即报「已断开」，导致流一条都发不出。客户端断开时
                    # Starlette 会 cancel 本生成器（GeneratorExit），由 finally 清理。
                    try:
                        be = await asyncio.wait_for(q.get(), timeout=15.0)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    payload = json.dumps(be.data, ensure_ascii=False)
                    yield f"id: {be.id}\nevent: {be.type}\ndata: {payload}\n\n"
            finally:
                rt.unsubscribe(q)

        return StreamingResponse(gen(), media_type="text/event-stream")

    app.include_router(router)
    return app
