"""Run 软删 + 备注（B3，ROUND3）。

覆盖的**真实后果**，不是路由壳子：
  - 软删后 GET /runs 不返回，但 GET /runs/{rid} 仍 200 —— 数据还在，
    「撤销」才有可能（硬规则 14：删除必须可撤销）
  - restore 后回到列表；restore/删除不存在的 id → 404（不静默 ok）
  - note 写入后能读回；超 500 字 → 400
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


def _mk_run(client, *, note: str = "") -> str:
    # Run 无法经 REST 直接创建，用 app.state.store 直插 registry（与 test_runs_api 相同手法）
    rid: str = _store_of(client).runs.create(
        kind="backtest",
        params={"fast": 20, "slow": 60},
        code_hash="abc123",
        data_as_of="2026-10-21",
        metrics={"total_return": 0.12},
    )
    if note:
        _store_of(client).runs.set_note(rid, note)  # 共享内核：RunRepo.set_note
    return rid


def _store_of(client) -> object:
    return client.app.state.store  # type: ignore[union-attr]


# ---------- 删除 ----------

def test_delete_run_returns_shape_and_hides_from_list(client):
    rid = _mk_run(client)
    assert len(client.get("/api/runs").json()) == 1

    r = client.delete(f"/api/runs/{rid}")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "id": rid, "soft": True}

    # 列表里不再出现 —— 这就是「删除」在用户眼里唯一可见的效果
    assert client.get("/api/runs").json() == []


def test_soft_deleted_run_detail_still_200(client):
    """软删 ≠ 数据没了：详情仍可读（撤销的前提是「它还找得到」）。"""
    rid = _mk_run(client)
    client.delete(f"/api/runs/{rid}")
    detail = client.get(f"/api/runs/{rid}")
    assert detail.status_code == 200
    assert detail.json()["id"] == rid


def test_delete_missing_run_is_404(client):
    assert client.delete("/api/runs/run-nope").status_code == 404


# ---------- 撤销 ----------

def test_restore_puts_run_back_into_list(client):
    rid = _mk_run(client)
    client.delete(f"/api/runs/{rid}")

    r = client.post(f"/api/runs/{rid}/restore")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "id": rid}

    rows = client.get("/api/runs").json()
    assert [row["id"] for row in rows] == [rid]


def test_restore_missing_run_is_404(client):
    assert client.post("/api/runs/run-nope/restore").status_code == 404


# ---------- 备注 ----------

def test_set_note_persists_and_reads_back(client):
    rid = _mk_run(client)
    r = client.post(f"/api/runs/{rid}/note", json={"note": "想验证 fast=20 是否过拟合"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    detail = client.get(f"/api/runs/{rid}").json()
    assert detail["note"] == "想验证 fast=20 是否过拟合"

    # 列表也要带出备注（前端备注列的数据来源）
    rows = client.get("/api/runs?kind=backtest").json()
    assert rows[0]["note"] == "想验证 fast=20 是否过拟合"


def test_set_note_too_long_is_400(client):
    rid = _mk_run(client)
    r = client.post(f"/api/runs/{rid}/note", json={"note": "x" * 501})
    assert r.status_code == 400
    # 原值不被污染
    assert client.get(f"/api/runs/{rid}").json()["note"] == ""


def test_set_note_on_missing_run_is_404(client):
    r = client.post("/api/runs/run-nope/note", json={"note": "hi"})
    assert r.status_code == 404


def test_set_note_overwrites_previous(client):
    rid = _mk_run(client, note="旧备注")
    client.post(f"/api/runs/{rid}/note", json={"note": "新备注"})
    assert client.get(f"/api/runs/{rid}").json()["note"] == "新备注"
