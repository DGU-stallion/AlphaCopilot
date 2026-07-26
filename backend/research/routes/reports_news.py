"""Reports & news route sub-module — myreports, radar, news, reports, announcements, financials."""

from __future__ import annotations

import time as _time

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from research.caches import ResearchCaches, validate_stock_code
from research.models import ReportIn

import research.astock as astock
import research.myreports as mr
import research.newsradar as newsradar


def register_reports_news_routes(router: APIRouter, *, caches: ResearchCaches) -> None:
    """Attach reports & news endpoints to the given router."""

    # ---- My Reports ----

    @router.get("/myreports")
    def myreports_list():
        return {"data": mr.list_reports()}

    @router.post("/myreports")
    def myreports_upload(r: ReportIn):
        try:
            return {"data": mr.save_report(r.name, r.content_b64)}
        except mr.ReportError as e:
            raise HTTPException(400, str(e)) from e

    @router.get("/myreports/file/{rid}")
    def myreports_file(rid: str):
        hit = mr.report_path(rid)
        if not hit:
            raise HTTPException(404, "研报不存在")
        path, name = hit
        return FileResponse(str(path), filename=name)

    @router.delete("/myreports/{rid}")
    def myreports_delete(rid: str):
        return {"data": {"ok": mr.delete_report(rid)}}

    # ---- News Radar ----

    @router.get("/radar")
    def radar():
        try:
            return {"data": newsradar.get_radar(force=False)}
        except Exception as e:
            raise HTTPException(502, f"资讯雷达异常：{e}") from e

    @router.post("/radar/refresh")
    def radar_refresh():
        try:
            return {"data": newsradar.fetch_radar()}
        except Exception as e:
            raise HTTPException(502, f"资讯雷达刷新失败：{e}") from e

    # ---- News / Reports / Announcements / Financials ----

    @router.get("/news")
    def news(code: str = Query(...), limit: int = Query(20, ge=1, le=50)):
        code = validate_stock_code(code)
        try:
            return {"data": astock.stock_news(code, limit=limit)}
        except astock.DependencyMissing as e:
            raise HTTPException(501, str(e)) from e
        except Exception as e:
            raise HTTPException(502, f"新闻源异常：{e}") from e

    @router.get("/reports")
    def reports(code: str = Query(...), pages: int = Query(2, ge=1, le=5)):
        code = validate_stock_code(code)
        try:
            rows = astock.eastmoney_reports(code, max_pages=pages)
            for r in rows:
                r["pdfUrl"] = (
                    astock.pdf_url(r.get("infoCode", "")) if r.get("infoCode") else None
                )
            return {"data": rows}
        except Exception as e:
            raise HTTPException(502, f"研报源异常：{e}") from e

    @router.get("/announcements")
    def announcements(code: str = Query(...)):
        code = validate_stock_code(code)
        hit = caches.ann_cache.get(code)
        if hit and _time.time() - hit[0] < 900:
            return {"data": hit[1]}
        try:
            data = astock.announcements(code)
            caches.ann_cache[code] = (_time.time(), data)
            return {"data": data}
        except Exception as e:
            raise HTTPException(502, f"公告源异常：{e}") from e

    @router.get("/financials")
    def financials(code: str = Query(...)):
        code = validate_stock_code(code)
        hit = caches.fin_cache.get(code)
        if hit and _time.time() - hit[0] < 1800:
            return {"data": hit[1]}
        try:
            data = astock.financials(code)
            caches.fin_cache[code] = (_time.time(), data)
            return {"data": data}
        except astock.DependencyMissing as e:
            raise HTTPException(501, str(e)) from e
        except Exception as e:
            raise HTTPException(502, f"财务摘要异常：{e}") from e
