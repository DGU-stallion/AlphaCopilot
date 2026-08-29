#!/usr/bin/env python3
"""G3 spike：run_python 沙箱边界验证。

用 macOS sandbox-exec + Seatbelt profile 包裹一个 Python 子进程，验证四条边界：
  A. 沙箱内能 import 项目库（这里用 research 作为代表）
  B. 沙箱内能写 workspace/runs/<run_id>/
  C. 沙箱内读沙箱外的敏感文件被拒绝
  D. 超时的代码被杀掉（wall-clock 上限）

每条各一个断言，通过打印 PASS/FAIL 并以退出码汇总。
不依赖 dsh、不依赖 API key、不依赖网络。
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROFILE = Path(__file__).resolve().parent / "run_python.sb"
PYPREFIX = Path(sys.prefix)


def run_sandboxed(code: str, workspace: Path, secret_dir: Path, timeout: float) -> subprocess.CompletedProcess:
    """在 Seatbelt 沙箱内执行一段 Python，返回 CompletedProcess。"""
    args = [
        "/usr/bin/sandbox-exec",
        "-f", str(PROFILE),
        "-D", f"WORKSPACE={workspace}",
        "-D", f"SECRET_DIR={secret_dir}",
        sys.executable, "-I", "-c", code,
    ]
    return subprocess.run(
        args, capture_output=True, text=True, timeout=timeout,
        cwd=str(workspace),
    )


def check_a_import(workspace: Path, secret_dir: Path) -> bool:
    """A. 沙箱内能 import 项目库。"""
    code = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(REPO / "backend")!r})
        import research
        print("IMPORT_OK", research.__name__)
    """)
    try:
        r = run_sandboxed(code, workspace, secret_dir, timeout=15)
    except subprocess.TimeoutExpired:
        print("A import: FAIL (timeout)")
        return False
    ok = r.returncode == 0 and "IMPORT_OK" in r.stdout
    print(f"A import: {'PASS' if ok else 'FAIL'} rc={r.returncode} out={r.stdout.strip()!r} err={r.stderr.strip()[:200]!r}")
    return ok


def check_b_write_runs(workspace: Path, secret_dir: Path) -> bool:
    """B. 沙箱内能写 workspace/runs/<run_id>/。"""
    code = textwrap.dedent("""
        import os
        d = os.path.join(os.getcwd(), "runs", "r-test")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "chart.json"), "w") as f:
            f.write('{"ok": true}')
        print("WRITE_OK")
    """)
    try:
        r = run_sandboxed(code, workspace, secret_dir, timeout=15)
    except subprocess.TimeoutExpired:
        print("B write: FAIL (timeout)")
        return False
    wrote = (workspace / "runs" / "r-test" / "chart.json").exists()
    ok = r.returncode == 0 and "WRITE_OK" in r.stdout and wrote
    print(f"B write: {'PASS' if ok else 'FAIL'} rc={r.returncode} file_exists={wrote} err={r.stderr.strip()[:200]!r}")
    return ok


def check_c_read_secret_denied(workspace: Path, secret_dir: Path, secret: Path) -> bool:
    """C. 沙箱内读沙箱外的敏感文件被拒绝。"""
    code = textwrap.dedent(f"""
        try:
            with open({str(secret)!r}) as f:
                data = f.read()
            print("READ_LEAKED", repr(data[:20]))
        except Exception as e:
            print("READ_DENIED", type(e).__name__)
    """)
    try:
        r = run_sandboxed(code, workspace, secret_dir, timeout=15)
    except subprocess.TimeoutExpired:
        print("C read-secret: FAIL (timeout)")
        return False
    # 期望：读被拒（PermissionError / OSError），绝不能出现 READ_LEAKED
    leaked = "READ_LEAKED" in r.stdout
    denied = "READ_DENIED" in r.stdout
    ok = denied and not leaked
    print(f"C read-secret: {'PASS' if ok else 'FAIL'} denied={denied} leaked={leaked} out={r.stdout.strip()!r}")
    return ok


def check_d_timeout(workspace: Path, secret_dir: Path) -> bool:
    """D. 超时的代码被杀掉。"""
    code = "import time\nwhile True:\n    time.sleep(1)\n"
    killed = False
    try:
        run_sandboxed(code, workspace, secret_dir, timeout=3)
    except subprocess.TimeoutExpired:
        killed = True
    print(f"D timeout: {'PASS' if killed else 'FAIL'} killed={killed}")
    return killed


def check_e_network_denied(workspace: Path, secret_dir: Path) -> bool:
    """E. 沙箱内发起网络连接被拒绝（不得外传数据）。"""
    code = textwrap.dedent("""
        import socket
        try:
            socket.create_connection(('1.1.1.1', 53), timeout=3)
            print('NET_LEAKED')
        except Exception as e:
            print('NET_DENIED', type(e).__name__)
    """)
    try:
        r = run_sandboxed(code, workspace, secret_dir, timeout=15)
    except subprocess.TimeoutExpired:
        print("E network: FAIL (timeout)")
        return False
    leaked = "NET_LEAKED" in r.stdout
    denied = "NET_DENIED" in r.stdout
    ok = denied and not leaked
    print(f"E network: {'PASS' if ok else 'FAIL'} denied={denied} leaked={leaked} out={r.stdout.strip()!r}")
    return ok


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="g3-ws-") as tmp:
        # macOS 的 /var 是指向 /private/var 的符号链接；Seatbelt 按真实路径匹配，
        # 所以传给 -D 的路径必须先 resolve()，否则 subpath 规则不命中。
        tmp = Path(tmp).resolve()
        workspace = tmp / "workspace"
        workspace.mkdir()
        # 沙箱外的敏感文件（模拟 ~/.ssh/id_rsa；本机无 .ssh，用临时文件语义等价）
        secret_dir = (tmp / "outside")
        secret_dir.mkdir()
        secret = secret_dir / "id_rsa"
        secret.write_text("SECRET-PRIVATE-KEY-DO-NOT-LEAK")

        print(f"REPO      = {REPO}")
        print(f"PYPREFIX  = {PYPREFIX}")
        print(f"WORKSPACE = {workspace}")
        print(f"SECRET    = {secret} (outside sandbox writable root)")
        print("-" * 60)

        results = {
            "A import": check_a_import(workspace, secret_dir),
            "B write runs": check_b_write_runs(workspace, secret_dir),
            "C read-secret denied": check_c_read_secret_denied(workspace, secret_dir, secret),
            "D timeout killed": check_d_timeout(workspace, secret_dir),
            "E network denied": check_e_network_denied(workspace, secret_dir),
        }

    print("-" * 60)
    all_ok = all(results.values())
    for name, ok in results.items():
        print(f"  {'✓' if ok else '✗'} {name}")
    print(f"\nG3 RESULT: {'PASS — 全部四条边界成立' if all_ok else 'FAIL — 见上方 ✗'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
