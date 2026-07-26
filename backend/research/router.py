"""Research 模块路由集合 —— 供统一后端入口 include_router 使用。

所有路径不带 /api/ 前缀（由调用方设置 prefix="/api/research"）。
不包含中间件（CORS、认证）和应用级副作用（如 scheduler），这些由 app.py 或统一入口管理。
"""

from __future__ import annotations

import json
import time as _time

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

import astock
import chat as chat_layer
import cli_runtime
import gstock
import newsradar
import portfolio as pf
import market
import myreports as mr


# ------------------------------------------------------------------
# Pydantic 模型（必须在模块级定义，避免 forward reference 问题）
# ------------------------------------------------------------------

class LLMConfig(BaseModel):
    provider: str = ""
    baseURL: str = ""
    apiKey: str = ""
    model: str


class ChatReq(BaseModel):
    messages: list[dict]
    context: str = ""
    llm: LLMConfig


class HoldingIn(BaseModel):
    code: str
    shares: float
    cost: float


class CloseIn(BaseModel):
    code: str
    date: str
    price: float
    shares: float
    cost: float


class ReportIn(BaseModel):
    name: str
    content_b64: str


# ------------------------------------------------------------------
# 模块级缓存容器
# ------------------------------------------------------------------

_PCT_CACHE: dict = {}
_ANN_CACHE: dict = {}
_FIN_CACHE: dict = {}
_DC_CACHE: dict = {}


def _validate(code: str) -> str:
    code = (code or "").strip()
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(400, "代码必须是 6 位数字")
    return code


def _cached(endpoint: str, code: str, ttl: int, fetch):
    key = (endpoint, code)
    hit = _DC_CACHE.get(key)
    if hit and _time.time() - hit[0] < ttl:
        return hit[1]
    data = fetch()
    _DC_CACHE[key] = (_time.time(), data)
    return data


def create_research_router() -> APIRouter:
    """创建 research 模块的 APIRouter，路径无前缀。"""
    router = APIRouter()

    # ------------------------------------------------------------------
    # 路由
    # ------------------------------------------------------------------

    @router.get("/health")
    def health():
        return {"ok": True, "service": "vibe-research-api", "version": "0.1.3"}

    # ---- AI Chat ----

    @router.post("/chat")
    def chat(req: ChatReq):
        """系统 AI 对话，流式 NDJSON。"""
        if not req.messages:
            raise HTTPException(400, "messages 不能为空")
        if not req.llm.model:
            raise HTTPException(400, "缺少模型配置，请先在「接入 AI」里选择")

        is_cli = req.llm.provider.startswith("cli-")
        if is_cli:
            kind = req.llm.provider[4:]
            if not cli_runtime.detect_cli(kind):
                raise HTTPException(400, f"未检测到「{kind}」对应的本机命令。请先安装并登录该 CLI，或改用「API 接入」。")
        elif not req.llm.apiKey or not req.llm.baseURL:
            raise HTTPException(400, "缺少 Base URL 或 API Key，请先在「接入 AI」里填写")

        cfg = req.llm.model_dump()

        def gen():
            try:
                events = (chat_layer.run_chat_cli_stream if is_cli else chat_layer.run_chat_stream)(cfg, req.messages, req.context)
                for ev in events:
                    yield json.dumps(ev, ensure_ascii=False) + "\n"
            except Exception as e:
                yield json.dumps({"type": "error", "message": f"对话失败：{e}"}, ensure_ascii=False) + "\n"

        return StreamingResponse(gen(), media_type="application/x-ndjson")

    # ---- Portfolio ----

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

    # ---- Market ----

    @router.get("/market/overview")
    def market_overview():
        try:
            return {"data": market.get_overview()}
        except Exception as e:
            raise HTTPException(502, f"市场总览异常：{e}") from e

    @router.get("/market/emotion")
    def market_emotion():
        try:
            return {"data": market.get_short_term_emotion()}
        except Exception as e:
            raise HTTPException(502, f"短线情绪异常：{e}") from e

    @router.get("/market/turnover-top")
    def market_turnover_top():
        try:
            return {"data": market.get_turnover_top()}
        except Exception as e:
            raise HTTPException(502, f"成交额榜异常：{e}") from e

    # ---- Global ----

    @router.get("/global/indices")
    def global_indices():
        try:
            return {"data": market.get_global_indices()}
        except Exception as e:
            raise HTTPException(502, f"全球指数异常：{e}") from e

    @router.get("/global/stock")
    def global_stock(symbol: str = Query(..., min_length=1, max_length=16)):
        try:
            data = gstock.us_hk_stock(symbol.strip())
            if not data:
                raise HTTPException(404, f"未找到美股/港股代码「{symbol}」")
            return {"data": data}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(502, f"美港股查询异常：{e}") from e

    # ---- A-Stock ----

    @router.get("/indices")
    def indices():
        try:
            return {"data": astock.index_quote()}
        except Exception as e:
            raise HTTPException(502, f"指数行情异常：{e}") from e

    @router.get("/quote")
    def quote(codes: str = Query(..., description="逗号分隔的 6 位代码")):
        lst = [c.strip() for c in codes.split(",") if c.strip()]
        if not lst or any(not c.isdigit() or len(c) != 6 for c in lst):
            raise HTTPException(400, "codes 必须是逗号分隔的 6 位数字")
        try:
            return {"data": astock.tencent_quote(lst)}
        except Exception as e:
            raise HTTPException(502, f"行情源异常：{e}") from e

    @router.get("/valuation/percentile")
    def valuation_percentile(code: str = Query(...)):
        code = _validate(code)
        hit = _PCT_CACHE.get(code)
        if hit and _time.time() - hit[0] < 1800:
            return {"data": hit[1]}
        try:
            data = astock.valuation_percentile(code)
            _PCT_CACHE[code] = (_time.time(), data)
            return {"data": data}
        except astock.DependencyMissing as e:
            raise HTTPException(501, str(e)) from e
        except Exception as e:
            raise HTTPException(502, f"估值分位异常：{e}") from e

    @router.get("/announcements")
    def announcements(code: str = Query(...)):
        code = _validate(code)
        hit = _ANN_CACHE.get(code)
        if hit and _time.time() - hit[0] < 900:
            return {"data": hit[1]}
        try:
            data = astock.announcements(code)
            _ANN_CACHE[code] = (_time.time(), data)
            return {"data": data}
        except Exception as e:
            raise HTTPException(502, f"公告源异常：{e}") from e

    @router.get("/financials")
    def financials(code: str = Query(...)):
        code = _validate(code)
        hit = _FIN_CACHE.get(code)
        if hit and _time.time() - hit[0] < 1800:
            return {"data": hit[1]}
        try:
            data = astock.financials(code)
            _FIN_CACHE[code] = (_time.time(), data)
            return {"data": data}
        except astock.DependencyMissing as e:
            raise HTTPException(501, str(e)) from e
        except Exception as e:
            raise HTTPException(502, f"财务摘要异常：{e}") from e

    @router.get("/valuation")
    def valuation(code: str = Query(...)):
        code = _validate(code)
        try:
            return {"data": astock.full_valuation(code)}
        except ValueError as e:
            raise HTTPException(404, str(e)) from e
        except Exception as e:
            raise HTTPException(502, f"估值计算异常：{e}") from e

    @router.get("/reports")
    def reports(code: str = Query(...), pages: int = Query(2, ge=1, le=5)):
        code = _validate(code)
        try:
            rows = astock.eastmoney_reports(code, max_pages=pages)
            for r in rows:
                r["pdfUrl"] = astock.pdf_url(r.get("infoCode", "")) if r.get("infoCode") else None
            return {"data": rows}
        except Exception as e:
            raise HTTPException(502, f"研报源异常：{e}") from e

    @router.get("/news")
    def news(code: str = Query(...), limit: int = Query(20, ge=1, le=50)):
        code = _validate(code)
        try:
            return {"data": astock.stock_news(code, limit=limit)}
        except astock.DependencyMissing as e:
            raise HTTPException(501, str(e)) from e
        except Exception as e:
            raise HTTPException(502, f"新闻源异常：{e}") from e

    @router.get("/info")
    def info(code: str = Query(...)):
        code = _validate(code)
        try:
            return {"data": astock.individual_info(code)}
        except astock.DependencyMissing as e:
            raise HTTPException(501, str(e)) from e
        except Exception as e:
            raise HTTPException(502, f"基本面源异常：{e}") from e

    @router.get("/disclosure")
    def disclosure(code: str = Query(...)):
        code = _validate(code)
        try:
            return {"data": astock.disclosure(code)}
        except astock.DependencyMissing as e:
            raise HTTPException(501, str(e)) from e
        except Exception as e:
            raise HTTPException(502, f"公告源异常：{e}") from e

    @router.get("/kline")
    def kline(code: str = Query(...), category: int = Query(4), offset: int = Query(60, ge=1, le=800)):
        code = _validate(code)
        try:
            return {"data": astock.kline(code, category=category, offset=offset)}
        except astock.DependencyMissing as e:
            raise HTTPException(501, str(e)) from e
        except Exception as e:
            raise HTTPException(502, f"K线源异常：{e}") from e

    @router.get("/finance")
    def finance(code: str = Query(...)):
        code = _validate(code)
        try:
            return {"data": astock.finance(code)}
        except astock.DependencyMissing as e:
            raise HTTPException(501, str(e)) from e
        except Exception as e:
            raise HTTPException(502, f"财务源异常：{e}") from e

    # ---- 资金面 / 筹码 / 信号 ----

    @router.get("/margin")
    def margin(code: str = Query(...)):
        code = _validate(code)
        try:
            return {"data": _cached("margin", code, 1800, lambda: astock.margin_trading(code))}
        except Exception as e:
            raise HTTPException(502, f"融资融券异常：{e}") from e

    @router.get("/block-trade")
    def block_trade(code: str = Query(...)):
        code = _validate(code)
        try:
            return {"data": _cached("block", code, 1800, lambda: astock.block_trade(code))}
        except Exception as e:
            raise HTTPException(502, f"大宗交易异常：{e}") from e

    @router.get("/holders")
    def holders(code: str = Query(...)):
        code = _validate(code)
        try:
            return {"data": _cached("holders", code, 1800, lambda: astock.holder_num_change(code))}
        except Exception as e:
            raise HTTPException(502, f"股东户数异常：{e}") from e

    @router.get("/dividend")
    def dividend(code: str = Query(...)):
        code = _validate(code)
        try:
            return {"data": _cached("dividend", code, 1800, lambda: astock.dividend_history(code))}
        except Exception as e:
            raise HTTPException(502, f"分红送转异常：{e}") from e

    @router.get("/fund-flow")
    def fund_flow(code: str = Query(...)):
        code = _validate(code)
        try:
            return {"data": _cached("fundflow", code, 900, lambda: astock.stock_fund_flow_120d(code))}
        except Exception as e:
            raise HTTPException(502, f"资金流异常：{e}") from e

    @router.get("/dragon-tiger")
    def dragon_tiger(code: str = Query(...)):
        code = _validate(code)
        try:
            return {"data": _cached("dt", code, 1800, lambda: astock.dragon_tiger_board(code))}
        except Exception as e:
            raise HTTPException(502, f"龙虎榜异常：{e}") from e

    @router.get("/lockup")
    def lockup(code: str = Query(...)):
        code = _validate(code)
        try:
            return {"data": _cached("lockup", code, 1800, lambda: astock.lockup_expiry(code))}
        except Exception as e:
            raise HTTPException(502, f"解禁日历异常：{e}") from e

    @router.get("/blocks")
    def blocks(code: str = Query(...)):
        code = _validate(code)
        try:
            return {"data": _cached("blocks", code, 1800, lambda: astock.concept_blocks(code))}
        except Exception as e:
            raise HTTPException(502, f"板块归属异常：{e}") from e

    @router.get("/hot-concepts")
    def hot_concepts(code: str = Query(...)):
        code = _validate(code)
        try:
            return {"data": _cached("hotcon", code, 900, lambda: astock.hot_concepts(code))}
        except Exception as e:
            raise HTTPException(502, f"热门概念异常：{e}") from e

    @router.get("/investor-qa")
    def investor_qa(code: str = Query(...)):
        code = _validate(code)
        try:
            return {"data": _cached("irm", code, 900, lambda: astock.investor_qa(code))}
        except Exception as e:
            raise HTTPException(502, f"互动易异常：{e}") from e

    @router.get("/industry")
    def industry(top: int = Query(20, ge=5, le=50)):
        key = ("industry", str(top))
        hit = _DC_CACHE.get(key)
        if hit and _time.time() - hit[0] < 300:
            return {"data": hit[1]}
        try:
            data = astock.industry_comparison(top_n=top)
            _DC_CACHE[key] = (_time.time(), data)
            return {"data": data}
        except Exception as e:
            raise HTTPException(502, f"行业排名异常：{e}") from e

    return router
