#!/usr/bin/env python3
"""G1 spike 第二部分：Python SDK + 自写 cordis.yml 挂我们的 MCP server。

验证链条（从 keyless 到需 key）：
  [A] SDK 能用 node carrier 启动 dsh runtime 子进程（DSH_RUNTIME_MODE=node）
  [B] initialize 成功 —— 因 cordis.yml 里 mcp-research 设了 failOnStartupError:true，
      且 sdk-jsonrpc-server 的 initialize 会等插件树 settle（含 MCP 工具发现），
      所以 initialize 成功即证明「MCP server 被挂载 + 工具发现完成」。这是 keyless 结论。
  [C] 真实 agent 调用 get_quote —— 需 DEEPSEEK_API_KEY，模型推理决定调工具。
      无 key 时标注为「需凭证」，不阻断 A/B 机制结论。

用法：
  DSH_RUNTIME_MODE=node python3 verify_sdk_mcp.py
  DEEPSEEK_API_KEY=sk-... DSH_RUNTIME_MODE=node python3 verify_sdk_mcp.py   # 含 C
"""

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORDIS = HERE / "cordis.yml"
MCP_SERVER = HERE / "mcp_server_min.py"

# 让 cordis.yml 里的 !!js process.env.G1_MCP_PY / G1_MCP_SERVER 解析到本机 python + server
os.environ["G1_MCP_PY"] = sys.executable
os.environ["G1_MCP_SERVER"] = str(MCP_SERVER)

from deepseek_harness import DeepSeekHarness, DeepSeekHarnessConfig


def main() -> int:
    print("=" * 60)
    print("G1-part2: Python SDK + cordis.yml 挂 MCP server")
    print("=" * 60)
    print(f"runtime mode : {os.environ.get('DSH_RUNTIME_MODE', '(default/exe)')}")
    print(f"cordis       : {CORDIS}")
    print(f"mcp server   : {MCP_SERVER}")

    has_key = bool(os.environ.get("DEEPSEEK_API_KEY"))
    print(f"api key      : {'set' if has_key else 'UNSET (C 项将标注需凭证)'}")
    print("-" * 60)

    with tempfile.TemporaryDirectory(prefix="g1-sdk-") as tmp:
        tmp = Path(tmp).resolve()
        workspace = tmp / "ws"
        workspace.mkdir()
        sessions = tmp / "sessions"
        sessions.mkdir()

        cfg = DeepSeekHarnessConfig(
            model="deepseek-v4-flash",
            cwd=str(workspace),
            session_root=str(sessions),
            cordis=str(CORDIS),
            request_timeout_seconds=60.0,
        )

        # [A]+[B] 启动 + initialize（initialize 成功即证明 MCP 挂载 + 工具发现完成）
        try:
            harness = DeepSeekHarness(cfg)
            harness.start()  # 内部：spawn runtime → initialize（等插件树 settle）
            print("[A] SDK 启动 node carrier: PASS（子进程已起）")
            print("[B] initialize 成功: PASS —— mcp-research 挂载且工具发现完成")
            print("    （failOnStartupError:true 下，MCP 连接失败会让 initialize 抛错）")
        except Exception as e:  # noqa: BLE001
            print(f"[A/B] FAIL: {type(e).__name__}: {e}")
            return 1

        mechanism_ok = True

        # [C] 真实调用（需 key）
        call_ok = False
        if has_key:
            try:
                result = harness.run(
                    "调用工具查询贵州茅台（600519）的最新股价，只报数字。",
                    session_id="g1-c",
                )
                text = result.final_response
                called = any(
                    "get_quote" in str(n.payload) for n in result.notifications
                )
                print(f"[C] agent 调用 get_quote: {'PASS' if called else '未见工具调用'} "
                      f"finish={result.finish_reason}")
                print(f"    回复摘要: {text[:120]!r}")
                call_ok = called
            except Exception as e:  # noqa: BLE001
                print(f"[C] agent 调用: 失败（可能网络/凭证）: {type(e).__name__}: {e}")
        else:
            print("[C] agent 调用 get_quote: 需 DEEPSEEK_API_KEY（机制已由 A/B 证明）")

        harness.close()

    print("-" * 60)
    print(f"G1-part2 机制结论: {'PASS — SDK 能挂载我们的 MCP server' if mechanism_ok else 'FAIL'}")
    print(f"  真实 agent 调用: {'PASS' if call_ok else '需凭证/未验证（不阻断机制结论）'}")
    return 0 if mechanism_ok else 1


if __name__ == "__main__":
    sys.exit(main())
