"""T45 展示页 REST + 渲染端点测试 —— 不联网（monkeypatch 假数据源）。

覆盖：
  · GET /api/pages          内置页已 upsert（correlation + daily-review）
  · GET /api/pages/{slug}    命中/404
  · POST /api/pages          合法 spec 落库；非法 fn 的 spec 转 400
  · POST /api/pages/{slug}/render
        correlation 页返回 3 个 block，每个 option 有非空 series
        参数越界（window 超上限）转 400

render 用 monkeypatch 把 alpha.data.closes_with_dates 换成假数据（factor._fetch 经它取数），
故不触网。TestClient 用法参考 test_session_api.py（这里端点非流式，用同步 TestClient 即可）。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alpha import data
from api.app import create_app


def _fake_closes_with_dates(code, period=data.DAY, count=250):
    """确定性假收盘价：所有标的共享同一批日期（对齐取交集后非空），价格随 code 微扰。"""
    base = float(int(code[-2:]) + 10)
    out = []
    for i in range(count):
        # 日期升序且唯一（避免 dict 去重成一条）；价格带波动保证收益率非全零。
        date = f"2025-{i // 28 + 1:02d}-{i % 28 + 1:02d}"
        price = base + i * 0.5 + (i % 5) * 0.3
        out.append((date, price))
    return out


@pytest.fixture
def client(monkeypatch, tmp_path):
    # factor._fetch 调 data.closes_with_dates；patch 到假数据，全程不触网。
    monkeypatch.setattr(data, "closes_with_dates", _fake_closes_with_dates)
    # names 走 tencent_quote（网络）；测试内回退代码，保持离线确定性。
    monkeypatch.setattr(data, "names", lambda codes: {c: c for c in codes})
    app = create_app(db_path=":memory:", workspace_root=tmp_path)
    with TestClient(app) as c:
        yield c


def test_list_pages_has_builtins(client):
    pages = client.get("/api/pages").json()
    slugs = {p["slug"] for p in pages}
    assert {"correlation", "daily-review"} <= slugs


def test_get_page_by_slug_and_404(client):
    ok = client.get("/api/pages/correlation")
    assert ok.status_code == 200
    assert ok.json()["slug"] == "correlation"

    missing = client.get("/api/pages/does-not-exist")
    assert missing.status_code == 404


def test_create_page(client):
    spec = {
        "slug": "my-page",
        "title": "我的页",
        "kind": "user",
        "layout": "stack",
        "blocks": [{"kind": "markdown", "span": 3, "text": "hi"}],
    }
    r = client.post("/api/pages", json={"spec": spec})
    assert r.status_code == 200
    assert r.json()["page_id"]
    assert client.get("/api/pages/my-page").status_code == 200


def test_create_page_rejects_unregistered_fn(client):
    spec = {
        "slug": "bad-page",
        "title": "非法",
        "kind": "user",
        "layout": "grid",
        "blocks": [{"kind": "chart", "span": 1, "analysis_ref": {"fn": "not.registered"}}],
    }
    r = client.post("/api/pages", json={"spec": spec})
    assert r.status_code == 400


def test_render_correlation_three_blocks_nonempty_series(client):
    r = client.post("/api/pages/correlation/render", json={})
    assert r.status_code == 200
    blocks = r.json()["blocks"]
    assert len(blocks) == 3
    for b in blocks:
        assert b["kind"] == "chart"
        series = b["option"]["series"]
        assert series and all(s.get("data") for s in series)


def test_render_rejects_out_of_range_param(client):
    # window 上限 250（correlation.rolling ParamSpec），传 9999 应被 coerce 拒 → 400
    r = client.post("/api/pages/correlation/render", json={"window": 9999})
    assert r.status_code == 400


# ---- S2 盘面数据 + 涨停样本统计（内置页注册 + 渲染 + 优雅降级）----

def test_s2_builtin_pages_registered(client):
    slugs = {p["slug"] for p in client.get("/api/pages").json()}
    assert {"market", "limit-up-stats"} <= slugs


def test_render_market_blocks_shape(client, monkeypatch):
    # mock 涨停板中心 + 大盘 + 成交额榜，验证 metric/table 三 block 形状。
    from alpha import market

    def fake_pool(endpoint, date, **k):
        return {
            "getTopicZTPool": [{"lbc": 1, "hybk": "半导体"}, {"lbc": 2, "hybk": "白酒"}],
            "getTopicZBPool": [{"lbc": 1}],
            "getTopicDTPool": [],
        }.get(endpoint, [])

    monkeypatch.setattr(market.astock, "em_zt_topic_pool", fake_pool)
    monkeypatch.setattr(market.astock, "index_quote",
                        lambda: [{"name": "上证", "price": 3000, "change_pct": 1.2}])
    monkeypatch.setattr(market.astock, "market_turnover_rank",
                        lambda n=20: [{"code": "600519", "name": "茅台", "amount": 5e9,
                                       "pct": 2.1, "industry": "白酒"}])
    blocks = client.post("/api/pages/market/render", json={}).json()["blocks"]
    kinds = [b["kind"] for b in blocks]
    assert kinds == ["metric", "table", "table"]
    metric_labels = [it["label"] for it in blocks[0]["metric"]["items"]]
    assert "涨停" in metric_labels
    assert blocks[1]["table"]["rows"][0][0] == "上证"


def test_render_market_degrades_gracefully(client, monkeypatch):
    # 数据源全不可用：不 500，metric 标「暂不可用」，table 标「暂不可用」。
    from alpha import market

    monkeypatch.setattr(market.astock, "em_zt_topic_pool", lambda *a, **k: [])
    monkeypatch.setattr(market.astock, "index_quote", lambda: [])
    monkeypatch.setattr(market.astock, "market_turnover_rank", lambda n=20: [])
    r = client.post("/api/pages/market/render", json={})
    assert r.status_code == 200
    blocks = r.json()["blocks"]
    assert blocks[0]["metric"]["items"][0]["value"] == "暂不可用"
    assert blocks[1]["table"]["rows"][0][0] == "暂不可用"


def test_render_limit_up_stats(client, monkeypatch):
    from alpha import market

    monkeypatch.setattr(
        market.astock, "em_zt_topic_pool",
        lambda *a, **k: [{"lbc": 1, "hybk": "半导体"}, {"lbc": 1, "hybk": "半导体"},
                         {"lbc": 3, "hybk": "白酒"}],
    )
    blocks = client.post("/api/pages/limit-up-stats/render", json={}).json()["blocks"]
    kinds = [b["kind"] for b in blocks]
    assert kinds == ["metric", "chart", "table"]
    # 连板梯队柱状图：1板2家、3板1家
    assert blocks[1]["option"]["series"][0]["data"] == [2, 1]
    # 行业表半导体在前
    assert blocks[2]["table"]["rows"][0] == ["半导体", 2]


# ---- S4 回测页（引擎接线 + 渲染 + 降级）----

def test_backtest_page_registered(client):
    slugs = {p["slug"] for p in client.get("/api/pages").json()}
    assert "backtest" in slugs


def test_render_backtest_blocks(client):
    # client fixture 已 patch data.closes_with_dates 为确定性假数据（价格递增）。
    blocks = client.post("/api/pages/backtest/render",
                         json={"symbol": "600519", "fast": 5, "slow": 10, "range": "1y"}).json()["blocks"]
    kinds = [b["kind"] for b in blocks]
    assert kinds == ["metric", "chart", "chart"]
    # 指标卡含总收益/夏普
    labels = [it["label"] for it in blocks[0]["metric"]["items"]]
    assert "总收益" in labels and "夏普" in labels
    # 净值图有策略 + 买入持有两条线
    assert len(blocks[1]["option"]["series"]) == 2


def test_render_backtest_degrades_when_no_data(client, monkeypatch):
    from alpha import data

    monkeypatch.setattr(data, "closes_with_dates", lambda *a, **k: [])
    blocks = client.post("/api/pages/backtest/render", json={"symbol": "600519"}).json()["blocks"]
    # 不 500；指标卡标不可用
    assert blocks[0]["metric"]["items"][0]["value"] == "暂不可用"
