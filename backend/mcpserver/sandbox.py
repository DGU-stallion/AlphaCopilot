"""run_python 沙箱执行器（T33 基础设施，非业务逻辑）。

用 macOS sandbox-exec + Seatbelt profile（G3 验证过）包裹一个 Python 子进程执行 agent
生成的代码。边界（G3 结论）：限写（仅 workspace）、拒读敏感目录、禁网络、wall-clock 超时。

约定：
- 每次执行分配 run_id，建 workspace/runs/<run_id>/，代码原样存 code.py（可重跑/可提炼）。
- 代码里可 `import alpha` / `import research`（执行器把 backend 注入 sys.path）。
- stdout/stderr 截断到上限（默认 6000 字符），防止 agent 上下文被撑爆。
- 超时 → 杀进程，返回 timed_out=True。

这是纯基础设施：不碰数据库、不校验产出内容（artifact 校验在业务层 T34）。
"""

from __future__ import annotations

import os
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
