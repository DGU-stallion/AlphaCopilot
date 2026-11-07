"""Pi 运行环境的配置生成（M1-3）。

## 这个模块解决的是什么问题

Pi 有三类资源需要在**启动前**就位，否则 agent 会「看起来能跑但什么都不会用」：

| 资源 | 位置 | 不配的后果 |
|---|---|---|
| MCP server | 项目 `.pi/mcp.json` | agent 没有 `run_python` / `get_quote` / `submit_backtest` |
| skills | `--skill <dir>` 显式挂载 | 全量加载仓库根 88 个（5.9k tok/轮 + 违规类别），或一个都没有 |
| project trust | `--approve` | 上面两项被**静默跳过**，不报错 |

这类失败**不会红任何测试**，只表现为 E2E 时「AI 怎么这么笨」。所以把配置生成
做成一个纯函数并测它，而不是手工维护一个 JSON 文件——手写的文件会在某次目录
搬迁后悄悄指错，而没人发现。

## 关键实测结论（改动前请先读）

1. **`--approve` 必须带**。RPC 模式弹不出 project trust 对话框。实测对比：
   带时系统 prompt 的 `mcp_servers` 段出现 server 条目，不带时为 `null`。

2. **MCP 的 `exposure` 必须是 `"direct"`**。Pi 默认给 MCP server `codemode`
   exposure，工具**不声明给模型**（只能经 codemode 脚本间接调）。实测：
   `exposure: "direct"` 时 `mcp__<server>__<tool>` 直接出现在 `toolsAdded` 里；
   默认时工具列表里完全没有它。

3. **不要设 `PI_CODING_AGENT_DIR`**。指向项目空目录会让 Pi 丢掉 `~/.pi/agent`
   下的 `models.json` 与 `auth.json`，表现为 `Unknown provider`。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# MCP server 的名字。Pi 把工具注册成 `mcp__<serverName>__<toolName>`。
SERVER_NAME = "alphacopilot"

# 后端包根目录（含 research / alpha / mcpserver）。
_BACKEND_DIR = Path(__file__).resolve().parents[1]


def build_mcp_config(*, python_executable: str | None = None) -> dict:
    """生成 `.pi/mcp.json` 的内容。

    返回结构而非写文件，便于测试断言。要落盘用 `write_project_pi_config`。

    `exposure: "direct"` 是**必须的**：默认的 `codemode` 不把工具声明给模型，
    而是要求模型写脚本间接调用。对我们的三个工具（run_python / get_quote /
    submit_backtest）来说，直接暴露才符合使用习惯，也让工具调用在 transcript
    里是一条清晰的 `tool_execution_start`，便于 provenance 取 codeHash。
    """
    exe = python_executable or sys.executable
    return {
        "mcpServers": {
            SERVER_NAME: {
                "command": exe,
                "args": ["-m", "mcpserver.server"],
                # cwd 必须是 backend：server.py 靠 parents[1] 定位自身包根，
                # 从别处启动会 import 失败。Pi 的 mcp 配置没有 cwd 字段，
                # 所以用 PYTHONPATH 兜住（server.py 自己也会插 sys.path，双保险）。
                "env": {"PYTHONPATH": str(_BACKEND_DIR)},
                # 不声明这个，工具不会出现在模型可见的工具列表里（实测）。
                "exposure": "direct",
                "description": "AlphaCopilot 量化工具：行情快照、沙箱代码执行、回测提交",
            }
        }
    }


def write_project_pi_config(
    workspace: Path, *, python_executable: str | None = None
) -> Path:
    """把 MCP 配置写到 `<workspace>/.pi/mcp.json`，返回该路径。

    workspace 是 agent 的 cwd（ADR-0010 硬规则 9）。配置写在 workspace 里而不是
    仓库根，是因为「agent 的可写区」和「agent 的配置区」应该是同一个地方。
    """
    pi_dir = workspace / ".pi"
    pi_dir.mkdir(parents=True, exist_ok=True)
    target = pi_dir / "mcp.json"
    target.write_text(
        json.dumps(build_mcp_config(python_executable=python_executable),
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target
