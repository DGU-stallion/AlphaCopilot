"""Vibe-Research 后端 —— A股数据层 HTTP 接口（FastAPI）。

独立运行模式：uvicorn app:app --host 127.0.0.1 --port 8900
路由逻辑已提取到 router.py，本文件作为 standalone fallback 保留。
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import portfolio as pf
from router import create_research_router

app = FastAPI(title="Vibe-Research API", version="0.1.3")

# 每半小时后台刷新持仓数据
pf.start_scheduler(1800)

# CORS：默认放开（本地自托管友好）；公网部署时用 VR_ALLOW_ORIGINS 收紧成白名单。
_ORIGINS = [o.strip() for o in os.environ.get("VR_ALLOW_ORIGINS", "*").split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ORIGINS,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# 可选鉴权：设了 VR_API_KEY 就要求所有 /api/* 带 `Authorization: Bearer <key>`
_API_KEY = os.environ.get("VR_API_KEY", "").strip()


@app.middleware("http")
async def _require_api_key(request: Request, call_next):
    if (
        _API_KEY
        and request.method != "OPTIONS"
        and request.url.path.startswith("/api/")
        and request.url.path != "/api/health"
    ):
        if request.headers.get("authorization", "") != f"Bearer {_API_KEY}":
            return JSONResponse({"detail": "未授权：缺少或错误的 API Key（VR_API_KEY）"}, status_code=401)
    return await call_next(request)


# 挂载 research 路由，前缀 /api（兼容原有前端直连模式）
app.include_router(create_research_router(), prefix="/api")
