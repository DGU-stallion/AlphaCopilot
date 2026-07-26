"""
AlphaCopilot — 统一后端入口
将 research（投研数据）和 quant（量化 agent）两个模块挂载到同一 FastAPI 实例。
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="AlphaCopilot API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5899"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 投研模块 ---
# TODO: 从 research/ 迁移并挂载各 router
# from research.astock import router as astock_router
# app.include_router(astock_router, prefix="/api/research")

# --- 量化模块 ---
# TODO: 从 quant/ 挂载 agent、backtest、factors 路由
# from quant.api import router as quant_router
# app.include_router(quant_router, prefix="/api/quant")


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}
