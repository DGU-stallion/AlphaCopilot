"""Agent Provider 防腐层契约（ADR-0007）——**契约桩，签名已定稿，实现见 providers/**。

这是业务层与具体 agent 运行时（当前是 Pi，未来可能是别的）之间的唯一边界。
api 层只依赖本模块的 AgentEvent / AgentProvider / ProviderSpec 三个抽象，
不得 import 任何 provider 具体实现，不得出现任何运行时的私有词汇（如 cordis/session_root/
text-delta/thinking 等）。

替换 provider = 新增 providers/<name>.py 实现 AgentProvider，不改业务层。

准入约束（ADR-0007 决策 2）：provider 必须能「禁用 shell / 代码仅经 MCP 执行」。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

# ---- 中立事件 kind（前端与 api 层只认这些字符串）----
# text_delta   : 助手回复的增量文本（payload: {"text": str}）
# tool_started : 工具开始执行（payload: {"name": str, "args": dict}）
# tool_result  : 工具返回（payload: {"name": str, "result": Any}）
# turn_end     : 本轮结束（payload: {"final_text": str, "finish_reason": str}）
#                  finish_reason 取值："stop"（正常说完）/ "aborted"（用户中止）/
#                  "error" / "eof"（进程提前退出）/ "unknown"
# error        : 出错（payload: {"error": str}）
EVENT_TEXT_DELTA = "text_delta"
EVENT_TOOL_STARTED = "tool_started"
EVENT_TOOL_RESULT = "tool_result"
EVENT_TURN_END = "turn_end"
EVENT_ERROR = "error"


@dataclass
class AgentEvent:
    """归一化的 agent 事件。provider 实现负责把各自的 wire 形状翻译成这个形状。"""

    kind: str
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        """text_delta / turn_end 便捷取文本。"""
        return self.payload.get("text") or self.payload.get("final_text") or ""


@dataclass
class McpServerSpec:
    """一个要挂载给 agent 的 MCP server（中立描述）。"""

    name: str
    command: str
    args: list[str] = field(default_factory=list)


@dataclass
class ProviderSpec:
    """中立的运行参数。不含任何 provider 私有词汇（如 cordis/session_root/thinking）。

    provider 实现内部自行把这些映射到各自的配置（Pi 映射到命令行参数 + .pi/mcp.json）。
    模型私有调参（如思考强度）由 provider 内部按目标端点
    能力决定是否启用，**不在本 spec 暴露**。
    """

    workspace: Path
    system_prompt: str
    mcp_servers: list[McpServerSpec] = field(default_factory=list)
    skills_dir: Path | None = None
    model: str | None = None
    # 下面两个字段**仅为向后兼容保留**，PiProvider 不使用它们：
    # Pi 从 `~/.pi/agent/models.json` + `auth.json` 读端点与凭据，
    # 传进来也不起作用。要换端点请改 models.json。
    base_url: str | None = None
    api_key: str | None = None
    request_timeout_seconds: float = 120.0


@runtime_checkable
class AgentProvider(Protocol):
    """一个会话对应一个 provider 实例（一会话一运行时，见 ADR-0006 决策 5）。"""

    def start(self) -> None:
        """起运行时。返回即表示可接收 prompt（如 MCP 已挂载）。"""
        ...

    def astream(self, prompt: str) -> AsyncIterator[AgentEvent]:
        """发一个 prompt，异步产出归一化 AgentEvent，直到本轮结束（含 turn_end）。"""
        ...

    def close(self) -> None:
        """关闭运行时。幂等。"""
        ...

    def abort(self, reason: str = "") -> None:
        """中止进行中的那一轮 turn。

        语义要求：
        - **同步、不阻塞**：可能在事件循环里的 HTTP handler 中调用。
        - **幂等**：没有进行中的 turn 时调用不得抛异常。
        - **不杀进程**：中止的是这一轮，不是整个会话。
        - 被中止的流仍以 `turn_end` 收尾，`finish_reason == "aborted"`，
          且已收到的 `final_text` 保留。

        这些约束写在契约里而不是各 provider 自己决定，是因为它们会直接影响
        用户看到的行为（半句回复是否保留、停止后能否继续聊）。
        """
        ...

    def is_alive(self) -> bool:
        """运行时是否存活（进程泄漏测试用）。"""
        ...
