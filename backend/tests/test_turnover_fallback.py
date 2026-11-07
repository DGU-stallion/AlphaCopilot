"""成交额榜的多源回退（ROUND2 阶段 2 续）。

2026-10-22 实测：东财 `push2.eastmoney.com/api/qt/clist/get` 与 `push2delay`
全部 `RemoteDisconnected`（和 gtimg 的 501 同一类问题 —— 上游 WAF 拦截）。
而两处代码只认东财，于是「全市场成交额 TOP20」整块显示「暂无数据」。

这不是新增数据源（数据层冻结禁止的），是**修阻断性 bug**（取数失败）。
"""

import json

import pytest

from research import astock


class _Resp:
    def __init__(self, body: bytes) -> None:
        self._b = body

    def read(self) -> bytes:
        return self._b


_SINA_ROW = {
    "symbol": "sz300308", "code": "300308", "name": "中际旭创",
    "trade": "590.110", "changepercent": -8.76,
    "amount": 24473146887,
    # 新浪的市值字段单位是**万元**，要 ×10000 才是元
    "mktcap": 69509625.825051, "nmc": 65498492.484033,
}


def _blocked_em_get(url, params=None, headers=None, timeout=0):  # noqa: ANN001
    """模拟东财被 WAF 断开。

    ⚠️ 必须同时控住 em_get：它走 requests，**不经过 urlopen**。
    只 patch urlopen 的话，东财会真的去打网络 —— 而这个阻断是**间歇性**的
    （2026-10-22 实测：有时 RemoteDisconnected，有时能通）。
    于是测试会间歇性地「东财成功、回退根本没跑」而假绿/假红。
    """
    raise OSError("Remote end closed connection without response")


def test_falls_back_to_sina_when_eastmoney_blocked(monkeypatch):
    """东财两个域名都断连时，必须回退到新浪的排行接口。"""

    monkeypatch.setattr(astock, "em_get", _blocked_em_get)

    def fake_urlopen(req, timeout=0):  # noqa: ANN001
        url = req.full_url
        if "eastmoney" in url:
            raise OSError("Remote end closed connection without response")
        if "sina" in url:
            return _Resp(json.dumps([_SINA_ROW]).encode())
        raise AssertionError(f"意料之外的 URL: {url}")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    rows = astock.market_turnover_rank(20)

    assert len(rows) == 1
    r = rows[0]
    assert r["code"] == "300308"
    assert r["name"] == "中际旭创"
    assert r["price"] == pytest.approx(590.11)
    assert r["pct"] == pytest.approx(-8.76)
    # 成交额本来就是元
    assert r["amount"] == pytest.approx(24473146887)
    # 市值必须换算成元（新浪给的是万元）—— 不换算会小 1 万倍，前端单位全错
    assert r["mcap"] == pytest.approx(69509625.825051 * 10000, rel=1e-6)
    assert r["float_cap"] == pytest.approx(65498492.484033 * 10000, rel=1e-6)


def test_prefers_eastmoney_when_it_works(monkeypatch):
    """东财可用时不该打新浪 —— 东财的字段更全（含行业）。

    注意：东财走 `em_get`（requests），**不是** urlopen —— 直接 patch urlopen
    拦不住它，测试会静默变成「东财真去打了网络」。这里必须两处都控住。
    """
    calls: list[str] = []

    class _EmResp:
        def json(self):
            return {"data": {"diff": [{
                "f12": "600519", "f14": "贵州茅台", "f2": 1500.0, "f3": 1.2,
                "f6": 1e9, "f20": 2e12, "f21": 2e12, "f100": "白酒",
            }]}}

    def fake_em_get(url, params=None, headers=None, timeout=0):  # noqa: ANN001
        calls.append(url)
        return _EmResp()

    def fail_urlopen(req, timeout=0):  # noqa: ANN001
        raise AssertionError("东财成功时不该走到新浪（urlopen）")

    monkeypatch.setattr(astock, "em_get", fake_em_get)
    monkeypatch.setattr("urllib.request.urlopen", fail_urlopen)

    rows = astock.market_turnover_rank(20)

    assert rows[0]["industry"] == "白酒"
    assert not any("sina" in c for c in calls), "东财成功就不该再打新浪"


def test_returns_empty_when_all_sources_fail(monkeypatch):
    """全部不可用返回 []（而不是抛异常），让上层按「暂无数据」展示。"""

    monkeypatch.setattr(astock, "em_get", _blocked_em_get)

    def always_fail(req, timeout=0):  # noqa: ANN001
        raise OSError("blocked")

    monkeypatch.setattr("urllib.request.urlopen", always_fail)
    assert astock.market_turnover_rank(20) == []
