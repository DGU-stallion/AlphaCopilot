"""run_python 记录式执行器（M1-6 重新定位；原 mcpserver/sandbox.py）。

## 它是什么，不是什么

**它是**：一个把 agent 写的 Python 代码跑起来、并顺手留档的通道。
**它不是**：安全边界。ADR-0012「已决 2」已裁决，原先叫「沙箱」是误导。

为什么不再算安全边界：agent 现在有完整 bash（ADR-0010），可以写任意位置、
读 `~/.ssh`、联网——下面这些 Seatbelt 限制全部绕得过去。把本模块当边界保护
产品，是自我安慰。

## 那为什么还留着

三个与安全无关、但确实有用的性质：

1. **自动留档** —— 每次执行分配 run_id、建 `workspace/runs/<run_id>/`、把代码
   原样存成 `code.py`。这正是 provenance 里 `runId` / `codeHash` 的抓手
   （走 bash 就得从 Pi session JSONL 反推）。
2. **工具一致性** —— 它和 MCP 的 `get_quote` 走同一套取数函数，
   不会出现「这个工具能取、那个不能」的割裂。
3. **可复现** —— 半年后能翻出当时的代码重跑。

Seatbelt profile（`run_python.sb`）只约束**这条通道自身**：限写（仅 workspace）、
对已知密钥目录 deny 读、wall-clock 超时。这些限制是纵深防御的一层，
**不代表 agent 整体受限**——见 ADR-0010 §3 的显式风险记录。

**网络是放行的**（曾经 deny，已改）。原意是「让取数走数据层」，但实测证伪：
agent 有 bash 与 web_fetch，禁网对它毫无约束力，唯一效果是把取数赶到
bash + curl 那条无留档的路径上。放行后实测模型 1 次 run_python 完成
（`alpha.data.kline` 取数），而禁网时是 10 次工具调用 + 自己实现指标。

## 约定

- 代码里可 `import alpha` / `import research`（执行器把 backend 注入 sys.path）
- stdout/stderr 截断到上限（默认 6000 字符），防止 agent 上下文被撑爆
- 超时 → 杀进程，返回 timed_out=True
- 不碰数据库、不校验产出内容（artifact 校验在业务层）
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[1]
_PROFILE = _HERE / "run_python.sb"
_BACKEND = _REPO_ROOT / "backend"

# 生产环境应显式拒绝读取的敏感目录（黑名单，纵深防御，见 ADR-0006 残余风险）。
_DEFAULT_SECRET_DIRS = [
    str(Path.home() / ".ssh"),
    str(Path.home() / ".aws"),
    str(Path.home() / ".config"),
]

_MAX_OUTPUT_CHARS = 6000


@dataclass
class RunResult:
    run_id: str
    run_dir: str
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    truncated: bool
    artifacts: list[str] = field(default_factory=list)


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + f"\n…[截断，共 {len(text)} 字符]", True


def _preamble(run_dir: Path) -> str:
    """注入 sys.path（让 import alpha/research 可用）+ 切到 run_dir。"""
    return (
        "import sys, os\n"
        f"sys.path.insert(0, {str(_BACKEND)!r})\n"
        f"os.chdir({str(run_dir)!r})\n"
    )


def run_python(
    code: str,
    *,
    workspace: str | Path | None = None,
    timeout: float = 30.0,
    secret_dirs: list[str] | None = None,
    max_output: int = _MAX_OUTPUT_CHARS,
) -> RunResult:
    """在 Seatbelt 沙箱内执行 code，产出写入 workspace/runs/<run_id>/。

    workspace: 沙箱唯一可写根（默认 <repo>/workspace）。timeout: wall-clock 秒。
    返回 RunResult（含 run_id / run_dir / stdout / stderr / timed_out / artifacts）。
    """
    ws = Path(workspace or Path.cwd()).resolve()
    (ws / "runs").mkdir(parents=True, exist_ok=True)
    run_id = f"r-{uuid.uuid4().hex[:12]}"
    run_dir = (ws / "runs" / run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    # 原样留存代码（可重跑、可提炼为 alpha.* 函数）。
    (run_dir / "code.py").write_text(code, encoding="utf-8")
    full_code = _preamble(run_dir) + code

    secrets = secret_dirs if secret_dirs is not None else _DEFAULT_SECRET_DIRS
    # Seatbelt profile 只支持一个 SECRET_DIR 参数；取第一个存在的，否则用 workspace 外一个占位。
    secret_dir = next((s for s in secrets if Path(s).exists()), str(ws.parent / "__no_secret__"))

    args = [
        "/usr/bin/sandbox-exec",
        "-f", str(_PROFILE),
        "-D", f"WORKSPACE={ws}",
        "-D", f"SECRET_DIR={Path(secret_dir).resolve()}",
        sys.executable, "-I", "-c", full_code,
    ]

    timed_out = False
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, cwd=str(run_dir),
        )
        rc, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        timed_out = True
        rc = -1
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")

    out, t1 = _truncate(out, max_output)
    err, t2 = _truncate(err, max_output)

    # 收集产出物（code.py 除外）。
    artifacts = sorted(
        p.name for p in run_dir.iterdir() if p.is_file() and p.name != "code.py"
    )

    return RunResult(
        run_id=run_id,
        run_dir=str(run_dir),
        returncode=rc,
        stdout=out,
        stderr=err,
        timed_out=timed_out,
        truncated=t1 or t2,
        artifacts=artifacts,
    )
