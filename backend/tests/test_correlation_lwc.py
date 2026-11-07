"""D5 —— 相关性走势图迁 Lightweight Charts（ROUND3 D5）。

用户要 TradingView 式交互（十字光标、滚轮/拖拽缩放），ECharts 给不了。
所以 `correlation.overlay`（多标的归一化叠加）与 `correlation.rolling`
（滚动相关单线）的 renderer 从 `echarts` 改为 `lwc`；`correlation.matrix`
是热力图，LWC 无此图形，**保持 echarts**。

这一层钉住四条契约（错了就是「图不出来」或「图出来但多了一条假回撤」）：

  1. renderer 映射：overlay / rolling → lwc，matrix → echarts。
  2. `wants_drawdown` 对相关性 fn 为 False —— 相关性没有「回撤」这一说，
     DRAWDOWN_FNS 里**不能**出现它们（曾因默认按净值算回撤，导致同一屏两份回撤）。
  3. lwc 载荷形状：`series` 条数 == 标的数（overlay）/ 1（rolling），
     `drawdown` 为空数组。
  4. 内置 correlation 页 spec 与映射表一致（`validate_spec` 通过），
     且 render 端点回的 block 里 renderer 已经是 lwc。

全程不联网：`data.closes_with_dates` / `data.names` 都被 monkeypatch。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import alpha.factor  # noqa: F401  —— 触发 correlation.* 注册（import 副作用）
from alpha import data
from alpha.lwc import lwc_payload
from api import page_spec
from api.app import create_app
from api.builtin_pages import CORRELATION_SPEC

_SYMBOLS = ["600519", "000858", "000568"]


# ---------------------------------------------------------------------------
# 假数据（与 test_pages.py 同款：日期升序唯一、价格带波动 → 收益率非全零）
# ---------------------------------------------------------------------------

def _fake_closes_with_dates(code, period=data.DAY, count=250):
    base = float(int(code[-2:]) + 10)
    out = []
    for i in range(count):
        date = f"2025-{i // 28 + 1:02d}-{i % 28 + 1:02d}"
        price = base + i * 0.5 + (i % 5) * 0.3
        out.append((date, price))
    return out


@pytest.fixture
def offline(monkeypatch):
    """不触网：价格序列与名称都换成本地确定性数据。"""
    monkeypatch.setattr(data, "closes_with_dates", _fake_closes_with_dates)
    monkeypatch.setattr(data, "names", lambda codes: {c: c for c in codes})


@pytest.fixture
def client(offline, tmp_path):
    app = create_app(db_path=":memory:", workspace_root=tmp_path)
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# 1. renderer 映射
# ---------------------------------------------------------------------------

def test_overlay_and_rolling_render_with_lwc():
    assert page_spec.renderer_for_fn("correlation.overlay") == "lwc"
    assert page_spec.renderer_for_fn("correlation.rolling") == "lwc"


def test_matrix_stays_echarts():
    """热力图 LWC 画不出来 —— 别把全族一起迁走。"""
    assert page_spec.renderer_for_fn("correlation.matrix") == "echarts"


# ---------------------------------------------------------------------------
# 2. 相关性没有「回撤」
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fn", ["correlation.overlay", "correlation.rolling"])
def test_correlation_fns_never_want_drawdown(fn):
    assert page_spec.wants_drawdown(fn) is False
    assert fn not in page_spec.DRAWDOWN_FNS


# ---------------------------------------------------------------------------
# 3. lwc 载荷形状
# ---------------------------------------------------------------------------

def test_overlay_payload_has_one_series_per_symbol_and_no_drawdown(offline):
    fn = "correlation.overlay"
    option = alpha.factor.correlation_overlay(_SYMBOLS, "1y")
    payload = lwc_payload(option, with_drawdown=page_spec.wants_drawdown(fn))

    assert len(payload["series"]) == len(_SYMBOLS)
    assert payload["drawdown"] == []
    # 归一化后每条都从 100 起（LWC 直接吃 points，不再反解 option）
    for s in payload["series"]:
        assert s["points"][0]["value"] == pytest.approx(100.0)
        assert len(s["points"]) >= 2, "少于 2 点在 LWC 里画不出线"


def test_rolling_payload_has_exactly_one_series_and_no_drawdown(offline):
    fn = "correlation.rolling"
    option = alpha.factor.correlation_rolling(_SYMBOLS[:2], 20, "1y")
    payload = lwc_payload(option, with_drawdown=page_spec.wants_drawdown(fn))

    assert len(payload["series"]) == 1
    assert payload["drawdown"] == []


# ---------------------------------------------------------------------------
# 4. 内置页 spec 与 render 端点一致
# ---------------------------------------------------------------------------

def test_builtin_correlation_spec_matches_renderer_map():
    """内置 spec 里写死的 renderer 必须与映射表一致，否则 validate_spec 直接拒。

    （内置页是 upsert 入库的，spec 里的 renderer 是**写死**的字段 ——
    改了映射却忘了改 spec，渲染出来还是旧渲染器，这条就是防线。）
    """
    page_spec.validate_spec(CORRELATION_SPEC)
    by_fn = {
        b["analysis_ref"]["fn"]: b["renderer"]
        for b in CORRELATION_SPEC["blocks"]
        if b.get("kind") == "chart"
    }
    assert by_fn["correlation.overlay"] == "lwc"
    assert by_fn["correlation.rolling"] == "lwc"
    assert by_fn["correlation.matrix"] == "echarts"


def test_render_endpoint_returns_lwc_blocks_for_correlation(client):
    r = client.post("/api/pages/correlation/render", json={"symbols": _SYMBOLS})
    assert r.status_code == 200
    blocks = r.json()["blocks"]

    overlay = next(b for b in blocks if b.get("title", "").startswith("归一化叠加走势"))
    assert overlay["renderer"] == "lwc"
    assert len(overlay["lwc"]["series"]) == len(_SYMBOLS)
    assert overlay["lwc"]["drawdown"] == []
    # option 仍保留（向后兼容 ECharts 消费方），但 LWC 只吃 lwc 载荷
    assert overlay["option"]["series"]

    rolling = next(b for b in blocks if "滚动" in b.get("title", ""))
    assert rolling["renderer"] == "lwc"
    assert len(rolling["lwc"]["series"]) == 1
    assert rolling["lwc"]["drawdown"] == []
