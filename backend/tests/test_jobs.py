"""T38 Job 队列测试 —— 提交/状态/事件流 + 失败路径 + 请求文件入队（keyless，快）。"""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from api.jobs import JobQueue
from api.store import Store

pytestmark = pytest.mark.asyncio


def _closes_uptrend(n=130):
    # 先跌后涨，确保金叉产生持仓变化
    return [100.0 - i for i in range(60)] + [40.0 + i for i in range(n - 60)]


async def test_submit_backtest_runs_and_succeeds():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(":memory:")
        jq = JobQueue(store, Path(tmp))
        jid = jq.submit_backtest({"closes": _closes_uptrend(), "fast": 20, "slow": 60})

        # 订阅事件直到 succeeded/failed
        q = jq.subscribe(jid)
        types = []
        for _ in range(20):
            try:
                ev = await asyncio.wait_for(q.get(), timeout=10)
            except asyncio.TimeoutError:
                break
            types.append(ev.type)
            if ev.type in ("succeeded", "failed"):
                break
        assert "queued" in types
        assert "running" in types
        assert "succeeded" in types, types

        job = store.get_job(jid)
        assert job["status"] == "succeeded"
        assert job["result"]["run_id"] == f"job-{jid}"
        assert "metrics" in job["result"]
        # 产出文件落盘
        run_dir = Path(job["result"]["run_dir"])
        assert (run_dir / "equity.json").exists()
        assert (run_dir / "drawdown.json").exists()
        assert (run_dir / "manifest.json").exists()
        store.close()


async def test_backtest_job_failure_path():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(":memory:")
        jq = JobQueue(store, Path(tmp))
        jid = jq.submit_backtest({"closes": [1.0]})  # <2 点 -> ValueError

        q = jq.subscribe(jid)
        last = None
        for _ in range(20):
            try:
                ev = await asyncio.wait_for(q.get(), timeout=10)
            except asyncio.TimeoutError:
                break
            last = ev
            if ev.type in ("succeeded", "failed"):
                break
        assert last is not None and last.type == "failed"
        assert store.get_job(jid)["status"] == "failed"
        assert "closes" in (store.get_job(jid)["error"] or "")
        store.close()


async def test_ingest_job_requests_from_files():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(":memory:")
        jq = JobQueue(store, Path(tmp))
        jobs_dir = Path(tmp) / "jobs"
        jobs_dir.mkdir()
        (jobs_dir / "jr-1.json").write_text(json.dumps({
            "kind": "backtest",
            "params": {"closes": _closes_uptrend(), "fast": 20, "slow": 60},
        }), encoding="utf-8")

        jids = jq.ingest_job_requests(Path(tmp))
        assert len(jids) == 1
        # 请求文件被消费
        assert list(jobs_dir.glob("*.json")) == []

        # 等 job 完成
        q = jq.subscribe(jids[0])
        for _ in range(20):
            try:
                ev = await asyncio.wait_for(q.get(), timeout=10)
            except asyncio.TimeoutError:
                break
            if ev.type in ("succeeded", "failed"):
                break
        assert store.get_job(jids[0])["status"] == "succeeded"
        store.close()


async def test_on_complete_fires_after_success():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(":memory:")
        jq = JobQueue(store, Path(tmp))
        jid = jq.submit_backtest({"closes": _closes_uptrend()})
        fired = {}
        jq.on_complete(jid, lambda run_dir: fired.update(run_dir=run_dir))

        q = jq.subscribe(jid)
        for _ in range(20):
            try:
                ev = await asyncio.wait_for(q.get(), timeout=10)
            except asyncio.TimeoutError:
                break
            if ev.type in ("succeeded", "failed"):
                break
        # 给回调一拍执行
        await asyncio.sleep(0.05)
        assert "run_dir" in fired
        assert (Path(fired["run_dir"]) / "manifest.json").exists()
        store.close()
