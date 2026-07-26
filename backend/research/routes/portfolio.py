"""Portfolio route sub-module — /portfolio endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from research.caches import ResearchCaches
from research.models import HoldingIn, CloseIn

import research.portfolio as pf


def register_portfolio_routes(router: APIRouter, *, caches: ResearchCaches) -> None:
    """Attach portfolio endpoints to the given router."""

    @router.get("/portfolio")
    def portfolio_get():
        try:
            return {"data": pf.get_portfolio()}
        except Exception as e:
            raise HTTPException(502, f"持仓读取异常：{e}") from e

    @router.post("/portfolio/holding")
    def portfolio_add(h: HoldingIn):
        code = (h.code or "").strip()
        if not code.isdigit() or len(code) != 6:
            raise HTTPException(400, "代码必须是 6 位数字")
        if h.shares <= 0:
            raise HTTPException(400, "数量必须大于 0")
        return {"data": pf.add_holding(code, h.shares, h.cost)}

    @router.delete("/portfolio/holding")
    def portfolio_remove(code: str = Query(...)):
        return {"data": pf.remove_holding(code.strip())}

    @router.post("/portfolio/close")
    def portfolio_close(c: CloseIn):
        code = (c.code or "").strip()
        if not code.isdigit() or len(code) != 6:
            raise HTTPException(400, "代码必须是 6 位数字")
        if c.price <= 0 or c.shares <= 0:
            raise HTTPException(400, "清仓价与股数必须大于 0")
        date = (c.date or "").strip()
        if not date:
            raise HTTPException(400, "请填清仓日期")
        from datetime import datetime

        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(400, "清仓日期格式应为 YYYY-MM-DD") from None
        return {"data": pf.close_position(code, date, c.price, c.shares, c.cost)}

    @router.delete("/portfolio/close")
    def portfolio_close_remove(index: int = Query(...)):
        return {"data": pf.remove_closed(index)}

    @router.post("/portfolio/refresh")
    def portfolio_refresh():
        try:
            return {"data": pf.get_portfolio()}
        except Exception as e:
            raise HTTPException(502, f"刷新失败：{e}") from e
