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
