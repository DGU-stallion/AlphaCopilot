"""M3-1 Run registry REST API —— 运行留档与 View 的对外只读/管理面。

Run registry 的数据库与约定见 api/store.py 的 RunRepo / ViewRepo（契约测试
tests/test_run_registry.py）。本模块只做 HTTP 编排：
  - /runs*    读多写少（Run 只能由回测 job 产生，agent 不能开洞伪造留档）
  - /views*   View 是「保存的看什么」，允许用户建 / 钉 / 删（M3-3）

路由风格与 build_pages_router / build_business_router 一致：prefix="/api"，
store 由调用方传入（create_app 持有），**不建模块级单例**。
"""

from __future__ import annotations

from collections.abc import Callable
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


class NoteIn(BaseModel):
    title: str
    text: str = ""


class RunNoteIn(BaseModel):
    """Run 的一行备注（B3）。上限 500，与页面备注口径一致。"""

    note: str

    @property
    def too_long(self) -> bool:
        return len(self.note) > 500


def build_runs_router(
    store: Store,
    submit_backtest: Callable[[dict[str, Any]], str] | None = None,
) -> APIRouter:
    """Run / View 的 REST 接口。

    submit_backtest 由调用方注入（app.py 传 jobs.submit_backtest 的包装）：
    runs 模块不该 import jobs（jobs 已经够重，且会形成双向依赖）。
    没注入时 /runs/{id}/rerun 返回 501 —— 明确「没这个能力」，
    而不是返回 200 然后什么也没发生。
    """
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

    @router.delete("/runs/{rid}")
    def delete_run(rid: str) -> dict:
        """软删一条 Run（B3，硬规则 14：破坏性操作必须可撤销）。

        Run 是「这次算了什么、用哪版代码、哪份数据」的证据链，硬删不可恢复；
        撤销入口在前端提示条里，后端只保证数据还在。没有「内置 Run」的保护：
        Run 只能由确定性计算产生，不存在手写产物。
        """
        r = store.runs.get(rid)   # get 也能取到已软删的（重复删不报 404）
        if r is None:
            raise HTTPException(404, f"run not found: {rid}")
        soft = store.runs.soft_delete(rid)
        return {"ok": True, "id": rid, "soft": soft}

    @router.post("/runs/{rid}/restore")
    def restore_run(rid: str) -> dict:
        """撤销软删。get() 看得见软删行，所以 restore 找得回来。"""
        r = store.runs.get(rid)
        if r is None:
            raise HTTPException(404, f"run not found: {rid}")
        restored = store.runs.restore(rid)
        if not restored:
            raise HTTPException(404, f"run not found: {rid}")
        return {"ok": True, "id": rid}

    @router.post("/runs/{rid}/note")
    def set_run_note(rid: str, body: RunNoteIn) -> dict:
        """写一行备注（「这一版想验证什么」）。上限 500，超了 400。"""
        if body.too_long:
            raise HTTPException(400, f"note 太长（{len(body.note)} > 500 字）")
        if store.runs.get(rid) is None:
            raise HTTPException(404, f"run not found: {rid}")
        if not store.runs.set_note(rid, body.note):
            raise HTTPException(404, f"run not found: {rid}")
        return {"ok": True}

    @router.post("/runs/{rid}/rerun")
    def rerun(rid: str) -> dict:
        """用同一个 Run 的输入快照重跑一次（M3-4「可重跑」）。

        为什么值得单独做：数据会变。同一个策略隔一周重跑，
        结果不同才是正常的 —— 前提是你能证明「除了数据，别的都一样」。
        输入快照（inputs）就是那个证明。
        """
        r = store.runs.get(rid)
        if r is None:
            raise HTTPException(404, f"run not found: {rid}")
        if submit_backtest is None:
            raise HTTPException(501, "本进程未启用 job 队列，无法重跑")
        inputs = r.get("inputs") or {}
        if not inputs:
            raise HTTPException(409, "这条 Run 没有输入快照（可能是早期版本产生），无法重跑")
        if not inputs.get("closes"):
            raise HTTPException(409, "输入快照里没有 closes，无法重跑")
        jid = submit_backtest(inputs)
        return {"job_id": jid, "rerun_of": rid}

    # ---------- 研究线（M5-3）：Note → Run → View → 复盘 ----------

    @router.get("/notes")
    def list_notes() -> list:
        """研究笔记列表（复用 doc 表）。"""
        return store.docs.list_docs()

    @router.post("/notes")
    def create_note(body: NoteIn) -> dict:
        did = store.docs.add_doc(title=body.title, source_path="", text=body.text)
        return {"id": did}

    @router.get("/notes/{did}/thread")
    def note_thread(did: str) -> dict:
        """一条研究线的完整视图：笔记 + 它的 Run + 它的 View。

        这一条是「半年后能回答我为什么这么买」的全部数据来源：
        当时写了什么（note）、用什么验证过（runs）、在看什么（views）。
        """
        thread = store.docs.thread(did)
        if thread["note"] is None:
            raise HTTPException(404, f"note not found: {did}")
        return thread

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
