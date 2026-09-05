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


def test_market_index_degrades(monkeypatch):
    monkeypatch.setattr(market.astock, "index_quote", lambda: [])
    out = market.market_index()
    assert out["rows"][0][0] == "暂不可用"
