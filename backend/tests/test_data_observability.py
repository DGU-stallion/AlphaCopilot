"""数据层「失败可分辨」的测试。

## 这些问题是怎么发现的

实测：`alpha.data.closes_with_dates('600519')` 在 run_python 通道内返回**空列表**，
不抛异常。后果很具体——模型拿到空数据以为「数据源挂了」，于是改用 bash 自己 curl、
自己用 numpy 算皮尔逊相关，**绕开了 alpha.factor，违反「数字只来自确定性函数」**。
整条链路一步都不报错，只是模型行为悄悄变差。

## 两层修法，两个方向都走过弯路

**第一层：让失败可分辨。**
真取不到（网络、上游变更、限流）→ 抛 `DataUnavailable` 带原因；
真的没数据（退市、停牌、代码错）→ 返回空。两者必须能区分，
否则模型会把「环境不支持」当成「这只票没数据」，进而自己造数。

**第二层：别把取数赶到无留档的路径。**
最初想「禁网逼它走数据层」，实测证伪：agent 有 bash 与 web_fetch，
禁网对它毫无约束力，唯一效果是让它用 bash + curl 取数——那条路没有 run_id、
没有 code.py、没有 provenance，等于为了不存在的安全收益放弃本模块唯一真价值。
所以通道**放行**网络。

两层都要有：联网不等于取数一定成功（上游变更、限流、代码错都会失败），
而失败时静默返回空，仍然会把模型推向自造数据。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_darwin_only = pytest.mark.skipif(
    sys.platform != "darwin", reason="run_python 通道依赖 macOS sandbox-exec"
)


def test_data_unavailable_is_a_catchable_type():
    """`research.astock.DataUnavailable` 必须存在且可被统一捕获。"""
    from research.astock import DataUnavailable

    assert issubclass(DataUnavailable, RuntimeError), (
        "DataUnavailable 应是 RuntimeError 子类，方便调用方按「数据不可用」统一处理"
    )


@_darwin_only
def test_fetch_failure_raises_a_named_error(tmp_path):
    """取数失败必须抛 `DataUnavailable`，而不是返回空列表。

    用不存在的代码（999999）触发真实失败路径。返回空和「成功但没数据」
    在调用方看来一模一样，所以必须用异常把两者区分开。
    """
    from mcpserver.runner import run_python

    code = (
        "from alpha import data\n"
        "from research.astock import DataUnavailable\n"
        "try:\n"
        "    rows = data.closes_with_dates('999999', count=10)\n"
        "    print('RETURNED', len(rows))\n"
        "except DataUnavailable as e:\n"
        "    print('RAISED', str(e)[:80])\n"
    )

    r = run_python(code, workspace=str(tmp_path), timeout=60)

    assert "RAISED" in r.stdout, (
        "取数失败时应当抛 DataUnavailable（可分辨），而不是返回空列表。\n"
        f"实际 stdout={r.stdout[:400]!r} stderr={r.stderr[:400]!r}"
    )


@_darwin_only
def test_channel_has_network_access(tmp_path):
    """run_python 通道必须有网络。

    锁住「放行网络」这个决定，防止有人出于「更安全」的直觉把 deny network
    加回来——那个改动看起来更安全，实际让记录式执行器失去意义（见模块 docstring）。
    """
    from mcpserver.runner import run_python

    code = (
        "import urllib.request\n"
        "try:\n"
        "    urllib.request.urlopen('https://web.ifzq.gtimg.cn/', timeout=10)\n"
        "    print('NET_OK')\n"
        "except Exception as e:\n"
        "    print('NET_FAIL', str(e)[:60])\n"
    )
    r = run_python(code, workspace=str(tmp_path), timeout=60)

    assert "NET_OK" in r.stdout, (
        "run_python 通道被禁网了。这会把取数逼到 bash 路径（无留档、无 provenance）。\n"
        f"实际 stdout={r.stdout[:300]!r}"
    )


@_darwin_only
def test_secret_read_still_denied_while_network_allowed(tmp_path):
    """放行网络之后，拒读密钥的那条限制必须仍然生效。

    这两件事在 Seatbelt profile 里是独立的两条规则。放松网络不应该顺带放开
    文件读权限——那才是真正的安全损失。这条测试盯住「别把两者搞混」。
    """
    from mcpserver.runner import run_python

    secret_dir = tmp_path / "secret"
    secret_dir.mkdir()
    (secret_dir / "id_rsa").write_text("PRIVATE-KEY")
    ws = tmp_path / "ws"
    ws.mkdir()

    code = (
        f"print(open({str(secret_dir / 'id_rsa')!r}).read())\n"
        "print('LEAKED')\n"
    )
    r = run_python(
        code, workspace=str(ws), timeout=30, secret_dirs=[str(secret_dir)]
    )

    assert "LEAKED" not in r.stdout, (
        "放行网络后连密钥读也跟着放开了——这两条限制是独立的，不能一起松。\n"
        f"stdout={r.stdout[:300]!r}"
    )
