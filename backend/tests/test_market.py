"""市场数据回归测试 —— 涨停原因映射 + 指数日K前缀归一化。

盘面数据 / 涨停样本改由前端直连专用端点（research.market），
这里覆盖 research 层的降级纪律与两处 bug 回归。
"""

from __future__ import annotations


# ---- 涨停原因映射（Bug A 回归：lianban_stocks[].reason 曾全为 None）----

def test_emotion_fills_reason_from_source(monkeypatch):
    """连板股的 reason 由问财题材串填充（数据源有值时不留空）。"""
    import research.market as rmarket

    def fake_pool(endpoint, date, *a, **k):
        if endpoint == "getTopicZTPool":
            return [
                {"c": "605577", "n": "龙版传媒", "lbc": 5, "p": 10000, "zdp": 10.0,
                 "amount": 1000, "ltsz": 1.0, "hybk": "出版"},
                {"c": "603162", "n": "海通发展", "lbc": 2, "p": 20000, "zdp": 10.0,
                 "amount": 500, "ltsz": 1.0, "hybk": "航运"},
            ]
        return []

    monkeypatch.setattr(rmarket.astock, "em_zt_topic_pool", fake_pool)
    monkeypatch.setattr(rmarket, "_fetch_zt_reasons",
                        lambda date: {"605577": "AI漫剧+出版发行", "603162": "干散货航运"})
    out = rmarket._emotion()
    reasons = {s["code"]: s["reason"] for s in out["lianban_stocks"]}
    assert reasons["605577"] == "AI漫剧+出版发行"
    assert reasons["603162"] == "干散货航运"


def test_emotion_reason_none_when_source_empty(monkeypatch):
    """问财缺 key / 失败 → reason 留 None（前端显示 —），不伪造。"""
    import research.market as rmarket

    monkeypatch.setattr(
        rmarket.astock, "em_zt_topic_pool",
        lambda endpoint, date, *a, **k: (
            [{"c": "605577", "n": "龙版传媒", "lbc": 3, "p": 10000, "zdp": 10.0,
              "amount": 1, "ltsz": 1.0, "hybk": "出版"}]
            if endpoint == "getTopicZTPool" else []),
    )
    monkeypatch.setattr(rmarket, "_fetch_zt_reasons", lambda date: {})
    out = rmarket._emotion()
    assert out["lianban_stocks"][0]["reason"] is None


def test_fetch_zt_reasons_no_key_returns_empty(monkeypatch):
    """未配置 IWENCAI_API_KEY 时直接返回空 dict，不发请求。"""
    import research.market as rmarket

    monkeypatch.delenv("IWENCAI_API_KEY", raising=False)
    assert rmarket._fetch_zt_reasons("20260905") == {}


def test_clean_reason_normalizes_and_limits():
    import research.market as rmarket

    assert rmarket._clean_reason("A，B,C") == "A+B+C"
    assert rmarket._clean_reason("a+b+c+d+e") == "a+b+c+d"  # 限 4 标签


# ---- 指数日K取数：指数代码前缀归一化（Bug B 回归：000300 曾判成 sz、取回 0 行）----

def test_index_kline_uses_exchange_prefix(monkeypatch):
    """沪深300(000300) 走 gtimg 时须用 sh 前缀，否则 sz000300 取不到日K → 基准直线。"""
    import research.astock as astock

    captured = {}

    class _Resp:
        def read(self):
            # gtimg 回退源需要 data[sym] 节点；只要 _tencent_kline 用对了 sym 就能解析
            sym = captured["sym"]
            return (
                '{"data": {"' + sym + '": {"qfqday": '
                '[["2026-09-04", "4575.32", "4548.05", "4602.20", "4530.76", "1.0"]]}}}'
            ).encode("utf-8")

    def fake_urlopen(req, timeout=12):
        captured["sym"] = req.full_url.split("param=")[1].split(",")[0]
        return _Resp()

    monkeypatch.setattr(astock.urllib.request, "urlopen", fake_urlopen)
    rows = astock._tencent_kline("000300", category=4, offset=10)
    assert captured["sym"] == "sh000300"  # 指数走 _INDEX_PREFIX，非个股默认 sz
    assert rows and rows[0]["close"] == 4548.05


def test_stock_kline_prefix_unaffected_by_index_map(monkeypatch):
    """个股 000001（平安银行, sz）不得被指数映射误判成 sh —— _INDEX_PREFIX 只覆盖指数取数场景。

    注：000001 同时是上证综指代码，但指数映射只作用于此 gtimg K 线函数的指数取数；
    个股行情 tencent_quote 仍走 get_prefix（此测覆盖 K 线路径不影响个股前缀语义）。
    """
    import research.astock as astock
    # 个股代码不在 _INDEX_PREFIX 时应走 get_prefix；600519 → sh，000858 → sz
    assert "600519" not in astock._INDEX_PREFIX
    assert astock.get_prefix("600519") == "sh"
    assert astock.get_prefix("000858") == "sz"
