"""S2 盘面数据 + 涨停样本统计 —— 纯计算 fixture 测试 + 内置页注册/降级验证。

纯计算函数用 fixture 断言（不碰网络，对标 vibe-astock 的可测纪律）；
内置页经白名单注册、数据源不可用时优雅降级为「暂不可用」而非 0。
"""

from __future__ import annotations

from alpha import market


# ---- 纯计算 fixture 测试（不碰网络）----

def test_compute_ladder_distribution():
    pool = [
        {"lbc": 1}, {"lbc": 1}, {"lbc": 2}, {"lbc": 3}, {"lbc": 3}, {"lbc": 3},
    ]
    assert market.compute_ladder(pool) == {1: 2, 2: 1, 3: 3}


def test_compute_ladder_defaults_missing_lbc_to_1():
    assert market.compute_ladder([{}, {"lbc": None}]) == {1: 2}


def test_compute_breadth_seal_rate():
    zt = [{"lbc": 1}, {"lbc": 2}]
    zb = [{"lbc": 1}]  # 1 炸板
    dt = []
    b = market.compute_breadth(zt, zb, dt)
    assert b["limit_up"] == 2
    assert b["broken"] == 1
    assert b["limit_down"] == 0
    assert b["seal_rate"] == round(2 / 3, 3)
    assert b["max_boards"] == 2


def test_compute_breadth_seal_rate_none_when_no_pool():
    b = market.compute_breadth([], [], [])
    assert b["seal_rate"] is None
    assert b["max_boards"] == 0


def test_compute_limitup_stats_industry_sorted_desc():
    pool = [
        {"lbc": 1, "hybk": "半导体"},
        {"lbc": 2, "hybk": "半导体"},
        {"lbc": 1, "hybk": "白酒"},
    ]
    stats = market.compute_limitup_stats(pool)
    assert stats["total"] == 3
    assert stats["ladder"] == {1: 2, 2: 1}
    # 行业从多到少
    assert list(stats["by_industry"].items())[0] == ("半导体", 2)


# ---- 内置页优雅降级（数据源不可用时标注不可用，不伪装成 0）----

def test_market_breadth_degrades_when_source_empty(monkeypatch):
    monkeypatch.setattr(market.astock, "em_zt_topic_pool", lambda *a, **k: [])
    out = market.market_breadth()
    labels = [it["label"] for it in out["items"]]
    assert "数据状态" in labels
    assert out["items"][0]["value"] == "暂不可用"


def test_market_breadth_computes_when_source_available(monkeypatch):
    def fake_pool(endpoint, date, **k):
        if endpoint == "getTopicZTPool":
            return [{"lbc": 1}, {"lbc": 2}, {"lbc": 3}]
        if endpoint == "getTopicZBPool":
            return [{"lbc": 1}]
        return []
    monkeypatch.setattr(market.astock, "em_zt_topic_pool", fake_pool)
    out = market.market_breadth()
    items = {it["label"]: it["value"] for it in out["items"]}
    assert items["涨停"] == 3
    assert items["炸板"] == 1
    assert items["最高连板"] == 3


def test_limit_up_ladder_returns_valid_bar_option(monkeypatch):
    monkeypatch.setattr(
        market.astock, "em_zt_topic_pool",
        lambda *a, **k: [{"lbc": 1}, {"lbc": 1}, {"lbc": 2}],
    )
    opt = market.limit_up_ladder()
    assert "series" in opt and opt["series"][0]["type"] == "bar"
    assert opt["series"][0]["data"] == [2, 1]  # 1板2家, 2板1家


# ---- 涨停原因映射（Bug A 回归：lianban_stocks[].reason 曾全为 None）----

def test_emotion_fills_reason_from_source(monkeypatch):
    """连板股的 reason 由问财题材串填充（数据源有值时不留空）。"""
    import research.market as rmarket

    def fake_pool(endpoint, date, *a, **k):
        if endpoint == "getTopicZTPool":
            return [
                {"c": "605577", "n": "龙版传媒", "lbc": 5, "p": 10000, "zdp": 10.0,
                 "amount": 1000, "ltsz": 1.0, "hybk": "出版"},
                {"c": "603162", "n": "海通发展", "lbc": 2, "p": 20000, "zdp": 10.0,
                 "amount": 500, "ltsz": 1.0, "hybk": "航运"},
            ]
        return []

    monkeypatch.setattr(rmarket.astock, "em_zt_topic_pool", fake_pool)
    monkeypatch.setattr(rmarket, "_fetch_zt_reasons",
                        lambda date: {"605577": "AI漫剧+出版发行", "603162": "干散货航运"})
    out = rmarket._emotion()
    reasons = {s["code"]: s["reason"] for s in out["lianban_stocks"]}
    assert reasons["605577"] == "AI漫剧+出版发行"
    assert reasons["603162"] == "干散货航运"


def test_emotion_reason_none_when_source_empty(monkeypatch):
    """问财缺 key / 失败 → reason 留 None（前端显示 —），不伪造。"""
    import research.market as rmarket

    monkeypatch.setattr(
        rmarket.astock, "em_zt_topic_pool",
        lambda endpoint, date, *a, **k: (
            [{"c": "605577", "n": "龙版传媒", "lbc": 3, "p": 10000, "zdp": 10.0,
              "amount": 1, "ltsz": 1.0, "hybk": "出版"}]
            if endpoint == "getTopicZTPool" else []),
    )
    monkeypatch.setattr(rmarket, "_fetch_zt_reasons", lambda date: {})
    out = rmarket._emotion()
    assert out["lianban_stocks"][0]["reason"] is None


def test_fetch_zt_reasons_no_key_returns_empty(monkeypatch):
    """未配置 IWENCAI_API_KEY 时直接返回空 dict，不发请求。"""
    import research.market as rmarket

    monkeypatch.delenv("IWENCAI_API_KEY", raising=False)
    assert rmarket._fetch_zt_reasons("20260905") == {}


def test_clean_reason_normalizes_and_limits():
    import research.market as rmarket

    assert rmarket._clean_reason("A，B,C") == "A+B+C"
    assert rmarket._clean_reason("a+b+c+d+e") == "a+b+c+d"  # 限 4 标签


def test_market_index_degrades(monkeypatch):
    monkeypatch.setattr(market.astock, "index_quote", lambda: [])
    out = market.market_index()
    assert out["rows"][0][0] == "暂不可用"


# ---- 指数日K取数：指数代码前缀归一化（Bug B 回归：000300 曾判成 sz、取回 0 行）----

def test_index_kline_uses_exchange_prefix(monkeypatch):
    """沪深300(000300) 走 gtimg 时须用 sh 前缀，否则 sz000300 取不到日K → 基准直线。"""
    import research.astock as astock

    captured = {}

    class _Resp:
        def read(self):
            # gtimg 回退源需要 data[sym] 节点；只要 _tencent_kline 用对了 sym 就能解析
            sym = captured["sym"]
            return (
                '{"data": {"' + sym + '": {"qfqday": '
                '[["2026-09-04", "4575.32", "4548.05", "4602.20", "4530.76", "1.0"]]}}}'
            ).encode("utf-8")

    def fake_urlopen(req, timeout=12):
        captured["sym"] = req.full_url.split("param=")[1].split(",")[0]
        return _Resp()

    monkeypatch.setattr(astock.urllib.request, "urlopen", fake_urlopen)
    rows = astock._tencent_kline("000300", category=4, offset=10)
    assert captured["sym"] == "sh000300"  # 指数走 _INDEX_PREFIX，非个股默认 sz
    assert rows and rows[0]["close"] == 4548.05


def test_stock_kline_prefix_unaffected_by_index_map(monkeypatch):
    """个股 000001（平安银行, sz）不得被指数映射误判成 sh —— _INDEX_PREFIX 只覆盖指数取数场景。

    注：000001 同时是上证综指代码，但指数映射只作用于此 gtimg K 线函数的指数取数；
    个股行情 tencent_quote 仍走 get_prefix（此测覆盖 K 线路径不影响个股前缀语义）。
    """
    import research.astock as astock
    # 个股代码不在 _INDEX_PREFIX 时应走 get_prefix；600519 → sh，000858 → sz
    assert "600519" not in astock._INDEX_PREFIX
    assert astock.get_prefix("600519") == "sh"
    assert astock.get_prefix("000858") == "sz"
