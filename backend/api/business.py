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


class PortfolioIn(BaseModel):
    name: str
    benchmark: str = "000300"
    created_on: str = ""


class RebalanceIn(BaseModel):
    effective_on: str
    weights: dict[str, float]


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

    @router.delete("/reports/{did}")
    def remove_report(did: str) -> dict:
        if not store.docs.delete_doc(did):
            raise HTTPException(404, "研报不存在")
        return {"ok": True}

    # ---------- 模拟组合（雪球式调仓事件）----------
    @router.get("/portfolios")
    def list_portfolios() -> list:
        out = []
        for pf in store.portfolio.list():
            pf["rebalances"] = store.portfolio.list_rebalances(pf["id"])
            out.append(pf)
        return out

    @router.post("/portfolios")
    def create_portfolio(body: PortfolioIn) -> dict:
        if not body.name.strip():
            raise HTTPException(400, "组合名不能为空")
        pid = store.portfolio.create(body.name, body.benchmark, body.created_on)
        return {"id": pid}

    @router.delete("/portfolios/{pid}")
    def delete_portfolio(pid: str) -> dict:
        if not store.portfolio.delete(pid):
            raise HTTPException(404, "组合不存在")
        return {"ok": True}

    @router.post("/portfolios/{pid}/rebalance")
    def add_rebalance(pid: str, body: RebalanceIn) -> dict:
        if store.portfolio.get(pid) is None:
            raise HTTPException(404, "组合不存在")
        for code, w in body.weights.items():
            if not (len(code) == 6 and code.isdigit()):
                raise HTTPException(400, f"非法标的 {code!r}")
            if w < 0 or w > 1:
                raise HTTPException(400, f"{code} 权重 {w} 越界 [0,1]")
        total = sum(body.weights.values())
        if total > 1.0 + 1e-9:
            raise HTTPException(400, f"权重和 {total:.3f} > 1（超出部分应为现金）")
        rid = store.portfolio.add_rebalance(pid, body.effective_on, body.weights)
        return {"id": rid}

    @router.get("/portfolios/{pid}/nav")
    def portfolio_nav(pid: str) -> dict:
        """组合净值曲线 vs 基准（ECharts line option）。数据源不可用时优雅降级。"""
        from alpha import chart, data, portfolio as pf_calc

        pf = store.portfolio.get(pid)
        if pf is None:
            raise HTTPException(404, "组合不存在")
        events = store.portfolio.list_rebalances(pid)
        if not events:
            return {"option": chart.line([], {"组合净值": []}, title="尚无调仓事件")}
        codes = sorted({c for e in events for c in e["weights"]})
        price_map: dict[str, dict[str, float]] = {}
        for code in codes:
            try:
                rows = data.closes_with_dates(code, count=250)
            except Exception:  # noqa: BLE001
                rows = []
            price_map[code] = {d: c for d, c in rows}
        dates, nav = pf_calc.compute_nav(events, price_map)
        if not dates:
            return {"option": chart.line([], {"组合净值": []},
                                         title="行情数据源暂不可用，净值待计算")}
        series = {"组合净值": nav}
        try:
            brows = data.closes_with_dates(pf["benchmark"], count=250)
            bench = pf_calc.compute_benchmark_nav(dates, {d: c for d, c in brows})
            if bench:
                series[f"基准({pf['benchmark']})"] = bench
        except Exception:  # noqa: BLE001
            pass
        return {"option": chart.line(dates, series, title=f"{pf['name']} 净值")}

    return router
