"""vendor 能力的 REST 暴露（M3-V5）。给 agent 用，页面继续走 curated 端点。

## 为什么 agent 需要这一层

页面用的端点是我们**精选过**的（每个都有明确的字段契约与错误语义）。
但 agent 需要的是「我能不能自己去找数据」—— 它应该能调到 vendor 的
全部 104 个能力，而不是等我们逐个封装。

这就有个张力：**能力全开 vs 契约稳定**。这里的取舍是：

  - `/v1/capabilities` —— 只读清单，agent 据此知道自己能调什么
  - `/v1/invoke`      —— 通用调用入口，`{name, args, kwargs}` 直通 vendor

不给每个 vendor 函数单独开一个 REST 端点（那就是「第二套 REST」，
AGENTS 反模式明确禁止），只开一个通用的。

## 不做的事

- 不缓存（取数有 TTL 需求时由调用方决定；这里缓存会把「数据时点」搞乱）
- 不做参数校验（vendor 自己的签名就是契约，重复校验只会漂移）
- 不鉴权（这是本地单用户工作台；与现有端点一致）
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from alpha.vendor_bridge import VendorBridge, VendorError


class InvokeIn(BaseModel):
    name: str
    args: list[Any] = []
    kwargs: dict[str, Any] = {}


def build_vendor_router(bridge: VendorBridge | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    b = bridge or VendorBridge()

    @router.get("/capabilities")
    def capabilities() -> dict:
        """vendor 能做什么。agent 进来先看这个。"""
        if not b.available():
            # 503 而不是空清单：空清单会被理解成「什么都不能做」，
            # 而实际是「这一层还没装」。两者对 agent 的决策完全不同。
            raise HTTPException(
                503,
                "data-service 未就绪（缺 venv 或 worker.py）。见 data-service/README.md。",
            )
        try:
            caps = b.capabilities()
        except VendorError as e:
            raise HTTPException(502, f"列举 vendor 能力失败：{e}") from e
        return {"count": len(caps), "capabilities": caps}

    @router.post("/invoke")
    def invoke(body: InvokeIn) -> dict:
        """调一个 vendor 能力。参数直通，不做二次校验。"""
        if not b.available():
            raise HTTPException(503, "data-service 未就绪")
        try:
            result = b.invoke(body.name, args=body.args, kwargs=body.kwargs)
        except VendorError as e:
            msg = str(e)
            # 缺依赖与「函数不存在」要能区分：前者是环境问题（可以装），
            # 后者是调用错了（agent 该换个函数）。都用 502 的话没法分辨。
            if "ModuleNotFoundError" in msg or "No module named" in msg:
                raise HTTPException(424, f"vendor 缺少依赖：{msg}") from e
            # 「调用方用错了」（400）与「上游/环境有问题」（502/424）必须分开：
            # 前者 agent 换个参数就能成功，后者重试也没用。
            caller_fault = (
                "没有可调用能力" in msg or "私有函数" in msg or "缺少 name" in msg
                or "参数不匹配" in msg
            )
            if caller_fault:
                raise HTTPException(400, msg) from e
            raise HTTPException(502, f"vendor 调用失败：{msg}") from e
        return {"name": body.name, "result": result}

    return router
