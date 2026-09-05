"""S4 模拟组合 —— 净值纯计算 fixture + CRUD 测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alpha import portfolio as pf
from api.app import create_app


# ---- 纯计算 fixture ----

def test_compute_nav_single_stock_full_weight():
    # 100% 持一只票，价格翻倍 → 净值翻倍
    events = [{"effective_on": "2025-01-01", "weights": {"600519": 1.0}}]
    prices = {"600519": {"2025-01-01": 100.0, "2025-01-02": 150.0, "2025-01-03": 200.0}}
    dates, nav = pf.compute_nav(events, prices)
    assert dates == ["2025-01-01", "2025-01-02", "2025-01-03"]
    assert nav[0] == 1.0
    assert nav[-1] == pytest.approx(2.0)


def test_compute_nav_half_cash_dampens_move():
    # 50% 一只票 + 50% 现金，价格翻倍 → 净值 1.5（现金不动）
    events = [{"effective_on": "2025-01-01", "weights": {"600519": 0.5}}]
    prices = {"600519": {"2025-01-01": 100.0, "2025-01-02": 200.0}}
    _dates, nav = pf.compute_nav(events, prices)
    assert nav[-1] == pytest.approx(1.5)


def test_compute_nav_empty_events():
    assert pf.compute_nav([], {}) == ([], [])


def test_compute_benchmark_nav_normalizes_to_1():
    dates = ["2025-01-01", "2025-01-02"]
    bench = pf.compute_benchmark_nav(dates, {"2025-01-01": 4000.0, "2025-01-02": 4400.0})
    assert bench[0] == 1.0
    assert bench[-1] == pytest.approx(1.1)


# ---- CRUD + NAV endpoint ----

@pytest.fixture
def client(tmp_path, monkeypatch):
    from alpha import data

    def fake_cwd(code, period=data.DAY, count=250):
        base = 100.0 + int(code[-2:])
        return [(f"2025-01-{i + 1:02d}", base * (1 + 0.01 * i)) for i in range(20)]

    monkeypatch.setattr(data, "closes_with_dates", fake_cwd)
    app = create_app(db_path=str(tmp_path / "t.db"), workspace_root=tmp_path)
    with TestClient(app) as c:
        yield c


def test_portfolio_crud_and_rebalance(client):
    pid = client.post("/api/portfolios", json={"name": "白酒组合"}).json()["id"]
    assert len(client.get("/api/portfolios").json()) == 1
    # 加调仓事件
    r = client.post(f"/api/portfolios/{pid}/rebalance",
                    json={"effective_on": "2025-01-01", "weights": {"600519": 0.6, "000858": 0.4}})
    assert r.status_code == 200
    pfs = client.get("/api/portfolios").json()
    assert len(pfs[0]["rebalances"]) == 1


def test_rebalance_rejects_weight_over_1(client):
    pid = client.post("/api/portfolios", json={"name": "x"}).json()["id"]
    r = client.post(f"/api/portfolios/{pid}/rebalance",
                    json={"effective_on": "2025-01-01", "weights": {"600519": 0.7, "000858": 0.5}})
    assert r.status_code == 400


def test_portfolio_nav_renders_series(client):
    pid = client.post("/api/portfolios", json={"name": "组合"}).json()["id"]
    client.post(f"/api/portfolios/{pid}/rebalance",
                json={"effective_on": "2025-01-01", "weights": {"600519": 1.0}})
    opt = client.get(f"/api/portfolios/{pid}/nav").json()["option"]
    assert "series" in opt
    assert any(s.get("data") for s in opt["series"])


def test_portfolio_delete(client):
    pid = client.post("/api/portfolios", json={"name": "del"}).json()["id"]
    assert client.delete(f"/api/portfolios/{pid}").status_code == 200
    assert client.get("/api/portfolios").json() == []
