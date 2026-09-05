"""业务页 CRUD REST（S3）——股票池 / 交易日志 / 我的研报（文档库）。

状态型业务页的真源是 SQLite（AGENTS 边界：业务层唯一持有产品数据库）。
本 router 是薄 CRUD：校验 → 调 store repo → 回 JSON。零分析逻辑。

  股票池 stock_pool：
    GET    /api/stock-pool           列出
    POST   /api/stock-pool           加入/更新（code 唯一 upsert）
    DELETE /api/stock-pool/{code}    移除
  交易日志 journal：
    GET    /api/journal              列出
    POST   /api/journal              新增一条成交
    POST   /api/journal/import       批量导入（vibe-astock JSON / 标准 CSV 行数组）
    DELETE /api/journal/{jid}        删除
  我的研报 reports（复用 doc 表）：
    GET    /api/reports              列出
    POST   /api/reports              新增（标题 + 文本/来源）
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.store import Store


class StockPoolIn(BaseModel):
    code: str
    name: str = ""
    note: str = ""
    tags: str = ""


class JournalIn(BaseModel):
    code: str = ""
    name: str = ""
    side: str
    price: float
    shares: int
    fee: float = 0.0
    traded_at: str = ""
    note: str = ""


class JournalImportIn(BaseModel):
    rows: list[dict[str, Any]]


class ReportIn(BaseModel):
    title: str
    text: str = ""
    source_path: str = ""


def build_business_router(store: Store) -> APIRouter:
    router = APIRouter(prefix="/api")

    # ---------- 股票池 ----------
    @router.get("/stock-pool")
    def list_pool() -> list:
        return store.stock_pool.list()

    @router.post("/stock-pool")
    def add_pool(body: StockPoolIn) -> dict:
        code = body.code.strip()
        if not (len(code) == 6 and code.isdigit()):
            raise HTTPException(400, f"非法标的代码 {code!r}（须 6 位数字）")
        pid = store.stock_pool.add(code, body.name, body.note, body.tags)
        return {"id": pid, "code": code}

    @router.delete("/stock-pool/{code}")
    def remove_pool(code: str) -> dict:
        if not store.stock_pool.remove(code):
            raise HTTPException(404, "不在股票池中")
        return {"ok": True}

    # ---------- 交易日志 ----------
    @router.get("/journal")
    def list_journal() -> list:
        return store.journal.list()

    @router.post("/journal")
    def add_journal(body: JournalIn) -> dict:
        try:
            jid = store.journal.add(
                code=body.code, name=body.name, side=body.side, price=body.price,
                shares=body.shares, fee=body.fee, traded_at=body.traded_at, note=body.note,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"id": jid}

    @router.post("/journal/import")
    def import_journal(body: JournalImportIn) -> dict:
        """批量导入。每行支持 vibe-astock/标准字段：code/name/side/price/shares/fee/traded_at/note。

        导入前逐行校验 side/price/shares；任一行非法则整批拒绝（预览校验语义），不部分写入。
        """
        parsed: list[dict[str, Any]] = []
        for i, row in enumerate(body.rows):
            side = str(row.get("side", "")).lower()
            if side not in ("buy", "sell"):
                raise HTTPException(400, f"第 {i + 1} 行 side 非法: {row.get('side')!r}")
            try:
                price = float(row.get("price"))
                shares = int(row.get("shares"))
            except (TypeError, ValueError) as e:
                raise HTTPException(400, f"第 {i + 1} 行 price/shares 非法") from e
            parsed.append({
                "code": str(row.get("code", "")), "name": str(row.get("name", "")),
                "side": side, "price": price, "shares": shares,
                "fee": float(row.get("fee", 0) or 0),
                "traded_at": str(row.get("traded_at", "")), "note": str(row.get("note", "")),
            })
        for p in parsed:
            store.journal.add(**p)
        return {"imported": len(parsed)}

    @router.delete("/journal/{jid}")
    def remove_journal(jid: str) -> dict:
        if not store.journal.remove(jid):
            raise HTTPException(404, "日志不存在")
        return {"ok": True}

    # ---------- 我的研报（复用 doc 表）----------
    @router.get("/reports")
    def list_reports() -> list:
        return store.docs.list_docs()

    @router.post("/reports")
    def add_report(body: ReportIn) -> dict:
        if not body.title.strip():
            raise HTTPException(400, "标题不能为空")
        did = store.docs.add_doc(body.title, body.source_path or "manual", body.text)
        return {"id": did}

    return router
