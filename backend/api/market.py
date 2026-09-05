"""盘面数据 / 复盘看板 —— REST 端点逆向搬运（{data} 契约，前端 lib/api.ts 直接解包 payload.data）。

原实现散落在 vibe-astock/vr/app.py（indices/quote/market.*）与 server.py（session/overseas/
live-emotion）。这里原样缝合搬运：数据计算复用 AlphaCopilot 已有的 research.astock /
research.market 数据层与新搬入的 duanxian（session/overseas/live-emotion）。

纪律：
  · 全部 {data:...} 契约（与前端 request() 解包一致）；
  · quote/indices 的 codes 6 位数字校验失败 → 400；
  · 其余数据源异常 → 502（HTTPException），mac 无 mootdx/akshare 时走原降级路径
    （数据源不可达返回空列表 / available=False 降级对象，不伪装 0）。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from alpha import limit_up_sample
from duanxian import live_emotion, overseas, trade_calendar
from duanxian.util import china_now, china_today, is_a_share_closed, is_weekend
from research import astock, macro, market


def build_market_router() -> APIRouter:
    router = APIRouter(prefix="/api")

    # ---- A 股大盘指数 / 个股行情（仅标准库，永远可用）----

    @router.get("/indices")
    def indices() -> dict:
        """A股大盘指数实时行情（上证/深证成指/创业板指/沪深300）。仅标准库。"""
        try:
            return {"data": astock.index_quote()}
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"指数行情异常：{e}") from e

    @router.get("/quote")
    def quote(codes: str = Query(..., description="逗号分隔的 6 位代码")) -> dict:
        """实时行情：现价/涨跌/PE/PB/市值/换手/涨跌停。仅标准库，永远可用。"""
        lst = [c.strip() for c in codes.split(",") if c.strip()]
        if not lst or any(not c.isdigit() or len(c) != 6 for c in lst):
            raise HTTPException(400, "codes 必须是逗号分隔的 6 位数字")
        try:
            return {"data": astock.tencent_quote(lst)}
        except Exception as e:  # noqa: BLE001  边界统一兜底
            raise HTTPException(502, f"行情源异常：{e}") from e

    # ---- 市场情绪 / 板块资金 / 短线情绪 / 成交额榜 / 全球指数 ----

    @router.get("/market/overview")
    def market_overview() -> dict:
        """市场情绪 + 板块资金流（板块/大盘级，全站共享缓存 5 分钟）。"""
        try:
            return {"data": market.get_overview()}
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"市场总览异常：{e}") from e

    @router.get("/market/emotion")
    def market_emotion() -> dict:
        """短线情绪：连板梯队 / 最高连板 / 炸板率 / 封板率 / 晋级率 / 涨跌停家数。全站共享缓存 5 分钟。"""
        try:
            return {"data": market.get_short_term_emotion()}
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"短线情绪异常：{e}") from e

    @router.get("/market/turnover-top")
    def market_turnover_top() -> dict:
        """全市场成交额榜 Top20（客观公开榜单数据）。全站共享缓存 5 分钟。"""
        try:
            return {"data": market.get_turnover_top()}
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"成交额榜异常：{e}") from e

    @router.get("/global/indices")
    def global_indices() -> dict:
        """全球指数快照（道指 / 标普500 / 纳斯达克 / 恒生 / 恒生科技）。缓存 5 分钟。"""
        try:
            return {"data": market.get_global_indices()}
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"全球指数异常：{e}") from e

    # ---- 场次标注 / 隔夜外围 / 今日实时打板情绪（源：server.py 507/546/556）----

    @router.get("/market/session")
    def market_session() -> dict:
        """此刻的「实时行情」到底属于哪一场（盘前返回上一场收盘，UI 据此如实标注）。"""
        try:
            today = china_today()
            quotes_of = trade_calendar.quote_trade_day()
            is_today_ = bool(quotes_of) and quotes_of == today
            closed = is_a_share_closed()

            now = china_now()
            hhmm = now.hour * 60 + now.minute
            if not quotes_of:
                phase, label = "未知", "行情时间取不到"
            elif is_today_ and not closed and hhmm < 9 * 60 + 25:
                phase, label = "集合竞价", "集合竞价 · 尚未成交"
            elif is_today_ and not closed:
                phase, label = "盘中", "盘中 · 实时"
            elif is_today_:
                phase, label = "已收盘", f"{today} 收盘"
            elif is_weekend(today):
                phase, label = "非交易日", f"非交易日 · 显示 {quotes_of} 收盘"
            elif not closed:
                phase, label = "盘前", f"盘前 · 显示 {quotes_of} 收盘"
            else:
                phase, label = "非交易日", f"今日无成交 · 显示 {quotes_of} 收盘"

            return {"data": {
                "now": now.strftime("%Y-%m-%d %H:%M"), "today": today,
                "quotes_of": quotes_of, "is_today": is_today_,
                "phase": phase, "label": label,
            }}
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"场次判定异常：{e}") from e

    @router.get("/market/overseas")
    def market_overseas() -> dict:
        """隔夜外围：美港股指数 + 美股七姐妹，各自带交易日。"""
        try:
            return {"data": overseas.overseas_snapshot()}
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"隔夜外围异常：{e}") from e

    @router.get("/market/live-emotion")
    def market_live_emotion() -> dict:
        """今日**实时**打板情绪（盘面数据页用，与复盘口径的 /market/emotion 并存）。"""
        try:
            return {"data": live_emotion.snapshot()}
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"实时打板情绪异常：{e}") from e

    # ---- 涨停样本统计（确定性统计，非 AI；逐日样本落盘缓存，历史结果不再变）----

    @router.get("/backtest")
    def backtest(days: int = Query(30, ge=5, le=90)) -> dict:
        """昨日涨停样本在次日的历史表现统计。mac 无 akshare 时降级 available=False。"""
        try:
            return {"data": limit_up_sample.run_backtest(days=days)}
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"涨停样本统计异常：{e}") from e

    @router.post("/backtest/refresh")
    def backtest_refresh(days: int = Query(30, ge=5, le=90)) -> dict:
        """强制重算（走外网逐日取数、写盘），只认 POST（防跨站 GET 触发）。"""
        try:
            return {"data": limit_up_sample.run_backtest(days=days)}
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"涨停样本统计异常：{e}") from e

    # ---- 宏观看板：大宗商品 / 汇率（腾讯 gtimg）/ 美债收益率（财政部 CSV）/ 加密 ----
    # 每类自洽降级：取不到返回 {available:False, reason}，前端如实显示「暂不可用」不伪造。

    @router.get("/macro/commodities")
    def macro_commodities() -> dict:
        """大宗商品：原油 / 布伦特 / 黄金 / 伦敦金 / 白银。"""
        return {"data": macro.commodities()}

    @router.get("/macro/forex")
    def macro_forex() -> dict:
        """汇率：USDCNY / EURUSD / USDJPY / GBPUSD / USDHKD。"""
        return {"data": macro.forex()}

    @router.get("/macro/rates")
    def macro_rates() -> dict:
        """美债收益率曲线关键期限：2Y / 5Y / 10Y / 30Y。"""
        return {"data": macro.rates()}

    @router.get("/macro/crypto")
    def macro_crypto() -> dict:
        """加密货币（BTC）：暂无靠谱免费现货源，降级占位。"""
        return {"data": macro.crypto()}

    return router
