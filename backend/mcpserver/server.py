"""AlphaCopilot MCP server —— 挂给 dsh 的模型可见工具（stdio transport）。

工具：
  run_python  —— 沙箱执行 agent 代码（核心：对话即研究的执行面）
  get_quote   —— A 股实时行情快照（数据层直连）

工具层零业务逻辑：校验 → 调 alpha.*/research.* / sandbox → JSON 化 → 截断。
模型看到的工具名为 mcp__<serverName>__<rawName>（serverName 在 cordis.yml 里配为 research）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 让本 server 子进程能 import 到 backend 下的包（research / alpha / mcpserver）。
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from mcpserver.tools.run_python import run_python as _run_python  # noqa: E402
from mcpserver.tools.submit_backtest import submit_backtest as _submit_backtest  # noqa: E402
from research import astock  # noqa: E402

mcp = FastMCP("alphacopilot")

_MAX_CHARS = 6000


def run_python(code: str, timeout: float = 30.0) -> dict:
    """在隔离沙箱内执行 Python 代码，产出写入 runs/<run_id>/。

    可 import alpha（chart/data/backtest）与 research。写产出到当前目录（chart.json /
    data.csv / report.md）。不能读密钥、不能联网、超时中止。
    返回 {run_id, run_dir, returncode, stdout, stderr, timed_out, truncated, artifacts}。
    """
    return _run_python(code, timeout=timeout)


def get_quote(codes: list[str]) -> dict:
    """A 股实时行情快照。输入 6 位代码列表（如 ['600519']），返回 {code: {name, price, ...}}。

    仅展示客观数据，不构成投资建议。
    """
    try:
        result = astock.tencent_quote(codes)
        text = json.dumps(result, ensure_ascii=False, default=str)
        if len(text) <= _MAX_CHARS:
            return {"data": result}
        return {"truncated": True, "head": text[:_MAX_CHARS]}
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


mcp.tool()(run_python)
mcp.tool()(get_quote)


def submit_backtest(closes: list[float], fast: int = 20, slow: int = 60,
                    symbol: str = "", dates: list[str] | None = None) -> dict:
    """提交双均线金叉回测 job（长任务，异步，不阻塞本轮）。返回 {job_id, status}。

    closes 收盘价序列（用 alpha.data.closes 取）；fast/slow 均线窗口（默认 20/60）；
    symbol 标的名；dates 可选日期。完成后净值+回撤图与指标作为 artifact 挂到会话。
    """
    return _submit_backtest(closes, fast=fast, slow=slow, symbol=symbol, dates=dates)


mcp.tool()(submit_backtest)


if __name__ == "__main__":
    mcp.run()
