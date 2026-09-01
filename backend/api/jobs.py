"""Job 队列 —— 长任务不进 agent turn（T38，AGENTS 硬规则 4）。

agent 只「写代码 → 提交 job → 读结果」。回测等长任务经本队列异步执行，事件经 SSE 回推。

架构约束：MCP server 是独立子进程，不能直接碰 FastAPI 里的 JobQueue。因此 agent 的
submit_backtest 工具把「job 请求」写成 workspace/jobs/<id>.json 文件；业务层（本模块 +
session_manager 在 turn 结束时）扫描并入队。这与 artifact 的「写文件→业务层校验落库」同构。

Job 生命周期（PLAN §Job 契约）：queued → running → succeeded(run_id) | failed(error)。
成功时把净值+回撤图（alpha.chart）与指标写成 artifact（manifest），run_id 记入 job.result。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from alpha import backtest as bt
from alpha import chart
from api.store import Store


@dataclass
class JobEvent:
    id: int
    type: str  # queued | running | succeeded | failed
    data: dict[str, Any]


@dataclass
class _JobStream:
    events: list[JobEvent] = field(default_factory=list)
    subscribers: list[asyncio.Queue] = field(default_factory=list)
    _next: int = 1

    def emit(self, ev_type: str, data: dict[str, Any]) -> None:
        ev = JobEvent(id=self._next, type=ev_type, data=data)
        self._next += 1
        self.events.append(ev)
        for q in list(self.subscribers):
            q.put_nowait(ev)

    def subscribe(self, last_id: int | None = None) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        floor = last_id or 0
        for ev in self.events:
            if ev.id > floor:
                q.put_nowait(ev)
        self.subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self.subscribers:
            self.subscribers.remove(q)


class JobQueue:
    """管理 job 的提交、异步执行、状态与事件流。业务层持有。"""

    def __init__(self, store: Store, workspace_root: Path) -> None:
        self._store = store
        self._ws = Path(workspace_root)
        self._streams: dict[str, _JobStream] = {}
        self._on_complete: dict[str, Any] = {}  # jid -> callable(run_dir)
        self._completed_runs: dict[str, str] = {}  # jid -> run_dir (若先完成后注册)

    def on_complete(self, jid: str, cb) -> None:
        """注册 job 成功回调（run_dir -> None）。若 job 已完成则立即触发。"""
        run_dir = self._completed_runs.get(jid)
        if run_dir is not None:
            cb(run_dir)
        else:
            self._on_complete[jid] = cb

    def _stream(self, jid: str) -> _JobStream:
        return self._streams.setdefault(jid, _JobStream())

    def submit_backtest(
        self, params: dict[str, Any], *, session_id: str | None = None
    ) -> str:
        """登记一个回测 job（queued），后台异步执行。返回 job_id（立即）。

        params: {closes: [float], fast?: int, slow?: int, symbol?: str, dates?: [str]}。
        """
        jid = self._store.create_job(kind="backtest", params=params, session_id=session_id)
        st = self._stream(jid)
        st.emit("queued", {"job_id": jid})
        asyncio.create_task(self._run_backtest(jid, params))
        return jid

    async def _run_backtest(self, jid: str, params: dict[str, Any]) -> None:
        st = self._stream(jid)
        self._store.update_job(jid, status="running")
        st.emit("running", {"job_id": jid})
        try:
            result = await asyncio.to_thread(self._compute_and_write, jid, params)
            self._store.update_job(jid, status="succeeded", result=result)
            st.emit("succeeded", {"job_id": jid, **result})
            run_dir = result["run_dir"]
            self._completed_runs[jid] = run_dir
            cb = self._on_complete.pop(jid, None)
            if cb is not None:
                cb(run_dir)
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
            self._store.update_job(jid, status="failed", error=err)
            st.emit("failed", {"job_id": jid, "error": err})

    def _compute_and_write(self, jid: str, params: dict[str, Any]) -> dict[str, Any]:
        """跑回测 + 产净值/回撤图 artifact + manifest，返回 {run_id, metrics}。"""
        closes = [float(x) for x in params.get("closes", [])]
        if len(closes) < 2:
            raise ValueError("closes 至少 2 个点")
        fast = int(params.get("fast", 20))
        slow = int(params.get("slow", 60))
        dates = params.get("dates") or [str(i) for i in range(len(closes))]
        res = bt.backtest_golden_cross(closes, fast=fast, slow=slow, dates=dates)

        run_dir = self._ws / "runs" / f"job-{jid}"
        run_dir.mkdir(parents=True, exist_ok=True)

        equity_opt = chart.line(
            res.dates, {"净值": res.equity}, title=f"{params.get('symbol', '')} 净值曲线".strip()
        )
        dd_opt = chart.line(
            res.dates, {"回撤": res.drawdown}, title="回撤"
        )
        (run_dir / "equity.json").write_text(
            json.dumps(equity_opt, ensure_ascii=False), encoding="utf-8"
        )
        (run_dir / "drawdown.json").write_text(
            json.dumps(dd_opt, ensure_ascii=False), encoding="utf-8"
        )
        manifest = {
            "run_id": f"job-{jid}",
            "artifacts": [
                {"id": "equity", "kind": "chart", "title": "净值曲线", "path": "equity.json",
                 "inputs": {"fast": fast, "slow": slow}},
                {"id": "drawdown", "kind": "chart", "title": "回撤", "path": "drawdown.json"},
                {"id": "metrics", "kind": "metric", "title": "回测指标", "path": "metrics.json"},
            ],
        }
        (run_dir / "metrics.json").write_text(
            json.dumps(res.metrics, ensure_ascii=False), encoding="utf-8"
        )
        (run_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
        )
        return {"run_id": f"job-{jid}", "run_dir": str(run_dir), "metrics": res.metrics}

    # ---- SSE 订阅 ----
    def subscribe(self, jid: str, last_id: int | None = None) -> asyncio.Queue:
        return self._stream(jid).subscribe(last_id)

    def unsubscribe(self, jid: str, q: asyncio.Queue) -> None:
        self._stream(jid).unsubscribe(q)

    # ---- 扫描 agent 写的 job 请求文件（workspace/jobs/<id>.json）----
    def ingest_job_requests(self, workspace: str | Path, session_id: str | None = None) -> list[str]:
        """扫描 <workspace>/jobs/*.json，登记为 job 并删除请求文件。返回 job_id 列表。

        请求文件形如 {"kind":"backtest","params":{...}}。这是 MCP 子进程与业务层之间
        的解耦通道（子进程不能直接调 JobQueue）。
        """
        jobs_dir = Path(workspace) / "jobs"
        if not jobs_dir.is_dir():
            return []
        submitted: list[str] = []
        for req in sorted(jobs_dir.glob("*.json")):
            try:
                spec = json.loads(req.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                req.unlink(missing_ok=True)
                continue
            if spec.get("kind") == "backtest":
                jid = self.submit_backtest(spec.get("params", {}), session_id=session_id)
                submitted.append(jid)
            req.unlink(missing_ok=True)
        return submitted
