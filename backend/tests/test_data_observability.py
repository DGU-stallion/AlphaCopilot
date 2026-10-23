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


def test_gtimg_kline_tries_both_hosts(monkeypatch):
    """K 线必须**依次尝试两个 gtimg 入口**，不能只认一个域名。

    2026-10-21 实测：`web.ifzq.gtimg.cn` 返回 501，而 `ifzq.gtimg.cn` 正常。
    只写一个域名时，上游一改行为整个 K 线功能就挂 —— 而它们只是同一个服务的
    两个入口，没有任何理由只用一个。

    这里让第一个域名失败，断言仍能拿到数据（即第二个域名被试过）。
    """
    from research import astock

    calls: list[str] = []

    class _Resp:
        def __init__(self, body: bytes) -> None:
            self._b = body

        def read(self) -> bytes:
            return self._b

    payload = (
        b'{"code":0,"msg":"","data":{"sh600519":{"qfqday":'
        b'[["2026-10-20","100.0","101.0","102.0","99.0","1000"]]}}}'
    )

    def fake_urlopen(req, timeout=0):  # noqa: ANN001
        url = req.full_url
        calls.append(url)
        if "web.ifzq" in url:
            raise OSError("HTTP Error 501: Not Implemented")
        return _Resp(payload)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    rows = astock._tencent_kline("600519", category=4, offset=5)

    assert rows, "第一个域名失败时，必须回退到第二个域名"
    assert rows[0]["close"] == 101.0
    assert len(calls) == 1, "第一个域名成功就不该再打第二个（避免无谓请求）"


def test_gtimg_kline_reports_when_all_hosts_fail(monkeypatch):
    """两个域名都失败时，必须抛出带原因的 DataUnavailable，而不是返回空。

    返回空会让图表画成一条平线，看着像「今天没成交」，用户会误读。
    """
    from research import astock

    def always_fail(req, timeout=0):  # noqa: ANN001
        raise OSError("HTTP Error 501: Not Implemented")

    monkeypatch.setattr("urllib.request.urlopen", always_fail)

    try:
        astock._tencent_kline("600519", category=4, offset=5)
    except astock.DataUnavailable as e:
        assert "均不可用" in str(e)
        assert "501" in str(e), "错误信息必须带上游具体原因，否则无法判断该重试还是换源"
    else:
        raise AssertionError("两个域名都失败时必须抛 DataUnavailable")


def test_gtimg_falls_back_to_unadjusted_endpoint(monkeypatch):
    """`/fqkline/get` 被上游 WAF 拦时，必须回退到 `/kline/kline`。

    2026-10-22 实测：`ifzq.gtimg.cn` 与 `web.ifzq.gtimg.cn` 的
    `/appstock/app/fqkline/get` 全部返回 501（腾讯 WAF 拦截页），
    而同一服务的 `/appstock/app/kline/kline` 正常。
    只认 fqkline 会让整个回测页 503 —— 用户看到的是「数据源不可用」。

    这不是「新增数据源」（那是数据层冻结禁止的），是**修阻断性 bug**：
    同一个 gtimg 服务的另一个端点。
    """
    from research import astock

    calls: list[str] = []

    class _Resp:
        def __init__(self, body: bytes) -> None:
            self._b = body

        def read(self) -> bytes:
            return self._b

    body = (
        b'{"code":0,"msg":"","data":{"sh600519":{"day":'
        b'[["2026-10-20","100.0","101.0","102.0","99.0","1000"]]}}}'
    )

    def fake_urlopen(req, timeout=0):  # noqa: ANN001
        url = req.full_url
        calls.append(url)
        if "fqkline" in url:
            raise OSError("HTTP Error 501: Not Implemented")
        return _Resp(body)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    rows = astock._tencent_kline("600519", category=4, offset=5)

    assert rows, "fqkline 全挂时必须回退到 kline/kline"
    assert rows[0]["close"] == 101.0
    assert any("kline/kline" in u for u in calls), "必须真的试过非复权端点"
    assert any("fqkline" in u for u in calls), "复权端点应优先尝试（有 qfq 更准）"


def test_gtimg_prefers_adjusted_endpoint_when_it_works(monkeypatch):
    """复权端点可用时**不该**去打非复权端点 —— 复权数据更准确。"""
    from research import astock

    calls: list[str] = []

    class _Resp:
        def __init__(self, body: bytes) -> None:
            self._b = body

        def read(self) -> bytes:
            return self._b

    body = (
        b'{"code":0,"msg":"","data":{"sh600519":{"qfqday":'
        b'[["2026-10-20","100.0","101.0","102.0","99.0","1000"]]}}}'
    )

    def fake_urlopen(req, timeout=0):  # noqa: ANN001
        calls.append(req.full_url)
        return _Resp(body)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    rows = astock._tencent_kline("600519", category=4, offset=5)

    assert rows[0]["close"] == 101.0
    assert len(calls) == 1, "复权端点成功就不该再试非复权（避免无谓请求）"
    assert "fqkline" in calls[0]
