"""M3-1 Run registry REST API 测试。

覆盖两层：
  1-7：API 壳子（runs / views 的 CRUD + diff + 404）；
  8：**回测任务真能产出 Run** —— 这是本任务的核心断言。前 7 条只证明路由通、
     契约对；第 8 条证明「跑一次回测，留档就发生了」，
     即「可复现、可比较」不是纸上谈兵。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.jobs import JobQueue
from api.store import Store


@pytest.fixture
def client(tmp_path):
    app = create_app(db_path=str(tmp_path / "t.db"), workspace_root=tmp_path)
    with TestClient(app) as c:
        yield c


# ---------- 1/2：列表与详情 ----------

def test_runs_list_and_detail(client):
    r1 = _mk_run(client)
    r2 = _mk_run(client, kind="backtest", data_as_of="2026-10-22")
    rows = client.get("/api/runs").json()
    assert len(rows) == 2
    assert {r["id"] for r in rows} == {r1, r2}
    # 过滤
    rows_f = client.get("/api/runs?kind=backtest&data_as_of=2026-10-22").json()
    assert len(rows_f) == 1 and rows_f[0]["id"] == r2
    detail = client.get(f"/api/runs/{r1}").json()
    assert detail["id"] == r1 and detail["metrics"]["total_return"] == 0.12


def test_run_detail_404(client):
    assert client.get("/api/runs/run-nope").status_code == 404


# ---------- 3/4：diff ----------

def test_run_diff_returns_delta(client):
    a = _mk_run(client, fast=20)
    b = _mk_run(client, fast=60, total=0.25)
    r = client.get(f"/api/runs/diff?a={a}&b={b}").json()
    assert r["a"] == a and r["b"] == b
    assert r["params"]["fast"] == {"a": 20, "b": 60}
    m = r["metrics"]["total_return"]
    assert m["a"] == 0.12 and m["b"] == 0.25
    assert m["delta"] == pytest.approx(0.13)


def test_run_diff_one_sided_metric_delta_is_none(client):
    """只有一侧有的指标：delta 必须是 None（约定：不是 0，避免误读「没变化」）。"""
    a = _mk_run(client)
    b = _mk_run(client, extra_metric={"sharpe": 1.5})
    r = client.get(f"/api/runs/diff?a={a}&b={b}").json()
    assert r["metrics"]["sharpe"]["a"] is None
    assert r["metrics"]["sharpe"]["delta"] is None


@pytest.mark.parametrize("missing", ["a", "b"])
def test_run_diff_missing_side_404(client, missing):
    a = _mk_run(client)
    ok, other = ("run-nope", a) if missing == "a" else (a, "run-nope")
    assert client.get(f"/api/runs/diff?a={ok}&b={other}").status_code == 404


# ---------- 5/6/7：View ----------

def test_view_create_and_list(client):
    vid = client.post("/api/views", json={
        "name": "茅台金叉", "kind": "backtest", "params": {"symbol": "600519"},
    }).json()["id"]
    rows = client.get("/api/views").json()
    assert [v["id"] for v in rows] == [vid]
    assert rows[0]["name"] == "茅台金叉" and rows[0]["pinned"] is False


def test_view_pin_unpin(client):
    vid = client.post("/api/views", json={"name": "v", "kind": "backtest"}).json()["id"]
    assert client.get("/api/views/pinned").json() == []
    client.post(f"/api/views/{vid}/pin", json={"pinned": True})
    assert [v["id"] for v in client.get("/api/views/pinned").json()] == [vid]
    client.post(f"/api/views/{vid}/pin", json={"pinned": False})
    assert client.get("/api/views/pinned").json() == []


def test_view_delete(client):
    vid = client.post("/api/views", json={"name": "v", "kind": "backtest"}).json()["id"]
    assert client.delete(f"/api/views/{vid}").status_code == 200
    assert client.get("/api/views").json() == []


# ---------- 8：回测任务产出 Run（核心） ----------

def _closes_uptrend(n=130):
    return [100.0 - i for i in range(60)] + [40.0 + i for i in range(n - 60)]


def test_backtest_job_produces_run_in_registry(tmp_path):
    """跑一次回测 job，Run registry 里必须有留档：params 真实入参、metrics 非空、
    code_hash 非空、artifact_ids 指向 manifest 的 artifact。"""
    with asyncio.Runner() as runner:
        runner.run(_backtest_job_asserts(tmp_path))


async def _backtest_job_asserts(tmp_path: Path):
    store = Store(":memory:")
    jq = JobQueue(store, tmp_path)
    jid = jq.submit_backtest({"closes": _closes_uptrend(), "fast": 20, "slow": 60})
    q = jq.subscribe(jid)
    for _ in range(30):
        ev = await asyncio.wait_for(q.get(), timeout=10)
        if ev.type in ("succeeded", "failed"):
            break
    job = store.get_job(jid)
    assert job["status"] == "succeeded", job

    runs = store.runs.list_recent(kind="backtest")
    assert len(runs) == 1
    r = runs[0]
    assert r["id"] == job["result"]["registry_run_id"]
    assert r["metrics"], "metrics 必须非空"
    assert r["code_hash"], "code_hash 必须非空（同一策略代码的判据）"
    assert r["params"]["fast"] == 20 and r["params"]["slow"] == 60
    # 这条用例用的是「只有收盘价、没有交易日历」的合成输入。
    # 此时 data_as_of 的正确值是**空串**（界面显示「时点未知」），
    # 而不是把索引 "119" 当日期写进去 —— 那会让界面上显示一个假的时间点，
    # 比不显示更危险。所以断言的真正不变量是：**绝不能是纯数字索引**。
    assert not r["data_as_of"].isdigit(), (
        f"data_as_of 不能是索引占位：{r['data_as_of']!r}（应留空表示时点未知）"
    )
    assert set(r["artifact_ids"]) == {"equity", "drawdown", "metrics"}
    assert job["result"]["run_id"] == f"job-{jid}"
    store.close()


# ---------- helpers ----------

def _mk_run(client, *, kind="backtest", data_as_of="2026-10-21", fast=20,
            total=0.12, extra_metric=None):
    metrics = {"total_return": total}
    metrics.update(extra_metric or {})
    # Run 经 REST API 无法直接制造（Run 只能由回测 job 或 registry 产生），
    # 所以测试用 create_app 共享的那个 store 直插 registry。
    store: Store = _store_of(client)
    rid = store.runs.create(
        kind=kind,
        params={"fast": fast, "slow": 60},
        code_hash="abc123",
        data_as_of=data_as_of,
        metrics=metrics,
        artifact_ids=["equity"],
    )
    return rid


def _store_of(client) -> Store:
    return client.app.state.store  # type: ignore[union-attr]


def test_run_records_real_dates_when_provided(tmp_path):
    """传了真实交易日历时，data_as_of 必须记录真日期。

    与上一条互补：上一条守「没有日期就别编」，这条守「有日期就得记」。
    只有两条一起，才能保证「空串」表示的是真的不知道，而不是懒得记。
    """
    async def _run():
        store = Store(":memory:")
        jq = JobQueue(store, tmp_path)
        dates = [f"2026-10-0{i}" for i in range(1, 6)]
        jid = jq.submit_backtest({
            "closes": _closes_uptrend()[:5], "fast": 2, "slow": 3,
            "dates": dates,
        })
        q = jq.subscribe(jid)
        for _ in range(30):
            ev = await asyncio.wait_for(q.get(), timeout=10)
            if ev.type in ("succeeded", "failed"):
                break
        runs = store.runs.list_recent(kind="backtest")
        assert runs, "应有一条 Run"
        assert runs[0]["data_as_of"] == "2026-10-05"
        store.close()

    with asyncio.Runner() as runner:
        runner.run(_run())


def test_run_inputs_allow_rerun(tmp_path):
    """M3-4 Rerun：Run 里必须存**足以重跑**的输入快照。

    只存 {fast, slow, symbol} 是不够的 —— 重跑要重新喂 closes，
    而 closes 是调用方给的（可能来自某个历史时点的取数）。
    没有它就只能说「可比较」，不能说「可重跑」。
    """
    async def _go():
        store = Store(":memory:")
        jq = JobQueue(store, tmp_path)
        closes = [10.0 + i for i in range(10)]
        jid = jq.submit_backtest({"closes": closes, "fast": 2, "slow": 3})
        q = jq.subscribe(jid)
        for _ in range(30):
            ev = await asyncio.wait_for(q.get(), timeout=10)
            if ev.type in ("succeeded", "failed"):
                break
        runs = store.runs.list_recent(kind="backtest")
        assert runs
        inputs = runs[0]["inputs"]
        assert inputs["closes"] == closes, "必须存全部 closes，否则无法重跑"
        assert inputs["fast"] == 2 and inputs["slow"] == 3
        store.close()

    with asyncio.Runner() as runner:
        runner.run(_go())


class TestRerun:
    """M3-4「可重跑」：用同一个输入快照再跑一次。"""

    def _client(self, tmp_path, *, with_submit: bool = True):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.runs import build_runs_router

        app = FastAPI()
        store = Store(":memory:")
        submitted: list[dict] = []

        def fake_submit(params: dict) -> str:
            submitted.append(params)
            return "job-fake"

        app.include_router(build_runs_router(
            store, submit_backtest=fake_submit if with_submit else None,
        ))
        return TestClient(app), store, submitted

    def test_rerun_submits_same_inputs(self, tmp_path):
        client, store, submitted = self._client(tmp_path)
        rid = store.runs.create(
            kind="backtest", params={"fast": 2, "slow": 3},
            inputs={"closes": [1.0, 2.0, 3.0], "fast": 2, "slow": 3},
            data_as_of="2026-10-21",
        )
        r = client.post(f"/api/runs/{rid}/rerun")
        assert r.status_code == 200
        body = r.json()
        assert body["rerun_of"] == rid
        assert submitted == [{"closes": [1.0, 2.0, 3.0], "fast": 2, "slow": 3}]

    def test_rerun_without_inputs_is_409_not_silent_ok(self, tmp_path):
        """老 Run（没有输入快照）不能假装重跑成功。"""
        client, store, _ = self._client(tmp_path)
        rid = store.runs.create(kind="backtest", params={}, data_as_of="2026-10-21")
        r = client.post(f"/api/runs/{rid}/rerun")
        assert r.status_code == 409

    def test_rerun_missing_run_is_404(self, tmp_path):
        client, _, _ = self._client(tmp_path)
        assert client.post("/api/runs/nope/rerun").status_code == 404

    def test_rerun_without_job_queue_is_501(self, tmp_path):
        """没注入 job 队列时明确 501，而不是 200 然后什么也没发生。"""
        client, store, _ = self._client(tmp_path, with_submit=False)
        rid = store.runs.create(
            kind="backtest", params={}, inputs={"closes": [1.0, 2.0]},
            data_as_of="2026-10-21",
        )
        assert client.post(f"/api/runs/{rid}/rerun").status_code == 501
