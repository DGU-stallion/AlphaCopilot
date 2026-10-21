"""PiProvider —— 与 Pi 运行时的唯一耦合点（ADR-0010）。

Pi 以 `pi --mode rpc` 子进程运行，协议是 **JSONL over stdio**（官方 docs/rpc.md、
docs/json.md）。本模块把 Pi 的 wire 形状翻译成 `agent.provider` 的中立事件，
业务层只认中立抽象，不出现任何 Pi 私有词汇。

## 为什么是 RPC 而不是 SDK

SDK 是进程内 Node/Bun 集成，业务后端是 Python，跨语言只能走子进程。
RPC 恰好就是这个边界，且官方明确「Other languages, isolated processes, IDEs」为其用途。

## 协议要点（实测 pi 1.3.0，改实现前先核对 docs）

命令（stdin，一行一个 JSON）：
    {"id": "<任意唯一串>", "type": "prompt", "message": "<文本>"}
    {"id": "<串>", "type": "get_state"}
    {"id": "<串>", "type": "abort"}

响应（stdout）：
    {"id": "<串>", "type": "response", "command": "prompt", "success": true,
     "data": {"disposition": "started" | "handled"}}

事件（stdout，多数无 id）：
    message_update / tool_execution_start / tool_execution_end / agent_end / agent_settled

**关键陷阱**：`agent_end` 只代表一次底层 run 结束，后面可能还有 retry、compaction、
steering、follow-up。必须等到 `agent_settled` 才算这一轮真的结束。等错了会截断回复。

## 分帧

严格 JSONL：一行一个完整 JSON 对象，以 LF 结尾。不能用「把 U+2028/U+2029 也当行界」
的通用行读取器（Node 的 readline 就是这种），因为它们在 JSON 字符串里合法。
这里按字节读、只切 `\n`，并剥掉可选的 `\r`。

## 生命周期

一会话一子进程（沿用 ADR-0006 决策 5）。`close()` 幂等：先关 stdin 请求有序退出，
超时再杀进程组。
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import threading
import time
from collections.abc import AsyncIterator
from typing import Any

from agent.pi_env import write_project_pi_config
from agent.provider import (
    EVENT_ERROR,
    EVENT_TEXT_DELTA,
    EVENT_TOOL_RESULT,
    EVENT_TOOL_STARTED,
    EVENT_TURN_END,
    AgentEvent,
    ProviderSpec,
)

# 默认可执行文件名。测试通过构造参数注入假 pi，生产走 PATH。
_DEFAULT_EXECUTABLE = "pi"
_SHUTDOWN_GRACE_SECONDS = 3.0

# 无数据时 select 的轮询间隔。只影响 abort 响应的及时性，不是性能参数。
_READ_POLL_SECONDS = 0.05


def _split_model(model: str) -> tuple[str | None, str]:
    """把 `provider/id` 拆成 (provider, id)；不带斜线时 provider 为 None。

    注意 model id 自身可能含斜线（如 `commandcode-plan/z-ai/glm-5.3-flash`），
    因此只按**第一个**斜线切分。
    """
    provider, sep, rest = model.partition("/")
    if not sep:
        return None, model
    return provider, rest


class PiProvider:
    """把 `pi --mode rpc` 子进程包装成 AgentProvider。

    `executable` 与 `env` 是**可注入的**，唯一目的是让契约测试能顶替真 pi 二进制
    （无需模型、key、网络，且能精确控制发出的 JSONL 记录）。生产代码不传这两个参数。
    这不是把实现细节泄漏给业务层——业务层看到的仍然只有 `ProviderSpec`。
    """

    def __init__(
        self,
        spec: ProviderSpec,
        *,
        executable: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self._spec = spec
        self._executable = executable or os.environ.get("PI_EXECUTABLE") or _DEFAULT_EXECUTABLE
        self._extra_env = dict(env or {})
        self._proc: subprocess.Popen[bytes] | None = None
        self._closed = False
        self._lock = threading.Lock()  # 串行化 turn：同一会话同一时刻只跑一轮
        self._stderr_tail: list[str] = []
        # 中止标志：由 abort() 置位，由该轮的读循环消费。
        # 用它而不是「直接关 stdin」，因为关 stdin 是**关闭整个进程**的语义，
        # 而用户想要的是只停这一轮、会话还能继续聊。
        self._abort_reason: str | None = None

    # ---------------------------------------------------------------- 生命周期

    def start(self) -> None:
        """起子进程。返回即表示可以发 prompt。

        RPC 模式**无法弹 project trust**（见 ADR-0010 修订 §1），
        所以必须带 `--approve`：否则项目 `.pi/mcp.json` 与 skills 会被静默跳过。
        实测对比：带 `--approve` 时系统 prompt 的 `mcp_servers` 段出现
        server 条目；不带时为 null。这个差异**不会红任何测试**，
        只表现为「AI 怎么什么工具都不会用」。
        """
        if self._proc is not None:
            raise RuntimeError("PiProvider 已 start()，不可重复启动")

        # 先落 MCP 配置，再起进程：Pi 在启动时读 .pi/mcp.json，错过就没有了。
        # 这一步失败不应该默默继续——没有 MCP 的 agent 等于被砍了双手。
        write_project_pi_config(self._spec.workspace)

        argv = self._build_argv()
        env = self._build_env()
        cwd = str(self._spec.workspace)

        try:
            self._proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=env,
                bufsize=0,  # 二进制无缓冲，自己按 \n 切分帧
                start_new_session=True,  # 独立进程组，close 时可整组杀
            )
        except FileNotFoundError as e:
            raise RuntimeError(
                f"找不到 pi 可执行文件 {self._executable!r}。"
                "PiProvider 需要 pi 1.3+ 在 PATH 上，或用 PI_EXECUTABLE 指定绝对路径。"
            ) from e

        self._drain_stderr()

    def _build_argv(self) -> list[str]:
        """组装 pi 命令行。

        取舍说明：
        - `--mode rpc`            JSONL 协议（本模块的全部前提）
        - `--session-dir`         会话落 workspace 内，不污染 ~/.pi
        - `--no-context-files`    不让 agent 读仓库根的 AGENTS.md（ADR-0010 硬规则 9）
        - `--approve`             RPC 无法弹 trust，显式信任项目自持目录
        - `--append-system-prompt` 注入合规 persona
        """
        spec = self._spec
        argv = [
            self._executable,
            "--mode",
            "rpc",
            "--no-context-files",
            "--approve",
        ]

        # 会话目录：workspace 下，避免动 ~/.pi
        session_dir = spec.workspace / ".pi-sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        argv += ["--session-dir", str(session_dir)]

        if spec.model:
            # `--model "provider/id"` 在 pi 1.3 里不被识别（会报 Model not found），
            # 必须拆成 `--provider <p> --model <id>`。实测：
            #   ✗ --model magpie/commandcode-plan/z-ai/glm-5.3-flash  → not found
            #   ✓ --provider magpie --model commandcode-plan/z-ai/glm-5.3-flash
            provider, model_id = _split_model(spec.model)
            if provider:
                argv += ["--provider", provider]
            argv += ["--model", model_id]

        if spec.system_prompt:
            argv += ["--append-system-prompt", spec.system_prompt]

        # skills：显式挂载（不让 Pi 自动发现，避免加载仓库根的全部 skills）
        if spec.skills_dir is not None:
            argv += ["--skill", str(spec.skills_dir)]
        else:
            # 不显式给 skills 时禁掉自动发现：仓库根有 88 个 SKILL.md，
            # 全量加载的 description 合计约 5.9k tokens/轮（ADR-0010 修订 §2）。
            argv.append("--no-skills")

        # MCP：Pi 从 agent dir 下的 mcp.json 读，不在这里传命令行
        return argv

    def _build_env(self) -> dict[str, str]:
        """构造子进程环境变量。

        **不设置 `PI_CODING_AGENT_DIR`** —— 这是实测得出的反直觉结论：
        把它指向项目的空目录会让 Pi 丢掉 `~/.pi/agent` 下的 `models.json` 与
        `auth.json`，表现为 `Unknown provider "magpie"` / `No models available`。
        而把 `auth.json` 复制进 workspace 又违反「密钥不进 workspace」的硬约束。

        正确做法：继续用 `~/.pi/agent`（凭据与模型目录都在），项目级资源交给
        **项目 `.pi/` + `--approve`**。实测 `--approve` 在 RPC 模式下确实生效：
        带它时 `.pi/mcp.json` 的 server 会被加载（系统 prompt 的 `mcp_servers`
        段出现对应条目），不带时该段为 null。
        """
        env = dict(os.environ)

        if self._spec.api_key:
            env["PI_API_KEY"] = self._spec.api_key
        if self._spec.base_url:
            env["PI_BASE_URL"] = self._spec.base_url

        env.update(self._extra_env)
        return env

    def _drain_stderr(self) -> None:
        """后台线程持续读 stderr。

        必须排空：stderr 管道写满后 Pi 会阻塞，表现为「agent 卡住不回复」。
        stderr 不是协议数据（见 docs/rpc.md），只保留尾部用于诊断。
        """

        def pump() -> None:
            proc = self._proc
            if proc is None or proc.stderr is None:
                return
            try:
                for raw in proc.stderr:
                    line = raw.decode("utf-8", "replace").rstrip()
                    if line:
                        self._stderr_tail.append(line)
                        del self._stderr_tail[:-50]  # 只留最后 50 行
            except (ValueError, OSError):
                return  # 进程已关闭

        threading.Thread(target=pump, name="pi-stderr", daemon=True).start()

    def close(self) -> None:
        """关闭运行时。幂等。

        先关 stdin 请求有序退出（Pi 会在 dispose 运行时后退出），宽限期内没退就杀进程组。
        """
        if self._closed:
            return
        self._closed = True

        proc = self._proc
        if proc is None:
            return

        try:
            if proc.stdin is not None:
                proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass

        try:
            proc.wait(timeout=_SHUTDOWN_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            # 整组杀：Pi 可能拉起子进程（如 MCP server）
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                try:
                    proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    pass

    def is_alive(self) -> bool:
        proc = self._proc
        return proc is not None and proc.poll() is None

    def abort(self, reason: str = "") -> None:
        """中止进行中的 turn。同步、幂等、不杀进程。

        做法是「置标志 + 向 pi 发 abort 命令」，而不是关 stdin 或杀进程：
        - 关 stdin = 让整个进程退出，会话就废了（用户下一句没人接）
        - 杀进程 = 同上，还会丢掉 MCP server 子进程的清理机会

        标志由该轮的读循环检查，它看到后主动结束流并以
        `turn_end(finish_reason="aborted")` 收尾，已收到的文本保留。

        同时仍向 pi 发一条 abort 命令：真的 pi 需要它来停下模型生成（否则它
        会继续烧 token 直到自己说完）。假 pi 也实现了同一行为，两边契约一致。
        """
        self._abort_reason = reason or "user"

        proc = self._proc
        if proc is None or proc.stdin is None or proc.poll() is not None:
            return
        try:
            cmd = {"id": f"abort-{int(time.time() * 1000)}", "type": "abort"}
            proc.stdin.write((json.dumps(cmd) + "\n").encode("utf-8"))
            proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            # 进程刚好退出了——目标（停下）已经达成，不必报错
            return

    # ---------------------------------------------------------------- turn

    def astream(self, prompt: str) -> AsyncIterator[AgentEvent]:
        return self._astream(prompt)

    async def _astream(self, prompt: str) -> AsyncIterator[AgentEvent]:
        if self._proc is None:
            raise RuntimeError("PiProvider 未 start()")

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Any] = asyncio.Queue()
        done = object()

        state = _TurnState()

        def on_record(rec: dict[str, Any]) -> None:
            """stdout 读线程 → 事件循环。翻译在循环线程里做，避免共享可变状态。"""
            loop.call_soon_threadsafe(_handle, rec)

        def _handle(rec: dict[str, Any]) -> None:
            ev = _translate(rec, state)
            if ev is not None:
                queue.put_nowait(ev)

        task = asyncio.create_task(
            asyncio.to_thread(self._run_turn_blocking, prompt, on_record, state, queue, done, loop)
        )

        try:
            while True:
                item = await queue.get()
                if item is done:
                    break
                yield item
        finally:
            # 若消费者提前 break（如前端停止），也要让读线程收尾
            if not task.done():
                task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    def _run_turn_blocking(
        self,
        prompt: str,
        on_record: Any,
        state: _TurnState,
        queue: asyncio.Queue,
        done: object,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        """在工作线程里：发 prompt，然后一直读到 agent_settled。"""
        proc = self._proc
        assert proc is not None and proc.stdin is not None and proc.stdout is not None

        with self._lock:
            # 新一轮开始：清掉上一轮的中止标志，否则这一轮会立刻自我中止。
            self._abort_reason = None
            request_id = f"prompt-{int(time.time() * 1000)}"
            try:
                cmd = {"id": request_id, "type": "prompt", "message": prompt}
                proc.stdin.write((json.dumps(cmd, ensure_ascii=False) + "\n").encode("utf-8"))
                proc.stdin.flush()
            except (BrokenPipeError, OSError) as e:
                loop.call_soon_threadsafe(queue.put_nowait, done)
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    AgentEvent(kind=EVENT_ERROR, payload={"error": f"写入 pi stdin 失败: {e}"}),
                )
                return

            try:
                self._read_until_settled(proc.stdout, request_id, on_record, state)
            except Exception as e:  # noqa: BLE001
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    AgentEvent(
                        kind=EVENT_ERROR,
                        payload={"error": f"{type(e).__name__}: {e}"},
                    ),
                )
            finally:
                # 收尾：仅当没收到过 agent_settled 且不是主动中止时，才补一个
                # turn_end（后者已由读循环设好 finish_reason="aborted"）。
                # state.settled 由读线程同步置位，此处读到的一定是最新值。
                if not state.settled:
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        _turn_end_event(state, finish_reason=state.finish_reason or "unknown"),
                    )
                loop.call_soon_threadsafe(queue.put_nowait, done)

    def _read_until_settled(
        self, stdout, request_id: str, on_record: Any, state: _TurnState
    ) -> None:
        """按 LF 切帧，逐条回调，直到本轮结束。

        帧读取必须按字节、只切 b"\n"：JSON 字符串里合法地包含 U+2028/U+2029，
        通用行读取器会把它们当行界，导致 JSON 解析失败。

        ## 为什么用「按 id 归属」而不是「等 N 秒排空」

        中止时真实 pi **不回应 abort 命令**：它在模型自然跑完后才发
        `agent_settled(aborted=true)`，实测可能在中止后十几秒。于是：
        - 上一轮中止后，那条 `agent_settled` 还压在 pipe 里；
        - 下一轮开头读到它，误判「本轮已结束」，只产一个空 turn_end。

        表现为「中止一次之后，这个会话就哑了」。任何超时值都会在慢响应时漏掉它，
        所以不能靠时序近似。协议本身给了归属信息：

          · 我们发出的 prompt 命令带唯一 `id`，pi 回一条同 `id` 的 `response`
            （`data.disposition` 为 `started` 或 `handled`）；
          · 会话事件（message_update / tool_execution_* / agent_settled）**没有 id**。

        因此：**看到本轮自己的 response 之后，才把事件算作本轮的**；
        之前的记录一律是上一轮的尾巴，丢弃。
        """
        import select

        buf = bytearray()
        own_response_seen = False

        while True:
            ready = select.select([stdout], [], [], _READ_POLL_SECONDS)[0]
            if not ready:
                # 没数据。注意**不能**把它当成「进程挂了」：Pi 在 TUI 交互下
                # 会用同步阻塞写 stdout，短暂空闲是正常的。
                if state.settled:
                    return
                continue

            chunk = stdout.read(4096)
            if not chunk:
                # 真 EOF：进程退出了
                if not state.settled:
                    state.finish_reason = state.finish_reason or "eof"
                return

            buf.extend(chunk)
            while True:
                idx = buf.find(b"\n")
                if idx < 0:
                    break
                line = bytes(buf[:idx])
                del buf[: idx + 1]
                if line.endswith(b"\r"):
                    line = line[:-1]
                if not line.strip():
                    continue

                try:
                    rec = json.loads(line.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue  # 坏帧跳过：stderr 才是诊断通道

                rtype = rec.get("type")

                if rtype == "response":
                    if rec.get("id") == request_id:
                        own_response_seen = True
                        if not rec.get("success", True):
                            # prompt 被拒（如模型不存在）：这是一条真错误，不能吞
                            on_record({
                                "type": "error_response",
                                "error": rec.get("error") or "prompt 被拒绝",
                            })
                    # 其他 id（如 abort 的回执）：与本轮无关
                    continue

                if not own_response_seen:
                    # 本轮 prompt 还没被受理 → 这是上一轮的残留，丢弃
                    continue

                # 已中止：后续可能的文本增量都不再累加（不把中止后的残余算进回复）
                if self._abort_reason is not None and not state.aborted:
                    state.aborted = True
                    state.finish_reason = "aborted"

                on_record(rec)

                if rtype == "agent_settled":
                    # 在**读线程**里同步置位：_translate 里的置位是经
                    # call_soon_threadsafe 排到事件循环的，本线程的 finally
                    # 可能先于它执行，导致多发一个空 turn_end。
                    state.settled = True
                    if state.aborted and state.finish_reason != "aborted":
                        state.finish_reason = "aborted"
                    return

    # ---------------------------------------------------------------- 诊断

    @property
    def stderr_tail(self) -> list[str]:
        """最近的 stderr 行，用于报错时附上线索。"""
        return list(self._stderr_tail)


# --------------------------------------------------------------------------
# wire → 中立事件 的翻译（纯函数，可单独推理）
# --------------------------------------------------------------------------


class _TurnState:
    """一轮 turn 内的累积状态。"""

    __slots__ = ("text_parts", "settled", "finish_reason", "aborted")

    def __init__(self) -> None:
        self.text_parts: list[str] = []
        self.settled = False
        self.finish_reason: str | None = None
        self.aborted = False


def _turn_end_event(state: _TurnState, finish_reason: str) -> AgentEvent:
    return AgentEvent(
        kind=EVENT_TURN_END,
        payload={
            "final_text": "".join(state.text_parts),
            "finish_reason": finish_reason,
        },
    )


def _translate(rec: dict[str, Any], state: _TurnState) -> AgentEvent | None:
    """把一条 Pi 记录翻译成中立事件；不关心的记录返回 None。

    逐字段对照 docs/json.md。字段名写错不会崩，只会「事件在但内容为空」，
    所以契约测试逐字段断言 payload，而不只断言 kind。
    """
    rtype = rec.get("type")

    if rtype == "message_update":
        # 中止后 pi 可能还会吐几个增量（模型已生成但尚未送达的部分）。
        # 不把它们算进本轮回复：用户点了停止，就不该再看到新字往外冒。
        if state.aborted:
            return None
        update = rec.get("assistantMessageEvent") or {}
        if update.get("type") == "text_delta":
            delta = update.get("delta") or ""
            if not delta:
                return None
            state.text_parts.append(delta)
            return AgentEvent(kind=EVENT_TEXT_DELTA, payload={"text": delta})
        return None

    if rtype == "tool_execution_start":
        return AgentEvent(
            kind=EVENT_TOOL_STARTED,
            payload={
                "name": rec.get("toolName"),
                "args": rec.get("args") or {},
                "call_id": rec.get("toolCallId"),
            },
        )

    if rtype == "tool_execution_end":
        return AgentEvent(
            kind=EVENT_TOOL_RESULT,
            payload={
                "name": rec.get("toolName"),
                "result": rec.get("result"),
                "is_error": bool(rec.get("isError")),
                "call_id": rec.get("toolCallId"),
            },
        )

    if rtype == "agent_settled":
        state.settled = True
        aborted = bool(rec.get("aborted"))
        state.finish_reason = "aborted" if aborted else "stop"
        return _turn_end_event(state, state.finish_reason)

    # agent_end 故意不处理：它只代表一次底层 run 结束，
    # 后面可能还有 retry / compaction / steering。提前收尾会截断回复。

    return None
