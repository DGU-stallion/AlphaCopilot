"""T37 alpha.data 门面测试 —— 委托正确 + docstring 即 schema（质量） + 可调用。

真实数据取值需网络/mootdx（留给用户实测 3 个真实提问）；这里用 monkeypatch 验证
门面确实转调 research.* 且参数映射正确，并断言 docstring 达到 LLM schema 质量。
"""

import inspect

from alpha import data


def test_kline_delegates_with_param_mapping(monkeypatch):
    seen = {}

    def fake_kline(code, category=4, offset=60):
        seen.update(code=code, category=category, offset=offset)
        return [{"open": 1, "close": 2, "high": 3, "low": 0.5}]

    monkeypatch.setattr(data.astock, "kline", fake_kline)
    rows = data.kline("600519", period=data.WEEK, count=120)
    assert seen == {"code": "600519", "category": data.WEEK, "offset": 120}
    assert rows[0]["close"] == 2


def test_quote_valuation_global_news_delegate(monkeypatch):
    monkeypatch.setattr(data.astock, "tencent_quote", lambda codes: {"c": {"n": codes}})
    monkeypatch.setattr(data.astock, "full_valuation", lambda code: {"pe": 30, "code": code})
    monkeypatch.setattr(data.gstock, "us_hk_stock", lambda q: {"q": q})
    monkeypatch.setattr(data.newsradar, "get_radar", lambda force=False: {"force": force})

    assert data.quote(["600519"]) == {"c": {"n": ["600519"]}}
    assert data.valuation("600519")["code"] == "600519"
    assert data.global_stock("AAPL") == {"q": "AAPL"}
    assert data.news_radar(force=True) == {"force": True}


def test_closes_extracts_close(monkeypatch):
    monkeypatch.setattr(
        data.astock, "kline",
        lambda code, category=4, offset=60: [
            {"close": 10.0}, {"close": 11.5}, {"open": 1},  # 第三条无 close -> 跳过
        ],
    )
    assert data.closes("600519") == [10.0, 11.5]


def test_facade_functions_have_quality_docstrings():
    """docstring 即 LLM schema：每个门面函数都要有讲清参数/返回/用途的非平凡 docstring。"""
    for name in ["kline", "quote", "valuation", "index_quote", "global_stock",
                 "news_radar", "closes"]:
        fn = getattr(data, name)
        doc = inspect.getdoc(fn) or ""
        assert len(doc) >= 40, f"{name} docstring 过短（LLM 用不好）"
        # 参数型函数应说明参数
        if name != "index_quote":
            assert "参数" in doc or "code" in doc, f"{name} docstring 未讲参数"


def test_period_constants():
    assert (data.DAY, data.WEEK, data.MONTH, data.MIN60) == (4, 5, 6, 11)
