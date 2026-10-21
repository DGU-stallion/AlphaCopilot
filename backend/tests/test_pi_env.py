"""Pi 运行环境配置的测试（M1-3）。

这些测试保护的是**静默失效**：配置错了不会崩，只会让 agent 一个工具都不会用。
所以每条断言都对应一个实测过的失败模式，而不是「字段存在」这种形式检查。
"""

from __future__ import annotations

import json
import sys

from agent.pi_env import SERVER_NAME, build_mcp_config, write_project_pi_config


def test_mcp_exposure_is_direct():
    """`exposure` 必须是 `direct`。

    这是最容易被忽略、后果最严重的一条：Pi 默认给 MCP server `codemode` exposure，
    工具**不声明给模型**（只能经 codemode 脚本间接调）。

    实测对比（真 pi 1.3.0 + 一个最小 MCP server）：
      exposure 缺省     → toolsAdded 里只有内置工具，没有 mcp__*
      exposure: "direct" → toolsAdded 里出现 mcp__echosrv__hello

    缺了它，agent 会以为「我没有量化工具」，转而用 bash 自己瞎算。
    """
    cfg = build_mcp_config(python_executable="/usr/bin/python3")
    server = cfg["mcpServers"][SERVER_NAME]

    assert server["exposure"] == "direct", (
        f"exposure 必须是 direct，否则 MCP 工具不会出现在模型可见的工具列表里；"
        f"实际 {server.get('exposure')!r}"
    )


def test_mcp_command_launches_our_server_module():
    """启动命令必须真的能拉起 `mcpserver.server`。"""
    cfg = build_mcp_config(python_executable="/usr/bin/python3")
    server = cfg["mcpServers"][SERVER_NAME]

    assert server["command"] == "/usr/bin/python3"
    assert server["args"] == ["-m", "mcpserver.server"], (
        f"必须用 -m mcpserver.server 启动；实际 {server['args']}"
    )


def test_mcp_env_makes_backend_importable():
    """PYTHONPATH 必须指向 backend 包根。

    `mcpserver/server.py` 靠 `parents[1]` 定位自身并插 sys.path，理论上能自足；
    但 Pi 启动 MCP server 时的 cwd 不是我们能完全控制的，所以显式给 PYTHONPATH
    是双保险。这条断言防的是「有人把 env 清空」。
    """
    cfg = build_mcp_config()
    env = cfg["mcpServers"][SERVER_NAME]["env"]

    assert "PYTHONPATH" in env, f"缺 PYTHONPATH，MCP server 可能 import 失败：{env}"
    assert env["PYTHONPATH"].endswith("backend"), (
        f"PYTHONPATH 应指向 backend 包根；实际 {env['PYTHONPATH']}"
    )


def test_default_python_is_the_current_interpreter():
    """不显式指定时，用当前解释器。

    理由：MCP server 需要 import research/alpha，而这些包只装在当前环境里。
    用 `python3` 这种 PATH 查找会踩到别的 venv。
    """
    cfg = build_mcp_config()
    assert cfg["mcpServers"][SERVER_NAME]["command"] == sys.executable


def test_write_creates_parseable_config_under_workspace(tmp_path):
    """落盘位置必须是 `<workspace>/.pi/mcp.json` 且是合法 JSON。

    workspace 是 agent 的 cwd（ADR-0010 硬规则 9）。配置写在 workspace 内，
    而不是仓库根——「agent 的可写区」和「agent 的配置区」应是同一处。
    """
    path = write_project_pi_config(tmp_path, python_executable="/usr/bin/python3")

    assert path == tmp_path / ".pi" / "mcp.json"
    assert path.exists()

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert SERVER_NAME in loaded["mcpServers"]
    assert loaded["mcpServers"][SERVER_NAME]["exposure"] == "direct"


def test_write_is_idempotent(tmp_path):
    """重复写不报错，且内容一致（每次 start 都会调）。"""
    first = write_project_pi_config(tmp_path)
    content_first = first.read_text(encoding="utf-8")

    second = write_project_pi_config(tmp_path)
    assert second == first
    assert second.read_text(encoding="utf-8") == content_first
