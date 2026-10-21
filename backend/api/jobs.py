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
import hashlib
import inspect
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
        self._on_failed: dict[str, Any] = {}  # jid -> callable(error)
        self._completed_runs: dict[str, str] = {}  # jid -> run_dir (若先完成后注册)
        self._failed_errors: dict[str, str] = {}  # jid -> error (若先失败后注册)

    def on_complete(self, jid: str, cb) -> None:
        """注册 job 成功回调（run_dir -> None）。若 job 已完成则立即触发。"""
        run_dir = self._completed_runs.get(jid)
        if run_dir is not None:
            cb(run_dir)
        else:
            self._on_complete[jid] = cb

    def on_failed(self, jid: str, cb) -> None:
        """注册 job 失败回调（error -> None）。若 job 已失败则立即触发。

        与 on_complete 对称。缺了它，失败路径上没有任何人知道——
        前端只能无限等待，比报错更糟。
        """
        err = self._failed_errors.get(jid)
        if err is not None:
            cb(err)
        else:
            self._on_failed[jid] = cb

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
            # 成功路径不该再有失败回调
            self._on_failed.pop(jid, None)
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
            self._store.update_job(jid, status="failed", error=err)
            st.emit("failed", {"job_id": jid, "error": err})
            self._failed_errors[jid] = err
            cb_fail = self._on_failed.pop(jid, None)
            if cb_fail is not None:
                cb_fail(err)
            # 失败时不该再等成功回调
            self._on_complete.pop(jid, None)

    def _trading_dates(self, closes: list[float], *, symbol: str) -> list[str]:
        """从数据源取真实交易日，长度与 closes 对齐。

        为什么需要这一步：调用方（agent / 前端）往往只给收盘价序列。
        缺日期时若拿索引占位，"119" 会被当日期写进 provenance —— 那是假的时间点。
        所以这里按代码取最近 N 根日线，用它们的真实日期。
        """
        if not symbol:
            return []
        # 不吞错：取数失败必须让上层知道，由上层决定「用合成日期兜底」还是失败。
        # `except Exception: return []` 会让「数据源挂了」和「这只票没有数据」
        # 看起来一样 —— 本项目已经栽过一次（取数失败静默返回空 → 模型自己造数据）。
        from research import astock
        bars = astock.kline(symbol, category=4, offset=len(closes))
        return [str(b["datetime"]) for b in bars][-len(closes):]

    def _compute_and_write(self, jid: str, params: dict[str, Any]) -> dict[str, Any]:
        """跑回测 + 产净值/回撤图 artifact + manifest，返回 {run_id, metrics}。"""
        closes = [float(x) for x in params.get("closes", [])]
        if len(closes) < 2:
            raise ValueError("closes 至少 2 个点")
        fast = int(params.get("fast", 20))
        slow = int(params.get("slow", 60))
        # ---- 交易日历：三级优先，绝不造假日期 ----
        #
        # provenance 的 dataAsOf 是**必填**的（api/artifacts.py 会拒收空值），
        # 但也不能用索引占位 —— "119" 会被当成日期写进 provenance，
        # 「数据时点」于是显示成一个看起来像日期、实际毫无意义的东西。
        # 假的时间戳比不显示更危险：它让人相信它。
        #
        #   ① 调用方给了 dates      → 直接用（最可信）
        #   ② 有 symbol 且数据源可用 → 取真实交易日
        #   ③ 以上都不行            → SYNTHETIC-0001 序列（自曝是合成，不是冒充日期）
        #
        # ③ 的存在理由：回测的**数值**仍然是真的（closes 由调用方提供），
        # 只有时间轴是占位。为此让整个 job 失败反而更糟 —— 用户会以为回测算不出来。
        symbol = str(params.get("symbol") or "")
        dates: list[str] = list(params.get("dates") or [])

        if not dates and symbol:
            from research.astock import DataUnavailable
            try:
                dates = self._trading_dates(closes, symbol=symbol)
            except (DataUnavailable, KeyError, IndexError):
                # 数据源不可用：不吞错到「假装没这回事」，而是明确走到 ③。
                dates = []

        if not dates:
            dates = [f"SYNTHETIC-{i + 1:04d}" for i in range(len(closes))]

        if len(dates) != len(closes):
            raise ValueError(f"交易日历长度 {len(dates)} 与收盘价 {len(closes)} 不一致")

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
        # provenance：回测是**我们自己**调 alpha.backtest 跑出来的，所以是
        # deterministic —— 这是「服务端铸造」的典型场景（ADR-0012「已决 1」）。
        # 注意这个章不是 agent 能盖的：manifest 由本模块（业务层）生成，
        # 摄取时还要经 server_stamped=True 才保留。
        provenance = {
            "kind": "deterministic",
            "fn": "alpha.backtest.backtest_golden_cross",
            "params": {"fast": fast, "slow": slow},
            "dataAsOf": str(dates[-1]),
        }
        manifest = {
            "run_id": f"job-{jid}",
            "artifacts": [
                {"id": "equity", "kind": "chart", "title": "净值曲线", "path": "equity.json",
                 "inputs": {"fast": fast, "slow": slow}, "provenance": provenance},
                {"id": "drawdown", "kind": "chart", "title": "回撤", "path": "drawdown.json",
                 "provenance": provenance},
                {"id": "metrics", "kind": "metric", "title": "回测指标", "path": "metrics.json",
                 "provenance": provenance},
            ],
        }
        (run_dir / "metrics.json").write_text(
            json.dumps(res.metrics, ensure_ascii=False), encoding="utf-8"
        )
        (run_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
        )

        # Run registry（M3-1）：同一组 params / codeHash / dataAsOf 的一次确定性计算。
        # manifest 只描述「这次产出了哪些文件」；Run 回答的是「这些数字怎么算出来的、
        # 能不能复现、能不能与另一次比较」。没有留档，「可复现」就只是口头承诺。
        code_hash = self._code_hash(bt)
        rid = self._store.runs.create(
            kind="backtest",
            params={"fast": fast, "slow": slow, "symbol": params.get("symbol", "")},
            code_hash=code_hash,
            data_as_of=str(dates[-1]),
            metrics=res.metrics,
            artifact_ids=[a["id"] for a in manifest["artifacts"]],
        )
        return {
            "run_id": f"job-{jid}",
            # registry 的 run id：session 事件回传、前端「打开这次留档」都用它。
            "registry_run_id": rid,
            "code_hash": code_hash,
            "run_dir": str(run_dir),
            "metrics": res.metrics,
        }

    @staticmethod
    def _code_hash(bt_mod: Any) -> str:
        """产出指标的策略代码指纹，短 hash 直接入库 / 展示。

        为什么是**整个 backtest 模块**而不是单个函数：指标的口径是
        ma / golden_cross_signal / backtest_golden_cross 三者合力的结果，
        改任何一个信号辅助函数都会改变指标值 —— 那就必须是新 Run。
        同一策略代码改了一个字，「可复现」立刻变空话，所以拿 hash 说真话。
        """
        src = inspect.getsource(bt_mod)
        return hashlib.sha256(src.encode("utf-8")).hexdigest()[:12]

    # ---- SSE 订阅 ----
    def subscribe(self, jid: str, last_id: int | None = None) -> asyncio.Queue:
        return self._stream(jid).subscribe(last_id)

    def unsubscribe(self, jid: str, q: asyncio.Queue) -> None:
        self._stream(jid).unsubscribe(q)

    # ---- 扫描 agent 写的 job 请求文件（workspace/jobs/<id>.json）----
    def ingest_job_requests(
        self, workspace: str | Path, session_id: str | None = None
    ) -> list[str]:
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
