"""E2E-2 回测 job 场景 —— job 队列 → artifact 挂载链路（无网络、无模型、无凭据）。

## 这条测试在验什么

验的是**异步 job 这一段**：agent 写一个 `workspace/jobs/<id>.json` 请求文件，
turn 结束时 `ingest_job_requests` 把它登记入队，JobQueue 异步跑 `alpha.backtest`，
产出净值/回撤/指标 artifact，`on_complete` 摄取并挂到那条 assistant 消息上。

这条链路跨了四个组件（文件通道 → JobQueue → 回测引擎 → artifact 摄取），
任何一环断掉都不会崩，只会让界面上永远等不到图。所以要端到端钉住。

## v1 → v2 的测法变化

v1 用 mock OpenAI 端点让「模型」返回 `submit_backtest` 的 tool_call。
Pi 之后我们拦不到模型请求，改为注入假 provider：它**直接写那个请求文件**
（也就是 `submit_backtest` 工具本该做的事），然后吐结论。

省掉的是「模型是否愿意调工具」；保留的是请求文件格式、入队、执行、摄取、
挂载、事件——全是我们自己会写错的确定性逻辑。
"""

from __future__ import annotations

import asyncio
import json
import socket
import tempfile
from pathlib import Path

import httpx
import uvicorn

from agent.provider import AgentEvent
from api.app import create_app

# 合成收盘价：先跌 60 天再涨 70 天 → 必然产生 20/60 金叉与持仓变化。
_CLOSES = [100.0 - i for i in range(60)] + [40.0 + i * 1.5 for i in range(70)]
_CONCLUSION = (
    "已提交 20/60 金叉回测 job。完成后将展示净值与回撤。"
    "以上为客观回测，不构成投资建议。"
)


class _JobSubmittingProvider:
    """假 provider：写 job 请求文件（等价于 submit_backtest 工具的行为），然后吐结论。"""

    def __init__(self, workspace: Path, conclusion: str) -> None:
        self._workspace = workspace
        self._conclusion = conclusion
        self._closed = False

    def start(self) -> None:
        return

    def abort(self, reason: str = "") -> None:
        return

    def close(self) -> None:
        self._closed = True

    def is_alive(self) -> bool:
        return not self._closed

    async def astream(self, prompt: str):
        from agent.provider import EVENT_TEXT_DELTA, EVENT_TURN_END

        # 复刻 mcpserver/tools/submit_backtest.py 的落盘协议：
        # {"kind": "backtest", "params": {...}} 写到 workspace/jobs/<id>.json
        jobs_dir = self._workspace / "jobs"
        jobs_dir.mkdir(parents=True, exist_ok=True)
        spec = {
            "kind": "backtest",
            "params": {
                "closes": _CLOSES,
                "fast": 20,
                "slow": 60,
                "symbol": "茅台",
            },
        }
        (jobs_dir / "e2e2.json").write_text(
            json.dumps(spec, ensure_ascii=False), encoding="utf-8"
        )

        for ch in self._conclusion:
            yield AgentEvent(kind=EVENT_TEXT_DELTA, payload={"text": ch})
        yield AgentEvent(
            kind=EVENT_TURN_END,
            payload={"final_text": self._conclusion, "finish_reason": "stop"},
        )


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def test_e2e2_backtest_job_attaches_equity_drawdown_metric():
    """端到端：agent 交 job → 异步执行 → 净值/回撤/指标三件 artifact 挂到消息。"""
    with tempfile.TemporaryDirectory(prefix="e2e2-") as tmp:

        def factory(session_id: str):
            ws = Path(tmp) / session_id / "ws"
            ws.mkdir(parents=True, exist_ok=True)
            return _JobSubmittingProvider(ws, _CONCLUSION), ws

        app = create_app(
            db_path=":memory:", workspace_root=Path(tmp), provider_factory=factory
        )
        port = _free_port()
        srv = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
        )
        task = asyncio.create_task(srv.serve())
        for _ in range(100):
            if srv.started:
                break
            await asyncio.sleep(0.05)

        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}", trust_env=False
        ) as client:
            sid = (await client.post("/api/sessions")).json()["session_id"]
            await client.post(
                f"/api/sessions/{sid}/messages",
                json={"content": "用 20/60 金叉在茅台回测近三年，画净值和回撤"},
            )

            # job 是异步的：轮询等 artifact 挂满（净值 + 回撤 + 指标）
            async def wait_artifacts():
                for _ in range(240):
                    msgs = (await client.get(f"/api/sessions/{sid}/messages")).json()
                    asst = [m for m in msgs if m["role"] == "assistant"]
                    if asst and len(asst[-1].get("artifacts", [])) >= 3:
                        return asst[-1]
                    await asyncio.sleep(0.5)
                return None

            assistant = await asyncio.wait_for(wait_artifacts(), timeout=120)
            assert assistant is not None, "job artifact 未在超时内挂到消息"

            arts = assistant["artifacts"]
            kinds = [a["kind"] for a in arts]
            titles = [a["title"] for a in arts]

            assert kinds.count("chart") >= 2, f"净值+回撤两个 chart 缺失：{kinds}"
            assert "metric" in kinds, f"指标卡缺失：{kinds}"
            assert any("净值" in t for t in titles), f"没有净值图：{titles}"
            assert any("回撤" in t for t in titles), f"没有回撤图：{titles}"

            equity = next(
                a for a in arts if a["kind"] == "chart" and "净值" in a["title"]
            )
            assert equity["payload"]["series"][0]["type"] == "line"

            # job 产物是 deterministic —— 回测数字由我们自己调 alpha.backtest 算，
            # 不是 agent 编的，所以应当带确定性章（ADR-0012「已决 1」的服务端铸造路径）
            prov = json.loads(arts[0]["provenance"])
            assert prov["kind"] == "deterministic", (
                f"job 产出的回测数字应为 deterministic；实际 {prov}"
            )
            assert prov["fn"] == "alpha.backtest.backtest_golden_cross"
            assert prov.get("dataAsOf"), "deterministic 必须带 dataAsOf（数据截止时点）"

            # job 在 store 里确实是 succeeded（不是「恰好有 artifact 但 job 失败」）
            jobs_rows = app.state.store.conn.execute(
                "SELECT status, result FROM job"
            ).fetchall()
            assert any(r["status"] == "succeeded" for r in jobs_rows), [
                dict(r) for r in jobs_rows
            ]

        srv.should_exit = True
        await task
        app.state.manager.close_all()


async def test_job_request_file_format_matches_ingest_contract(tmp_path):
    """单元：请求文件的格式必须与 `ingest_job_requests` 的期望一致。

    单独一条的理由：上面那条 E2E 失败时，分不清是「文件格式不对」还是
    「队列/引擎/摄取有问题」。这条把格式契约单独钉住 —— 它是最容易在
    重构 `submit_backtest` 工具时被悄悄改坏的地方，而且改坏后 job 会静默不执行。
    """
    from api.jobs import JobQueue
    from api.store import Store

    store = Store(":memory:")
    queue = JobQueue(store, tmp_path)
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    (jobs_dir / "j1.json").write_text(
        json.dumps(
            {"kind": "backtest", "params": {"closes": _CLOSES, "fast": 20, "slow": 60}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    submitted = queue.ingest_job_requests(tmp_path)

    assert len(submitted) == 1, f"请求文件没被登记为 job：{submitted}"
    assert not (jobs_dir / "j1.json").exists(), "请求文件应在登记后删除（否则会重复入队）"
    store.close()
