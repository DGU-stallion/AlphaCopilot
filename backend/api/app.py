"""FastAPI 应用 —— 会话 REST + SSE（T28）。

端点：
  POST /sessions                    -> {session_id}
  GET  /sessions                    -> [session...]
  GET  /sessions/{id}/messages      -> [message...]（前端从我们的 DB 重建对话，不读 dsh JSONL）
  POST /sessions/{id}/messages      -> 落库 user + 触发 agent turn（后台流）
  GET  /sessions/{id}/stream        -> SSE：text_delta 等中立事件逐条推；支持 Last-Event-ID 重连
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.persona import system_prompt as _compliance_prompt
from agent.provider import ProviderSpec
from agent.providers.dsh import DshProvider
from api.builtin_pages import register_builtin_pages
from api.jobs import JobQueue
from api.pages import build_pages_router
from api.session_manager import SessionManager
from api.store import Store

_REPO_ROOT = Path(__file__).resolve().parents[2]


class MessageIn(BaseModel):
    content: str


def _default_provider_factory(workspace_root: Path, base_url=None, api_key=None, model=None):
    def factory(session_id: str):
        ws = workspace_root / session_id / "ws"
        ws.mkdir(parents=True, exist_ok=True)
        spec = ProviderSpec(
            workspace=ws,
            system_prompt=_compliance_prompt(),
            model=model,
            base_url=base_url,
            api_key=api_key,
        )
        return DshProvider(spec), ws

    return factory


def create_app(
    db_path: str = ":memory:",
    workspace_root: Path | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> FastAPI:
    store = Store(db_path)
    register_builtin_pages(store)
    ws_root = workspace_root or Path(tempfile.mkdtemp(prefix="alphacopilot-ws-"))
    jobs = JobQueue(store, ws_root)
    manager = SessionManager(
        store,
        _default_provider_factory(ws_root, base_url=base_url, api_key=api_key, model=model),
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
                    except TimeoutError:
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
        start_id = int(last_event_id) if last_event_id and last_event_id.isdigit() else None

        async def gen():
            # runtime 可能在首条消息 POST 时才创建。若订阅早于 POST（前端先连流再发消息），
            # 不能直接关闭流——那样会丢掉随后 turn 的事件。改为轮询等待 runtime 出现，
            # 期间发心跳保活；出现后订阅其 buffer（全量补发保证不漏早期事件）。
            rt = manager.get_runtime(sid)
            waited = 0.0
            while rt is None and waited < 300.0:
                yield ": waiting\n\n"
                await asyncio.sleep(0.2)
                waited += 0.2
                rt = manager.get_runtime(sid)
            if rt is None:
                return
            q = rt.subscribe(last_event_id=start_id)
            try:
                while True:
                    # 不用 request.is_disconnected()：在 ASGI 传输下它会消费 receive
                    # 通道并可能立即报「已断开」，导致流一条都发不出。客户端断开时
                    # Starlette 会 cancel 本生成器（GeneratorExit），由 finally 清理。
                    try:
                        be = await asyncio.wait_for(q.get(), timeout=15.0)
                    except TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    payload = json.dumps(be.data, ensure_ascii=False)
                    yield f"id: {be.id}\nevent: {be.type}\ndata: {payload}\n\n"
            finally:
                rt.unsubscribe(q)

        return StreamingResponse(gen(), media_type="text/event-stream")

    app.include_router(router)
    app.include_router(build_pages_router(store))
    return app
