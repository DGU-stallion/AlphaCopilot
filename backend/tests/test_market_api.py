"""盘面数据 / 复盘看板 REST 端点集成测试。

逐端点验证 {data} 契约形状 + 数据源不可用时的优雅降级（空列表 / available=False，
不伪装 0，异常 → 502）。数据源全部 mock，不碰网络。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(db_path=str(tmp_path / "t.db"), workspace_root=tmp_path)
    with TestClient(app) as c:
        yield c


# ---- indices / quote（仅标准库，永远可用）----

def test_indices_wraps_data(client, monkeypatch):
    from research import astock
    monkeypatch.setattr(astock, "index_quote",
                        lambda: [{"name": "上证指数", "price": 3200.0, "change_pct": 0.5, "change_amt": 16.0}])
    r = client.get("/api/indices")
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    assert body["data"][0]["name"] == "上证指数"


def test_indices_degrades_to_empty(client, monkeypatch):
    from research import astock
    monkeypatch.setattr(astock, "index_quote", lambda: [])
    r = client.get("/api/indices")
    assert r.status_code == 200
    assert r.json()["data"] == []


def test_quote_wraps_data(client, monkeypatch):
    from research import astock
    monkeypatch.setattr(astock, "tencent_quote", lambda codes: {c: {"name": "x", "price": 1.0} for c in codes})
    r = client.get("/api/quote?codes=600519,000858")
    assert r.status_code == 200
    assert set(r.json()["data"].keys()) == {"600519", "000858"}


def test_quote_rejects_bad_codes(client):
    assert client.get("/api/quote?codes=ABC").status_code == 400
    assert client.get("/api/quote?codes=60051").status_code == 400
    assert client.get("/api/quote?codes=").status_code == 400


# ---- market.* 复用 research.market 数据层 ----

def test_market_overview_wraps_data(client, monkeypatch):
    from research import market
    monkeypatch.setattr(market, "get_overview",
                        lambda: {"sentiment": {"up": 3000}, "sectors": [], "updated": "2026-09-05 18:00"})
    r = client.get("/api/market/overview")
    assert r.status_code == 200
    assert r.json()["data"]["sentiment"]["up"] == 3000


def test_market_overview_degrades(client, monkeypatch):
    """akshare 缺失时数据层返回空 sentiment/sectors，端点仍 200 且不伪装 0。"""
    from research import market
    monkeypatch.setattr(market, "get_overview",
                        lambda: {"sentiment": {}, "sectors": [], "updated": "2026-09-05 18:00"})
    r = client.get("/api/market/overview")
    assert r.status_code == 200
    assert r.json()["data"]["sentiment"] == {}


def test_market_emotion_wraps_data(client, monkeypatch):
    from research import market
    monkeypatch.setattr(market, "get_short_term_emotion",
                        lambda: {"date": "2026-09-05", "zt_count": 42, "ladder": [], "lianban_stocks": []})
    r = client.get("/api/market/emotion")
    assert r.status_code == 200
    assert r.json()["data"]["zt_count"] == 42


def test_market_emotion_degrades_empty(client, monkeypatch):
    from research import market
    monkeypatch.setattr(market, "get_short_term_emotion", lambda: {})
    r = client.get("/api/market/emotion")
    assert r.status_code == 200
    assert r.json()["data"] == {}


def test_market_turnover_top_wraps_data(client, monkeypatch):
    from research import market
    monkeypatch.setattr(market, "get_turnover_top",
                        lambda: {"stocks": [{"code": "600519", "name": "贵州茅台"}], "updated": "x"})
    r = client.get("/api/market/turnover-top")
    assert r.status_code == 200
    assert r.json()["data"]["stocks"][0]["code"] == "600519"


def test_global_indices_wraps_data(client, monkeypatch):
    from research import market
    monkeypatch.setattr(market, "get_global_indices",
                        lambda: [{"key": "DJI", "name": "道琼斯", "region": "美股",
                                  "price": 40000.0, "change_pct": 0.3}])
    r = client.get("/api/global/indices")
    assert r.status_code == 200
    assert r.json()["data"][0]["name"] == "道琼斯"


def test_global_indices_degrades_empty(client, monkeypatch):
    from research import market
    monkeypatch.setattr(market, "get_global_indices", lambda: [])
    r = client.get("/api/global/indices")
    assert r.status_code == 200
    assert r.json()["data"] == []


# ---- session / overseas / live-emotion（源 server.py）----

def test_market_session_shape(client, monkeypatch):
    from duanxian import trade_calendar
    monkeypatch.setattr(trade_calendar, "quote_trade_day", lambda: None)
    r = client.get("/api/market/session")
    assert r.status_code == 200
    data = r.json()["data"]
    # quotes_of 取不到时如实标「未知」，不拿今天顶替
    assert data["quotes_of"] is None
    assert data["phase"] == "未知"
    assert "label" in data and "now" in data and "today" in data


def test_market_overseas_degrades_when_source_down(client, monkeypatch):
    from duanxian import overseas
    monkeypatch.setattr(overseas, "_fetch", lambda symbols: {})
    r = client.get("/api/market/overseas")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["available"] is False
    assert "reason" in data


def test_market_live_emotion_degrades_when_pool_down(client, monkeypatch):
    """涨停池取数失败（返回 None）→ available=False，不伪装 0。"""
    from duanxian import live_emotion
    monkeypatch.setattr(live_emotion, "_pool", lambda kind, ymd: None)
    monkeypatch.setattr(live_emotion.trade_calendar, "is_settled", lambda d: False)
    # 清缓存以免受其它测试/真实网络污染
    live_emotion._cache.clear()
    r = client.get("/api/market/live-emotion")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["available"] is False


def test_market_live_emotion_computes_when_pool_available(client, monkeypatch):
    from duanxian import live_emotion

    def fake_pool(kind, ymd):
        if kind == "getTopicZTPool":
            return [{"c": "600519", "lbc": 1}, {"c": "000001", "lbc": 2}]
        if kind == "getTopicZBPool":
            return [{"c": "000002", "lbc": 1}]
        if kind == "getTopicDTPool":
            return []
        return []

    monkeypatch.setattr(live_emotion, "_pool", fake_pool)
    monkeypatch.setattr(live_emotion.trade_calendar, "is_settled", lambda d: True)
    monkeypatch.setattr(live_emotion.trade_calendar, "prev_trade_date", lambda d: None)
    live_emotion._cache.clear()
    r = client.get("/api/market/live-emotion")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["available"] is True
    assert data["zt_count"] == 2
    assert data["zb_count"] == 1
    assert data["max_boards"] == 2
    assert data["lianban_count"] == 1
    # 封板率 = 2 / (2+1)
    assert data["seal_rate"] == round(2 / 3, 4)


# ---- 涨停样本统计（确定性统计；逐日样本 mock，不碰网络）----

def _fake_pool_rows(seal: str = "093000"):
    """一天的「昨日涨停股今日表现」样本：含首板/连板、封板时间、涨停价字段。"""
    return [
        {"code": "600519", "name": "首板早封", "ret": 3.5, "prev_boards": 1,
         "seal_time": seal, "sector": "白酒", "close": 11.0, "limit_price": 11.0},
        {"code": "000001", "name": "连板", "ret": -2.0, "prev_boards": 2,
         "seal_time": "104500", "sector": "银行", "close": 9.0, "limit_price": 9.9},
        {"code": "000002", "name": "首板尾盘", "ret": 1.0, "prev_boards": 1,
         "seal_time": "144500", "sector": "白酒", "close": 5.0, "limit_price": 6.0},
    ]


def test_backtest_wraps_data(client, monkeypatch):
    from alpha import limit_up_sample
    dates = [f"2026-08-{d:02d}" for d in range(1, 8)]
    monkeypatch.setattr(limit_up_sample.trade_calendar, "last_trade_dates", lambda days: dates)
    monkeypatch.setattr(limit_up_sample, "_fetch_prev_pool", lambda d: _fake_pool_rows())
    r = client.get("/api/backtest?days=30")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["available"] is True
    assert data["layer"] == "market_phenomenon"
    assert data["days_used"] == len(dates)
    # 全体涨停基准存在，且首板策略样本 = 每天 2 首板 × 天数
    assert data["strategies"]["全体涨停"]["overall"]["sample"] == 3 * len(dates)
    assert data["strategies"]["首板打板"]["overall"]["sample"] == 2 * len(dates)
    # 封板曲线是列表，含分档
    assert isinstance(data["seal_curve"], list) and data["seal_curve"]
    # sample_caveat 原文风险提示不得丢
    assert "市场现象统计" in data["sample_caveat"]


def test_backtest_degrades_when_source_down(client, monkeypatch):
    """mac 无 akshare / 取数全失败 → available=False，不伪装 0。"""
    from alpha import limit_up_sample
    dates = [f"2026-08-{d:02d}" for d in range(1, 8)]
    monkeypatch.setattr(limit_up_sample.trade_calendar, "last_trade_dates", lambda days: dates)
    monkeypatch.setattr(limit_up_sample, "_fetch_prev_pool", lambda d: None)
    r = client.get("/api/backtest?days=30")
    assert r.status_code == 200
    assert r.json()["data"]["available"] is False


def test_backtest_refresh_is_post(client, monkeypatch):
    from alpha import limit_up_sample
    dates = [f"2026-08-{d:02d}" for d in range(1, 8)]
    monkeypatch.setattr(limit_up_sample.trade_calendar, "last_trade_dates", lambda days: dates)
    monkeypatch.setattr(limit_up_sample, "_fetch_prev_pool", lambda d: _fake_pool_rows())
    # GET refresh 不允许（只认 POST）
    assert client.get("/api/backtest/refresh").status_code == 405
    r = client.post("/api/backtest/refresh?days=30")
    assert r.status_code == 200
    assert r.json()["data"]["available"] is True


def test_backtest_rejects_out_of_range_days(client):
    assert client.get("/api/backtest?days=3").status_code == 422
    assert client.get("/api/backtest?days=120").status_code == 422
