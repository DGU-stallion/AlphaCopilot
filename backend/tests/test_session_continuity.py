"""会话续接测试（M1-5）。

## 问题

`PiProvider.start()` 只给了 `--session-dir`，没指定**具体哪个**会话文件。
结果是每次启动 Pi 都新建一个会话：

- 同一 provider 连续两轮 → 记得上文 ✓
- 进程重启后再问 → **完全不记得**（实测：「我刚让你记的词是什么？」答
  「我这里没有记录——当前会话里没有你让我记词的上下文」）

用户视角：界面上一整条对话历史都在，agent 却像失忆一样。这比"没有记忆"更糟
——它让人无法信任上下文。

## 修法

Pi 每次会话在 `--session-dir` 下写一个 `<timestamp>_<uuid>.jsonl`。
`--session-id` 可以指定精确的会话 ID（不存在则创建）。所以：

1. 首次启动：不指定，让 Pi 建，然后把落盘的会话 id 记下来
2. 之后启动：用 `--session-id <记下的 id>` 续上

关键点：**id 要能跨进程存活**。它由 `ProviderSpec` 承载（业务层知道"这是同一个
会话"），不由 PiProvider 自己猜。

## 这条测试不测什么

不测「重启后能完整回忆每一句话」——那依赖模型与上下文裁剪策略，不是我们能
断言的确定性行为。只测：**续接之后，上一轮的内容确实在 agent 的上下文里**。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from agent.provider import ProviderSpec

_asyncio = pytest.mark.asyncio


# --------------------------------------------------------------------------
# 假 pi：把会话状态写到文件，模拟「同一 session-id 能读回历史」
# --------------------------------------------------------------------------

_STATEFUL_PI = '''\
import json, os, sys

out = sys.stdout
out.reconfigure(encoding="utf-8", newline="\\n")

STATE_DIR = os.environ["FAKE_PI_STATE"]
os.makedirs(STATE_DIR, exist_ok=True)

# 从 argv 里拿 --session-id（模拟 Pi 的行为：给了就续、没给就新建）
argv = sys.argv[1:]
session_id = None
if "--session-id" in argv:
    session_id = argv[argv.index("--session-id") + 1]

created_new = False
if session_id is None:
    session_id = f"sess-{os.getpid()}"
    created_new = True

state_file = os.path.join(STATE_DIR, session_id + ".json")


def load():
    if os.path.exists(state_file):
        with open(state_file, encoding="utf-8") as f:
            return json.load(f)
    return []


def save(turns):
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(turns, f, ensure_ascii=False)


def emit(record):
    out.write(json.dumps(record, ensure_ascii=False) + "\\n")
    out.flush()


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        cmd = json.loads(line)
    except json.JSONDecodeError:
        continue

    cid = cmd.get("id")
    ctype = cmd.get("type")

    if ctype == "get_state":
        # 报告当前会话 id（Phase 1 用它把新建的 id 告知调用方）
        emit({"id": cid, "type": "response", "command": "get_state", "success": True,
              "data": {"sessionId": session_id, "createdNew": created_new}})
        continue

    if ctype != "prompt":
        emit({"id": cid, "type": "response", "command": ctype, "success": True, "data": {}})
        continue

    turns = load()
    turns.append(cmd.get("message", ""))
    save(turns)

    emit({"id": cid, "type": "response", "command": "prompt", "success": True,
          "data": {"disposition": "started"}})

    # 把历史里所有内容回显出来 —— 这样测试能看出「到底记不记得」
    echo = " | ".join(turns)
    emit({"type": "message_update",
          "assistantMessageEvent": {"type": "text_delta", "contentIndex": 0,
                                    "delta": echo}})
    emit({"type": "agent_settled", "aborted": False})
'''


def _stateful_pi(tmp_path: Path) -> str:
    path = tmp_path / "stateful_pi.py"
    path.write_text(f"#!{sys.executable}\n" + _STATEFUL_PI, encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def _spec(tmp_path: Path, **kw) -> ProviderSpec:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    return ProviderSpec(
        workspace=ws, system_prompt="测试。", request_timeout_seconds=30.0, **kw
    )


async def _one(p, prompt: str) -> str:
    parts = []
    async for e in p.astream(prompt):
        if e.kind == "text_delta":
            parts.append(e.payload["text"])
    return "".join(parts)


# --------------------------------------------------------------------------
# 契约
# --------------------------------------------------------------------------


def test_spec_carries_session_id():
    """`ProviderSpec` 必须能承载会话 id —— 否则跨进程无从续接。

    id 属于**业务层**（它知道"这是同一个会话"），不该由 PiProvider 自己生成并
    藏在实例里：那样换一个 Provider 实例就丢了。
    """
    assert "session_id" in ProviderSpec.__dataclass_fields__, (
        "ProviderSpec 缺 session_id 字段。会话 id 必须由业务层持有，"
        "否则进程重启后无法知道该续哪个会话"
    )


@_asyncio
async def test_same_provider_remembers_within_session(tmp_path):
    """同一 provider 连续两轮，第二轮能看到第一轮的内容（基线）。"""
    from agent.providers.pi import PiProvider

    spec = _spec(tmp_path, skills_dir=None)
    p = PiProvider(spec, executable=_stateful_pi(tmp_path))
    p._extra_env["FAKE_PI_STATE"] = str(tmp_path / "state")
    await asyncio.to_thread(p.start)
    try:
        await _one(p, "第一句")
        out = await _one(p, "第二句")
        assert "第一句" in out, f"同会话内应记得第一句；实际 {out!r}"
    finally:
        p.close()


@_asyncio
async def test_restart_continues_the_same_session(tmp_path):
    """**核心**：换一个 provider 实例（模拟进程重启）后，必须续上同一会话。

    这是当前实装的缺口：只给 --session-dir 不给 --session-id，Pi 每次新建会话，
    agent 重启即失忆——界面上一整条历史都在，它却什么都不记得。
    """
    from agent.providers.pi import PiProvider

    state_dir = tmp_path / "state"

    # 第一段：新 provider，说一句话
    spec1 = _spec(tmp_path)
    p1 = PiProvider(spec1, executable=_stateful_pi(tmp_path))
    p1._extra_env["FAKE_PI_STATE"] = str(state_dir)
    await asyncio.to_thread(p1.start)
    try:
        await _one(p1, "暗号是紫金铜锣")
        first_session_id = p1.session_id
    finally:
        p1.close()

    assert first_session_id, (
        "首次启动后应能拿到 Pi 实际使用的 session id（否则无法在重启后续接）"
    )

    # 第二段：新实例，带上同一个 session_id
    spec2 = _spec(tmp_path, session_id=first_session_id)
    p2 = PiProvider(spec2, executable=_stateful_pi(tmp_path))
    p2._extra_env["FAKE_PI_STATE"] = str(state_dir)
    await asyncio.to_thread(p2.start)
    try:
        out = await _one(p2, "暗号是什么")
        assert "紫金铜锣" in out, (
            "重启后丢了上文。会话 id 没有正确传给 Pi。\n"
            f"首个会话 id={first_session_id!r}，第二轮输出={out!r}"
        )
    finally:
        p2.close()


@_asyncio
async def test_session_id_is_reported_after_start(tmp_path):
    """`start()` 之后要能读到实际生效的 session id。

    没有这个，业务层无法把它存进数据库，下一次启动就无从续接。
    """
    from agent.providers.pi import PiProvider

    p = PiProvider(_spec(tmp_path), executable=_stateful_pi(tmp_path))
    p._extra_env["FAKE_PI_STATE"] = str(tmp_path / "state")
    await asyncio.to_thread(p.start)
    try:
        sid = p.session_id
        assert sid, "start() 后 session_id 不能为空"
        assert isinstance(sid, str)
    finally:
        p.close()


@_asyncio
async def test_explicit_session_id_is_passed_to_pi(tmp_path):
    """给了 `ProviderSpec.session_id` 时，必须作为 `--session-id` 传给 Pi。"""
    from agent.providers.pi import PiProvider

    spec = _spec(tmp_path, session_id="fixed-session-123")
    p = PiProvider(spec, executable=_stateful_pi(tmp_path))
    p._extra_env["FAKE_PI_STATE"] = str(tmp_path / "state")

    argv = p._build_argv()
    assert "--session-id" in argv, f"未把 session_id 传给 Pi；argv={argv}"
    idx = argv.index("--session-id")
    assert argv[idx + 1] == "fixed-session-123"


# --------------------------------------------------------------------------
# 业务层：把运行时会话 id 存下来，重启后能取回
# --------------------------------------------------------------------------


def test_store_persists_runtime_session_id(tmp_path):
    """`session` 表要能存运行时会话 id。

    这是续接链路的最后一环：PiProvider 拿到 id → 业务层存库 → 下次启动读出来
    填回 ProviderSpec。少任何一环，重启就还是失忆。
    """
    from api.store import Store

    store = Store(":memory:")
    try:
        sid = store.create_session()
        assert not store.get_session(sid).get("runtime_session_id"), (
            "新会话不该有运行时会话 id"
        )

        store.set_runtime_session_id(sid, "pi-abc-123")
        assert store.get_session(sid)["runtime_session_id"] == "pi-abc-123"

        # 幂等：重复设置应覆盖而不是报错
        store.set_runtime_session_id(sid, "pi-abc-456")
        assert store.get_session(sid)["runtime_session_id"] == "pi-abc-456"
    finally:
        store.close()


@_asyncio
async def test_manager_reuses_runtime_session_id_across_runtimes(tmp_path):
    """`SessionManager` 重建 runtime 后，新 provider 仍拿到同一个会话 id。

    这条覆盖的是「provider 崩了/被关掉，再发消息时重建」这个真实场景
    （`_ensure_runtime` 的现成行为）。不测的话，一旦 runtime 重建，
    业务层就不知道要续哪个会话，agent 依然失忆。
    """
    from api.session_manager import SessionManager

    captured: list[str | None] = []

    from agent.provider import AgentEvent

    class _P:
        def __init__(self, session_id: str | None) -> None:
            captured.append(session_id)
            self.session_id = session_id or "pi-generated-1"
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

            yield AgentEvent(kind=EVENT_TEXT_DELTA, payload={"text": "ok"})
            yield AgentEvent(
                kind=EVENT_TURN_END,
                payload={"final_text": "ok", "finish_reason": "stop"},
            )

    from api.store import Store

    store = Store(":memory:")

    def factory(session_id: str, stored_id: str | None):
        ws = tmp_path / session_id / "ws"
        ws.mkdir(parents=True, exist_ok=True)
        return _P(stored_id), ws

    # 先建会话并手动塞一个「上次用过的运行时会话 id」
    sid = store.create_session()
    store.set_runtime_session_id(sid, "pi-previous-42")

    manager = SessionManager(
        store,
        lambda session_id: factory(
            session_id, store.get_session(session_id).get("runtime_session_id")
        ),
    )
    try:
        await manager.send_message(sid, "第一轮")
        await asyncio.sleep(0.2)
        assert captured and captured[0] == "pi-previous-42", (
            f"新 provider 没拿到存下来的会话 id，实际 {captured}"
        )
    finally:
        manager.close_all()
        store.close()


# --------------------------------------------------------------------------
# 关闭竞态：turn 还在跑时关服务，不能写已关闭的库
# --------------------------------------------------------------------------


@_asyncio
async def test_close_all_waits_for_inflight_turns(tmp_path):
    """`aclose_all()` 必须等在跑的 turn 收尾，再让调用方关库。

    **这是一个真实会发生的场景**：用户发完消息、agent 正在生成，此时关服务
    （部署、Ctrl-C、测试里的 teardown）。当前 `_run_turn` 是 create_task 起后
    不留引用的，`close_all()` 不等它，于是 turn 收尾时去写已关闭的 sqlite：

        sqlite3.ProgrammingError: Cannot operate on a closed database

    用户看到的是「消息发出去了但没存下来」。

    修法：把在跑的 turn task 记下来，`aclose_all()` 里 cancel + await。
    （同步的 `close_all()` 保留给不需要等 turn 的场合，如测试里的快速清理。）
    """
    from agent.provider import AgentEvent
    from api.session_manager import SessionManager
    from api.store import Store

    started = asyncio.Event()

    class _SlowProvider:
        def __init__(self) -> None:
            self.closed = False

        def start(self) -> None:
            return

        def abort(self, reason: str = "") -> None:
            return

        def close(self) -> None:
            self.closed = True

        def is_alive(self) -> bool:
            return not self.closed

        async def astream(self, prompt: str):
            from agent.provider import EVENT_TEXT_DELTA

            started.set()
            # 故意慢：模拟「用户发完消息、agent 正在生成时关服务」
            await asyncio.sleep(1.5)
            yield AgentEvent(kind=EVENT_TEXT_DELTA, payload={"text": "迟到的话"})

    store = Store(":memory:")
    sid = store.create_session()

    def factory(_sid: str):
        ws = tmp_path / "ws"
        ws.mkdir(parents=True, exist_ok=True)
        return _SlowProvider(), ws

    manager = SessionManager(store, factory)
    await manager.send_message(sid, "问一句")
    await asyncio.wait_for(started.wait(), timeout=5)

    # 记录所有未被取消、跑到写库的后台任务
    loop = asyncio.get_running_loop()
    exceptions: list[BaseException] = []
    loop.set_exception_handler(lambda _l, ctx: exceptions.append(ctx.get("exception")))

    await manager.aclose_all()
    store.close()

    # 等到慢 provider 本该完成的时间点之后，看有没有后台任务炸出来。
    # 若 close_all 没取消 turn，它会在 1.5s 后醒来去写已关闭的库。
    await asyncio.sleep(2.0)

    real = [e for e in exceptions if isinstance(e, BaseException)]
    assert not real, (
        "close_all() 没有等在跑的 turn 收尾，后台任务撞上了已关闭的库：\n"
        + "\n".join(f"  {type(e).__name__}: {e}" for e in real)
    )
