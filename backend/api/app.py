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

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.harness import HarnessSettings
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
    manager = SessionManager(
        store, _default_settings_factory(ws_root, base_url=base_url, api_key=api_key)
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        manager.close_all()
        store.close()

    app = FastAPI(title="AlphaCopilot API", version="0.2.0", lifespan=lifespan)
    app.state.store = store
    app.state.manager = manager

    @app.post("/sessions")
    def create_session(title: str = "") -> dict:
        sid = manager.create_session(title)
        return {"session_id": sid}

    @app.get("/sessions")
    def list_sessions() -> list:
        return store.list_sessions()

    @app.get("/sessions/{sid}/messages")
    def list_messages(sid: str) -> list:
        if store.get_session(sid) is None:
            raise HTTPException(404, "session not found")
        return store.list_messages(sid)

    @app.post("/sessions/{sid}/messages")
    async def post_message(sid: str, body: MessageIn) -> dict:
        if store.get_session(sid) is None:
            raise HTTPException(404, "session not found")
        await manager.send_message(sid, body.content)
        return {"ok": True}

    @app.get("/sessions/{sid}/stream")
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

    return app
