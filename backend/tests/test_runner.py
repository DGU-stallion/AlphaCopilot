"""run_python 记录式执行器的测试（原 T33，M1-6 随 sandbox→runner 改名）。

覆盖：执行 + artifact 落 runs/<run_id>/、import alpha、超时被杀、输出截断、
以及**本通道自身**的限权（读敏感目录被拒）。

⚠️ 重要口径（ADR-0012「已决 2」）：这些断言只证明**这条通道**的限制生效，
**不证明 agent 整体受限**。agent 有完整 bash，同样的事它绕得过去。
把本文件当成「我们有沙箱保护」是误读——它不是安全边界。

（macOS 专属：用 /usr/bin/sandbox-exec。）
"""

import sys
import tempfile
from pathlib import Path

import pytest

from mcpserver.runner import run_python

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="run_python 通道用 macOS sandbox-exec 做纵深防御"
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


def test_read_secret_denied_by_this_channel():
    """本通道拒绝读敏感目录。

    ⚠️ 读这一条时不要得出「agent 读不到密钥」的结论：agent 用 bash 能直接 `cat`。
    这条只保证「当 agent 选择走 run_python 时，我们不会替它开门」。
    真正的防线是 prompt 层约束 + 人看着跑（ADR-0010 §3 显式接受的残余风险）。
    """
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
