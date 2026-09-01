"""run_python MCP 工具 —— 工具层零业务逻辑（T33）。

职责仅：接收 code → 调 sandbox.run_python 执行 → 把 RunResult JSON 化返回。
沙箱边界、artifact 写入都在 sandbox 层；本层不碰数据库、不校验产出内容。
"""

from __future__ import annotations

from typing import Any

from mcpserver.sandbox import run_python as _run


def run_python(code: str, timeout: float = 30.0) -> dict[str, Any]:
    """在隔离沙箱内执行 Python 代码，产出写入本次运行目录 runs/<run_id>/。

    用途：你（agent）写分析/画图代码，在用户数据上算结果。可 `import alpha`（业务库：
    alpha.chart 画 ECharts、alpha.data 取数、alpha.backtest 回测）与 `import research`。
    把要留存的产出（图 chart.json / 表 data.csv / 报告 report.md）写到当前工作目录。

    边界：只能写本次 run 目录，不能读密钥目录，不能联网，超时会被中止。

    参数：
      code:    要执行的 Python 源码（字符串）。
      timeout: wall-clock 秒上限（默认 30）。
    返回：
      {run_id, run_dir, returncode, stdout, stderr, timed_out, truncated, artifacts[]}。
    """
    r = _run(code, timeout=timeout)
    return {
        "run_id": r.run_id,
        "run_dir": r.run_dir,
        "returncode": r.returncode,
        "stdout": r.stdout,
        "stderr": r.stderr,
        "timed_out": r.timed_out,
        "truncated": r.truncated,
        "artifacts": r.artifacts,
    }
