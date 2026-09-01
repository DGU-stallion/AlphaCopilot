"""submit_backtest MCP 工具 —— 把回测作为 job 提交，立即返回（不阻塞 turn，AGENTS 规则 4）。

工具层零业务逻辑：把 job 请求写成 workspace/jobs/<id>.json 文件，业务层（FastAPI 侧的
JobQueue）在 turn 结束时扫描入队并异步执行。子进程与业务层通过文件解耦（同 artifact）。
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any


def submit_backtest(closes: list[float], fast: int = 20, slow: int = 60,
                    symbol: str = "", dates: list[str] | None = None) -> dict[str, Any]:
    """提交一个双均线金叉回测 job（长任务，异步执行，不阻塞本轮对话）。

    参数：
      closes: 收盘价序列（用 alpha.data.closes 取，如茅台近三年日线收盘）。
      fast/slow: 快/慢均线窗口（默认 20/60）。
      symbol: 标的名（仅用于图标题）。dates: 可选日期标签。
    返回：{job_id, status:'queued'}。回测完成后净值+回撤图与指标会作为 artifact 挂到会话。

    用法：先用 run_python + alpha.data.closes 取到 closes，再调本工具提交 job。
    """
    jid = f"jr-{uuid.uuid4().hex[:12]}"
    jobs_dir = Path(os.getcwd()) / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    spec = {
        "kind": "backtest",
        "params": {"closes": closes, "fast": fast, "slow": slow,
                   "symbol": symbol, "dates": dates},
    }
    (jobs_dir / f"{jid}.json").write_text(json.dumps(spec, ensure_ascii=False),
                                          encoding="utf-8")
    return {"job_id": jid, "status": "queued"}
