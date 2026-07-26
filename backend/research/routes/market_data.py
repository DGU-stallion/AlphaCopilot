"""Market data route sub-module — indices, quote, valuation, kline, and signal endpoints."""

from __future__ import annotations

import time as _time

from fastapi import APIRouter, HTTPException, Query

from research.caches import ResearchCaches, validate_stock_code, cached_lookup

import research.astock as astock
import research.gstock as gstock
import research.market as market


def register_market_data_routes(router: APIRouter, *, caches: ResearchCaches) -> None:
    """Attach market data endpoints to the given router."""

    # ---- Market Overview ----

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

    # ---- A-Stock Core ----

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
        code = validate_stock_code(code)
        hit = caches.pct_cache.get(code)
        if hit and _time.time() - hit[0] < 1800:
            return {"data": hit[1]}
        try:
            data = astock.valuation_percentile(code)
            caches.pct_cache[code] = (_time.time(), data)
            return {"data": data}
        except astock.DependencyMissing as e:
            raise HTTPException(501, str(e)) from e
        except Exception as e:
            raise HTTPException(502, f"估值分位异常：{e}") from e

    @router.get("/valuation")
    def valuation(code: str = Query(...)):
        code = validate_stock_code(code)
        try:
            return {"data": astock.full_valuation(code)}
        except ValueError as e:
            raise HTTPException(404, str(e)) from e
        except Exception as e:
            raise HTTPException(502, f"估值计算异常：{e}") from e

    @router.get("/kline")
    def kline(
        code: str = Query(...),
        category: int = Query(4),
        offset: int = Query(60, ge=1, le=800),
    ):
        code = validate_stock_code(code)
        try:
            return {"data": astock.kline(code, category=category, offset=offset)}
        except astock.DependencyMissing as e:
            raise HTTPException(501, str(e)) from e
        except Exception as e:
            raise HTTPException(502, f"K线源异常：{e}") from e

    @router.get("/finance")
    def finance(code: str = Query(...)):
        code = validate_stock_code(code)
        try:
            return {"data": astock.finance(code)}
        except astock.DependencyMissing as e:
            raise HTTPException(501, str(e)) from e
        except Exception as e:
            raise HTTPException(502, f"财务源异常：{e}") from e

    @router.get("/info")
    def info(code: str = Query(...)):
        code = validate_stock_code(code)
        try:
            return {"data": astock.individual_info(code)}
        except astock.DependencyMissing as e:
            raise HTTPException(501, str(e)) from e
        except Exception as e:
            raise HTTPException(502, f"基本面源异常：{e}") from e

    @router.get("/disclosure")
    def disclosure(code: str = Query(...)):
        code = validate_stock_code(code)
        try:
            return {"data": astock.disclosure(code)}
        except astock.DependencyMissing as e:
            raise HTTPException(501, str(e)) from e
        except Exception as e:
            raise HTTPException(502, f"公告源异常：{e}") from e

    # ---- 资金面 / 筹码 / 信号 ----

    @router.get("/margin")
    def margin(code: str = Query(...)):
        code = validate_stock_code(code)
        try:
            return {"data": cached_lookup(caches.dc_cache, "margin", code, 1800, lambda: astock.margin_trading(code))}
        except Exception as e:
            raise HTTPException(502, f"融资融券异常：{e}") from e

    @router.get("/block-trade")
    def block_trade(code: str = Query(...)):
        code = validate_stock_code(code)
        try:
            return {"data": cached_lookup(caches.dc_cache, "block", code, 1800, lambda: astock.block_trade(code))}
        except Exception as e:
            raise HTTPException(502, f"大宗交易异常：{e}") from e

    @router.get("/holders")
    def holders(code: str = Query(...)):
        code = validate_stock_code(code)
        try:
            return {"data": cached_lookup(caches.dc_cache, "holders", code, 1800, lambda: astock.holder_num_change(code))}
        except Exception as e:
            raise HTTPException(502, f"股东户数异常：{e}") from e

    @router.get("/dividend")
    def dividend(code: str = Query(...)):
        code = validate_stock_code(code)
        try:
            return {"data": cached_lookup(caches.dc_cache, "dividend", code, 1800, lambda: astock.dividend_history(code))}
        except Exception as e:
            raise HTTPException(502, f"分红送转异常：{e}") from e

    @router.get("/fund-flow")
    def fund_flow(code: str = Query(...)):
        code = validate_stock_code(code)
        try:
            return {"data": cached_lookup(caches.dc_cache, "fundflow", code, 900, lambda: astock.stock_fund_flow_120d(code))}
        except Exception as e:
            raise HTTPException(502, f"资金流异常：{e}") from e

    @router.get("/dragon-tiger")
    def dragon_tiger(code: str = Query(...)):
        code = validate_stock_code(code)
        try:
            return {"data": cached_lookup(caches.dc_cache, "dt", code, 1800, lambda: astock.dragon_tiger_board(code))}
        except Exception as e:
            raise HTTPException(502, f"龙虎榜异常：{e}") from e

    @router.get("/lockup")
    def lockup(code: str = Query(...)):
        code = validate_stock_code(code)
        try:
            return {"data": cached_lookup(caches.dc_cache, "lockup", code, 1800, lambda: astock.lockup_expiry(code))}
        except Exception as e:
            raise HTTPException(502, f"解禁日历异常：{e}") from e

    @router.get("/blocks")
    def blocks(code: str = Query(...)):
        code = validate_stock_code(code)
        try:
            return {"data": cached_lookup(caches.dc_cache, "blocks", code, 1800, lambda: astock.concept_blocks(code))}
        except Exception as e:
            raise HTTPException(502, f"板块归属异常：{e}") from e

    @router.get("/hot-concepts")
    def hot_concepts(code: str = Query(...)):
        code = validate_stock_code(code)
        try:
            return {"data": cached_lookup(caches.dc_cache, "hotcon", code, 900, lambda: astock.hot_concepts(code))}
        except Exception as e:
            raise HTTPException(502, f"热门概念异常：{e}") from e

    @router.get("/investor-qa")
    def investor_qa(code: str = Query(...)):
        code = validate_stock_code(code)
        try:
            return {"data": cached_lookup(caches.dc_cache, "irm", code, 900, lambda: astock.investor_qa(code))}
        except Exception as e:
            raise HTTPException(502, f"互动易异常：{e}") from e

    @router.get("/industry")
    def industry(top: int = Query(20, ge=5, le=50)):
        key = ("industry", str(top))
        hit = caches.dc_cache.get(key)
        if hit and _time.time() - hit[0] < 300:
            return {"data": hit[1]}
        try:
            data = astock.industry_comparison(top_n=top)
            caches.dc_cache[key] = (_time.time(), data)
            return {"data": data}
        except Exception as e:
            raise HTTPException(502, f"行业排名异常：{e}") from e
