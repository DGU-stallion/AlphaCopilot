"""T45 展示页 REST + 渲染端点测试 —— 不联网（monkeypatch 假数据源）。

覆盖：
  · GET /api/pages          内置页已 upsert（correlation + backtest）
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
    assert {"correlation", "backtest"} <= slugs


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


# ---- 回测多策略可插拔骨架 ----

def test_strategies_registry_has_dual_ma():
    """STRATEGIES 注册表含默认双均线金叉，且每条含 label/desc/signal_fn。"""
    from alpha import backtest_page as bp

    assert "dual_ma" in bp.STRATEGIES
    entry = bp.STRATEGIES["dual_ma"]
    assert entry["label"] == "双均线金叉"
    assert callable(entry["signal_fn"])


def test_run_dispatches_by_strategy_name(monkeypatch):
    """_run 按 strategy 名分发到对应 signal_fn；未知策略名降级为不支持提示。"""
    from alpha import backtest_page as bp

    called = {}

    def fake_signal(closes, fast, slow):
        called["hit"] = (fast, slow)
        return [0] * len(closes)

    monkeypatch.setitem(bp.STRATEGIES, "dual_ma",
                        {"label": "双均线金叉", "desc": "", "signal_fn": fake_signal})
    monkeypatch.setattr(bp, "_load", lambda symbol, range: (["d1", "d2", "d3"], [10.0, 11.0, 12.0]))
    monkeypatch.setattr(bp.be, "gate", lambda *a, **k: None)
    monkeypatch.setattr(bp.be, "run", lambda *a, **k: object())

    _res, reason = bp._run("600519", 5, 10, "1y", "dual_ma")
    assert reason is None
    assert called["hit"] == (5, 10)  # 分发到了 dual_ma 的 signal_fn

    # 未知策略名：不取数、直接降级
    res2, reason2 = bp._run("600519", 5, 10, "1y", "not_a_strategy")
    assert res2 is None and "不支持" in reason2
