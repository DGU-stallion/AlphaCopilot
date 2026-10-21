"""M3-1 Run registry REST API —— 运行留档与 View 的对外只读/管理面。

Run registry 的数据库与约定见 api/store.py 的 RunRepo / ViewRepo（契约测试
tests/test_run_registry.py）。本模块只做 HTTP 编排：
  - /runs*    读多写少（Run 只能由回测 job 产生，agent 不能开洞伪造留档）
  - /views*   View 是「保存的看什么」，允许用户建 / 钉 / 删（M3-3）

路由风格与 build_pages_router / build_business_router 一致：prefix="/api"，
store 由调用方传入（create_app 持有），**不建模块级单例**。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.store import Store


class CreateViewIn(BaseModel):
    name: str
    kind: str
    params: dict[str, Any] | None = None
    last_run_id: str | None = None


class PinViewIn(BaseModel):
    pinned: bool


def build_runs_router(store: Store) -> APIRouter:
    router = APIRouter(prefix="/api")

    # ---------- Run registry ----------
    # 注意：/runs/diff 必须注册在 /runs/{rid} 之前，否则 "diff" 会被路径参数吃掉。

    @router.get("/runs/diff")
    def diff_runs(a: str, b: str) -> dict:
        try:
            return store.runs.diff(a, b)
        except KeyError as e:
            raise HTTPException(404, f"run not found: {e.args[0]}") from e

    @router.get("/runs")
    def list_runs(kind: str | None = None, data_as_of: str | None = None,
                  limit: int = 50) -> list:
        return store.runs.list_recent(kind=kind, data_as_of=data_as_of, limit=limit)

    @router.get("/runs/{rid}")
    def get_run(rid: str) -> dict:
        r = store.runs.get(rid)
        if r is None:
            raise HTTPException(404, f"run not found: {rid}")
        return r

    # ---------- View ----------

    @router.get("/views")
    def list_views() -> list:
        return store.views.list_all()

    @router.get("/views/pinned")
    def list_pinned_views() -> list:
        return store.views.list_pinned()

    @router.post("/views")
    def create_view(body: CreateViewIn) -> dict:
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "view name 不能为空")
        vid = store.views.create(
            name=name, kind=body.kind, params=body.params, last_run_id=body.last_run_id
        )
        return {"id": vid}

    @router.post("/views/{vid}/pin")
    def pin_view(vid: str, body: PinViewIn) -> dict:
        if store.views.get(vid) is None:
            raise HTTPException(404, f"view not found: {vid}")
        # 用 pydantic 解析过的 bool（曾因 truthy 判断把 pinned:false 存成 1，
        # true/false 会变成同一值 —— 显式类型就是这个教训的护栏）。
        store.views.set_pinned(vid, body.pinned)
        return {"id": vid, "pinned": body.pinned}

    @router.delete("/views/{vid}")
    def delete_view(vid: str) -> dict:
        if store.views.get(vid) is None:
            raise HTTPException(404, f"view not found: {vid}")
        store.views.delete(vid)
        return {"ok": True}

    return router
