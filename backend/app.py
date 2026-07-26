"""
AlphaCopilot — 统一后端入口

将 research（投研数据）和 quant（量化 agent）两个模块挂载到同一 FastAPI 实例。

启动：
    cd backend && python -m uvicorn app:app --host 127.0.0.1 --port 8900
"""

from __future__ import annotations

import sys
from pathlib import Path

# 让 research/ 下的模块能用相对 import 风格（如 import astock）
sys.path.insert(0, str(Path(__file__).resolve().parent / "research"))

# 直接复用 research/app.py 创建的 FastAPI 实例，它已经注册了所有投研路由。
# 后续 quant 模块的路由会以 APIRouter 形式 include 进来。
from research.app import app  # noqa: E402

# --- 量化模块（TODO：逐步接入）---
# quant/api_server.py 内部有复杂的 import 结构，需要做 path 适配后再挂载。
# 第一步：先跑通 research 部分，确认前后端联通。
# from quant.api import router as quant_router
# app.include_router(quant_router, prefix="/api/quant")

# 覆盖 title 和 version
app.title = "AlphaCopilot API"
app.version = "0.1.0"
