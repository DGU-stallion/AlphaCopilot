"""T33 run_python 沙箱执行器测试（复用 G3 边界，落到生产执行器）。

DoD：沙箱内执行、artifact 写入 runs/<run_id>/、超时/输出截断契约；读敏感目录被拒。
（macOS 专属：用 /usr/bin/sandbox-exec。）
"""

import sys
import tempfile
from pathlib import Path

import pytest

from mcpserver.sandbox import run_python

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="run_python 沙箱依赖 macOS sandbox-exec"
)


def test_exec_and_write_artifact():
    with tempfile.TemporaryDirectory(prefix="t33-") as tmp:
        code = (
            "import json\n"
            "with open('chart.json','w') as f: json.dump({'ok': True}, f)\n"
            "print('DONE')\n"
        )
        r = run_python(code, workspace=tmp, timeout=15)
        assert r.returncode == 0, r.stderr
        assert "DONE" in r.stdout
        assert "chart.json" in r.artifacts
        # 文件确实落在 runs/<run_id>/
        assert (Path(r.run_dir) / "chart.json").exists()
        assert (Path(r.run_dir) / "code.py").read_text().startswith("import json")


def test_can_import_alpha():
    with tempfile.TemporaryDirectory(prefix="t33-imp-") as tmp:
        code = (
            "from alpha import chart\n"
            "opt = chart.line(['a','b'], {'s':[1,2]})\n"
            "print('SERIES', opt['series'][0]['type'])\n"
        )
        r = run_python(code, workspace=tmp, timeout=20)
        assert r.returncode == 0, r.stderr
        assert "SERIES line" in r.stdout


def test_timeout_killed():
    with tempfile.TemporaryDirectory(prefix="t33-to-") as tmp:
        code = "import time\nwhile True: time.sleep(1)\n"
        r = run_python(code, workspace=tmp, timeout=2)
        assert r.timed_out is True


def test_output_truncated():
    with tempfile.TemporaryDirectory(prefix="t33-tr-") as tmp:
        code = "print('x' * 20000)\n"
        r = run_python(code, workspace=tmp, timeout=15, max_output=6000)
        assert r.truncated is True
        assert len(r.stdout) <= 6000 + 64  # 截断提示尾巴


def test_read_secret_denied():
    with tempfile.TemporaryDirectory(prefix="t33-sec-") as tmp:
        tmp = Path(tmp).resolve()
        ws = tmp / "ws"
        ws.mkdir()
        secret_dir = tmp / "secret"
        secret_dir.mkdir()
        secret = secret_dir / "id_rsa"
        secret.write_text("PRIVATE-KEY-DO-NOT-LEAK")
        code = (
            f"open({str(secret)!r}).read()\n"
            "print('LEAKED')\n"
        )
        r = run_python(code, workspace=str(ws), timeout=15,
                       secret_dirs=[str(secret_dir)])
        # 读被拒 → 抛异常（非零退出），绝不能出现 LEAKED
        assert "LEAKED" not in r.stdout
        assert r.returncode != 0
