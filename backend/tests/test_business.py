"""S3 业务页 CRUD 测试 —— 股票池 / 交易日志 / 我的研报。落 SQLite 真源，重启不丢。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.store import Store


@pytest.fixture
def client(tmp_path):
    app = create_app(db_path=str(tmp_path / "t.db"), workspace_root=tmp_path)
    with TestClient(app) as c:
        yield c


# ---------- 股票池 ----------

def test_stock_pool_crud(client):
    assert client.get("/api/stock-pool").json() == []
    r = client.post("/api/stock-pool", json={"code": "600519", "name": "贵州茅台", "tags": "白酒"})
    assert r.status_code == 200
    pool = client.get("/api/stock-pool").json()
    assert len(pool) == 1 and pool[0]["code"] == "600519"
    # 移除
    assert client.delete("/api/stock-pool/600519").status_code == 200
    assert client.get("/api/stock-pool").json() == []


def test_stock_pool_rejects_bad_code(client):
    assert client.post("/api/stock-pool", json={"code": "ABC"}).status_code == 400


def test_stock_pool_upsert_dedupes_by_code(client):
    client.post("/api/stock-pool", json={"code": "000858", "name": "五粮液"})
    client.post("/api/stock-pool", json={"code": "000858", "name": "五粮液", "note": "加仓"})
    pool = client.get("/api/stock-pool").json()
    assert len(pool) == 1 and pool[0]["note"] == "加仓"


def test_stock_pool_delete_404(client):
    assert client.delete("/api/stock-pool/600519").status_code == 404


# ---------- 交易日志 ----------

def test_journal_crud(client):
    r = client.post("/api/journal", json={
        "code": "600519", "name": "贵州茅台", "side": "buy",
        "price": 1500.0, "shares": 100, "fee": 5.0, "traded_at": "2025-01-02",
        "note": "建仓",
    })
    assert r.status_code == 200
    jid = r.json()["id"]
    rows = client.get("/api/journal").json()
    assert len(rows) == 1 and rows[0]["side"] == "buy" and rows[0]["shares"] == 100
    assert client.delete(f"/api/journal/{jid}").status_code == 200
    assert client.get("/api/journal").json() == []


def test_journal_rejects_bad_side(client):
    r = client.post("/api/journal", json={"side": "hold", "price": 1, "shares": 1})
    assert r.status_code == 400


def test_journal_import_batch(client):
    rows = [
        {"code": "600519", "name": "茅台", "side": "buy", "price": 1500, "shares": 100,
         "traded_at": "2025-01-02"},
        {"code": "000858", "name": "五粮液", "side": "sell", "price": 160, "shares": 200,
         "traded_at": "2025-01-03"},
    ]
    r = client.post("/api/journal/import", json={"rows": rows})
    assert r.status_code == 200 and r.json()["imported"] == 2
    assert len(client.get("/api/journal").json()) == 2


def test_journal_import_rejects_whole_batch_on_bad_row(client):
    rows = [
        {"code": "600519", "side": "buy", "price": 1500, "shares": 100},
        {"code": "000858", "side": "invalid", "price": 160, "shares": 200},
    ]
    r = client.post("/api/journal/import", json={"rows": rows})
    assert r.status_code == 400
    # 整批拒绝，不部分写入
    assert client.get("/api/journal").json() == []


# ---------- 我的研报 ----------

def test_reports_crud(client):
    r = client.post("/api/reports", json={"title": "白酒行业2025年报对比", "text": "结论..."})
    assert r.status_code == 200
    reports = client.get("/api/reports").json()
    assert len(reports) == 1 and reports[0]["title"] == "白酒行业2025年报对比"


def test_reports_rejects_empty_title(client):
    assert client.post("/api/reports", json={"title": "  "}).status_code == 400


# ---------- 持久化：重启后不丢 ----------

def test_persistence_across_reopen(tmp_path):
    db = str(tmp_path / "persist.db")
    s1 = Store(db)
    s1.stock_pool.add("600519", "贵州茅台")
    s1.journal.add(code="600519", name="茅台", side="buy", price=1500, shares=100)
    s1.close()
    s2 = Store(db)
    assert len(s2.stock_pool.list()) == 1
    assert len(s2.journal.list()) == 1
    s2.close()
