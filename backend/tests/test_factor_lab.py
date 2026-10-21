"""M4-1 因子实验室（alpha.factor_lab）单元测试。

全部用「答案已知」的构造数据，不用真实行情（真实数据会随日期漂移、闪烁）。
覆盖：
  1. IC 完美正=1 / 完美负=-1 / 无关=0
  2. RankIC 对异常值不敏感（IC 大变、RankIC 几乎不变）
  3. ICIR 的 std=0 / 样本不足边界（明确返回 0.0，不是 NaN/inf）
  4. decay 结构正确（keys、值域、perfect 数据），不写死全部期望值
  5. quantile_returns 样本不足一个分位（3 只股票分 5 组）
  6. 缺失值按【股票级 pairwise 丢弃】（声明约定，不弃整日）
  7. 空输入不崩（全部返回安全的空/零值）
  8. rank_ic 并列值（ties）→ 平均位次（midrank），有精确已知答案
尾部有 3 个变异测试锚点：MISS-ref（mutation 注释标明靶点）。
"""

from __future__ import annotations

import pytest

from alpha import chart, factor_lab, lwc
from alpha.registry import is_registered
from api import page_spec

# ---------------------------------------------------------------------------
# 1/8. IC 基础 + RankIC ties
# ---------------------------------------------------------------------------

def test_ic_perfect_positive_negative_and_zero():
    assert factor_lab.ic([1, 2, 3], [0.1, 0.2, 0.3]) == pytest.approx(1.0)
    assert factor_lab.ic([1, 2, 3], [0.3, 0.2, 0.1]) == pytest.approx(-1.0)
    # 构造的正交截面：x 偏差 (-1.5,-.5,.5,1.5)，y 偏差 (1,-1,-1,1) → cov=0 → IC=0
    assert factor_lab.ic([1, 2, 3, 4], [1.0, -1.0, -1.0, 1.0]) == pytest.approx(0.0)


def test_ic_method_validation():
    with pytest.raises(ValueError):
        factor_lab.ic([1, 2], [1, 2], method="cosine")


def test_rank_ic_ties_use_average_ranks():
    """并列值取平均位次：factor [1,1,2] → 位次 [1.5,1.5,3]。

    σ ranks [1.5,1.5,3] vs returns [1,2,3] 的皮尔逊 = 1.5/√3 ≈ 0.8660。
    若实现选择别的方式（first/min/max 位次或把这些对丢弃），都会得到不同答案。
    """
    assert factor_lab.rank_ic([1, 1, 2], [1.0, 2.0, 3.0]) == pytest.approx(1.5 / 3 ** 0.5)


def test_rank_ic_aliases_spearman_method():
    assert factor_lab.rank_ic([3, 1, 2], [0.3, 0.1, 0.2]) == \
        factor_lab.ic([3, 1, 2], [0.3, 0.1, 0.2], method="spearman")


# ---------------------------------------------------------------------------
# 2. RankIC 对异常值不敏感（最能体现两者区别的构造例子）
# ---------------------------------------------------------------------------

def test_rank_ic_robust_to_factor_outlier():
    """1 只股票因子值被夸大 100 倍、其收益只是平庸（并列前二）：

      factor [1,2,3,100]  returns [1,2,3,3]
    皮尔逊被杠杆点拖到 ≈0.536；Spearman（位次 [1,2,3,4] vs [1,2,3.5,3.5]）：
    sxy=4.5, sxx=5, syy=4.5 → 4.5/√22.5 ≈ 0.9487。
    """
    f = [1.0, 2.0, 3.0, 100.0]
    r = [1.0, 2.0, 3.0, 3.0]
    assert factor_lab.ic(f, r) == pytest.approx(0.536, abs=0.01)
    assert factor_lab.rank_ic(f, r) == pytest.approx(4.5 / 22.5 ** 0.5, abs=1e-6)
    # 表达「几乎不变」：RankIC 仍 >0.9，IC 掉到 0.6 以下，两者差距 >0.3
    assert factor_lab.ic(f, r) < 0.6 < factor_lab.rank_ic(f, r)


# ---------------------------------------------------------------------------
# 3. ICIR 边界
# ---------------------------------------------------------------------------

def test_icir_known_answer_sample_std():
    # 均值 0.4；样本方差 = 0.16...; sample std (ddof=1) = 0.2581989
    assert factor_lab.icir([0.1, 0.3, 0.5, 0.7]) == pytest.approx(0.4 / 0.25819889, rel=1e-6)


def test_icir_std_zero_returns_zero_not_nan():
    """std=0：IC 全相同（哪怕全为正、一致性完美）。

    约定：返回 0.0，不返 NaN/inf。理由写在实现里；这里锁定行为：
    前端拿到 0.0 即「无证据」，不会渲染 NaN 断崖。
    """
    assert factor_lab.icir([0.3, 0.3, 0.3]) == 0.0
    assert factor_lab.icir([0.5]) == 0.0          # 样本不足
    assert factor_lab.icir([]) == 0.0


# ---------------------------------------------------------------------------
# 4. decay 结构
# ---------------------------------------------------------------------------

# 4 天 × 2 股票，因子与「次日收益」完全同构 → 1 期前瞻 IC=1，5 期因缺数据略过。
# · f(d1){A:2,B:1} → ret(d2){A:.10,B:.01}（高因子次日高收益）
# · f(d2){A:1,B:2} → ret(d3){A:.01,B:.10}
# · f(d3){A:2,B:1} → ret(d4){A:.10,B:.01}
# ret(d1) 故意与 f(d1) 反向：若 decay 错用当日收益会得到 IC=-1（见 MISS-3）。
_DECAY_FACTOR = {
    "d1": {"A": 2.0, "B": 1.0},
    "d2": {"A": 1.0, "B": 2.0},
    "d3": {"A": 2.0, "B": 1.0},
    "d4": {"A": 1.0, "B": 2.0},
}
_DECAY_RET = {
    "d1": {"A": 0.01, "B": 0.10},
    "d2": {"A": 0.10, "B": 0.01},
    "d3": {"A": 0.01, "B": 0.10},
    "d4": {"A": 0.10, "B": 0.01},
}


def test_decay_structure_and_perfect_case():
    out = factor_lab.decay(_DECAY_FACTOR, _DECAY_RET)
    assert set(out) == {1}            # 只有 period=1 有足够未来数据
    assert out[1] == pytest.approx(1.0)
    # 真数据级别：各 period 都有值时 keys = periods；所有 IC 落在 [-1,1]
    out2 = factor_lab.decay(_DECAY_FACTOR, _DECAY_RET, periods=(1, 2, 3))
    assert set(out2) == {1, 2, 3}
    assert all(-1.0 <= v <= 1.0 for v in out2.values())


# MISS-3 靶点：decay 用了【当日收益】而不是未来 N 日收益 → 本测试变红。
# 正确实现：forward(t)=未来 1 日收益=ret(d_{t+1})，与 f(t) 完美同向 → 1.0；
# 错误实现：用 ret(d_t)（与 f(t) 反向）→ -1.0。
def test_decay_uses_forward_not_same_day_return():
    assert factor_lab.decay(_DECAY_FACTOR, _DECAY_RET, periods=(1,))[1] == pytest.approx(1.0)
    # period=N 是 N 日前瞻【复合】收益。本构造里 2 日复合 A=1.1×1.01=B=1.01×1.1 打平
    # → 截面常数 → IC=0（而不是 1）；3 日复合 A=1.1×1.01×1.1 > B → IC=1。
    out = factor_lab.decay(_DECAY_FACTOR, _DECAY_RET, periods=(1, 2, 3))
    assert out[2] == pytest.approx(0.0)
    assert out[3] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 5. quantile_returns：已知答案 + 样本不足
# ---------------------------------------------------------------------------

def test_quantile_returns_known_answer():
    f = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    r = [0.50, 0.40, 0.30, 0.20, 0.10, 0.05, 0.04, 0.03, 0.02, 0.01]
    out = factor_lab.quantile_returns(f, r, q=5)
    assert [d["quantile"] for d in out] == [1, 2, 3, 4, 5]
    assert all(d["count"] == 2 for d in out)
    assert [d["mean_return"] for d in out] == pytest.approx([0.45, 0.25, 0.075, 0.035, 0.015])


# MISS-2 靶点：分位数分组方向反了（q=1 应含最低因子值）→ 本测试变红。
# 若方向翻转，Q1 会含最高因子的收益 0.01 而不是 0.45。
def test_quantile_direction_lowest_factor_is_q1():
    f = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    r = [0.50, 0.40, 0.30, 0.20, 0.10, 0.05, 0.04, 0.03, 0.02, 0.01]
    out = factor_lab.quantile_returns(f, r, q=5)
    q1 = next(d for d in out if d["quantile"] == 1)
    q5 = next(d for d in out if d["quantile"] == 5)
    assert q1["mean_return"] == pytest.approx(0.45)
    assert q5["mean_return"] == pytest.approx(0.015)


def test_quantile_returns_insufficient_sample():
    """3 只股票分 5 组：只返回非空桶；空桶不造 0 收益（0 会伪装成「这层赚了 0」）。

    分桶规则 floor(i*q/n)：i=0,1,2 → 桶 0,1,3（即 Q1,Q2,Q4），Q3/Q5 缺。
    """
    out = factor_lab.quantile_returns([3.0, 1.0, 2.0], [0.3, 0.1, 0.2], q=5)
    assert [d["quantile"] for d in out] == [1, 2, 4]
    assert [d["mean_return"] for d in out] == pytest.approx([0.1, 0.2, 0.3])
    assert all(d["count"] == 1 for d in out)


# ---------------------------------------------------------------------------
# 6. 缺失值：按【股票级 pairwise 丢弃】，不弃整日
# ---------------------------------------------------------------------------

def test_missing_values_drop_stock_not_day():
    """factor/ret 任一侧缺失的股票整只丢弃；其余股票照常成对 → IC 仍可算。

    若实现选择弃整日，这里剩下的合法截面 (1,1),(3,3) 会被清空 → 返回 0.0。
    锁定 1.0 即锁定我们的约定。
    """
    f = [1.0, None, 3.0, 4.0, float("nan")]
    r = [1.0, 9.0, 3.0, float("nan"), 9.9]
    assert factor_lab.ic(f, r) == pytest.approx(1.0)
    assert factor_lab.rank_ic(f, r) == pytest.approx(1.0)


def test_all_missing_cross_section_is_zero():
    assert factor_lab.ic([None, float("nan")], [1.0, 2.0]) == 0.0


# ---------------------------------------------------------------------------
# 7. 空输入不崩
# ---------------------------------------------------------------------------

def test_empty_inputs():
    assert factor_lab.ic([], []) == 0.0
    assert factor_lab.rank_ic([], []) == 0.0
    assert factor_lab.ic_series({}, {}) == []
    assert factor_lab.icir([]) == 0.0
    assert factor_lab.decay({}, {}) == {}
    assert factor_lab.quantile_returns([], [], q=5) == []
    assert factor_lab.turnover({}, q=5) == 0.0
    rep = factor_lab.report({}, {})
    assert rep["n_dates"] == 0
    assert rep["ic_series"] == []
    assert rep["decay"] == {}
    assert rep["ic_ir"] == 0.0


# ---------------------------------------------------------------------------
# ic_series / turnover / report
# ---------------------------------------------------------------------------

# 3 天 × 4 股票：d1 完美正向（IC=1）、d2 完美反向（IC=-1）、d3 正交（IC=0）。
_SERIES_FACTOR = {
    "d1": {"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0},
    "d2": {"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0},
    "d3": {"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0},
}
_SERIES_RET = {
    "d1": {"A": 0.1, "B": 0.2, "C": 0.3, "D": 0.4},
    "d2": {"A": 0.4, "B": 0.3, "C": 0.2, "D": 0.1},
    "d3": {"A": 1.0, "B": -1.0, "C": -1.0, "D": 1.0},
}


def test_ic_series_known_values_and_ordering():
    out = factor_lab.ic_series(_SERIES_FACTOR, _SERIES_RET)
    assert [d for d, _ in out] == ["d1", "d2", "d3"]
    assert [v for _, v in out] == pytest.approx([1.0, -1.0, 0.0])


def test_ic_series_rolling_window_skips_incomplete_head():
    """window=k 只输出凑满完整 k 期的尾端点，头部不输出部分窗口
    （避免把「样本不足的均值」画成真的低 IC）。"""
    raw = factor_lab.ic_series(_SERIES_FACTOR, _SERIES_RET)
    full = factor_lab.ic_series(_SERIES_FACTOR, _SERIES_RET, window=2)
    assert [d for d, _ in full] == ["d2", "d3"]
    assert [v for _, v in full] == pytest.approx([(1.0 - 1.0) / 2, (-1.0 + 0.0) / 2])
    window_too_big = factor_lab.ic_series(_SERIES_FACTOR, _SERIES_RET, window=5)
    assert window_too_big == []
    # window=None 语义 = 原始逐日 IC
    assert factor_lab.ic_series(_SERIES_FACTOR, _SERIES_RET) == raw


def test_turnover_known_answer():
    """q=2；n=3 → floor 分桶：d1 Q1={A,B} Q2={C}；d2 Q1={B,C} Q2={A}。
    换组：A、C，不变：B → 2/3。"""
    f = {
        "d1": {"A": 1.0, "B": 2.0, "C": 3.0},
        "d2": {"A": 3.0, "B": 2.0, "C": 1.0},
    }
    assert factor_lab.turnover(f, q=2) == pytest.approx(2 / 3)


def test_turnover_single_date_zero():
    assert factor_lab.turnover({"d1": {"A": 1.0, "B": 2.0}}, q=2) == 0.0


def test_report_shape():
    rep = factor_lab.report(_SERIES_FACTOR, _SERIES_RET)
    assert rep["n_dates"] == 3
    assert rep["ic_mean"] == pytest.approx(0.0)
    assert rep["ic_ir"] == pytest.approx(factor_lab.icir([1.0, -1.0, 0.0]))
    assert rep["rank_ic_mean"] == pytest.approx(0.0)
    assert [d for d, _ in rep["ic_series"]] == ["d1", "d2", "d3"]
    assert isinstance(rep["decay"], dict)
    assert 0.0 <= rep["turnover"] <= 1.0
    assert isinstance(rep["quantile_returns"], list)
    # report round 到 6 位（前端 payload 稳定性），空报告全零不崩
    empty = factor_lab.report({}, {})
    assert empty == {
        "n_dates": 0,
        "ic_mean": 0.0,
        "ic_std": 0.0,
        "ic_ir": 0.0,
        "rank_ic_mean": 0.0,
        "rank_ic_ir": 0.0,
        "ic_series": [],
        "rank_ic_series": [],
        "decay": {},
        "turnover": 0.0,
        "quantile_returns": [],
    }


# MISS-1 靶点：icir 的 std 用 population (ddof=0) 而 ICIR 契约用 sample (ddof=1)。
# sample: 0.4/0.2581989=1.5492；population: 0.4/0.2236068=1.7889 → 本测试变红。
def test_icir_uses_sample_std_not_population():
    assert factor_lab.icir([0.1, 0.3, 0.5, 0.7]) < 1.6  # population 会给 1.7889


# ---------------------------------------------------------------------------
# 注册与 renderer 白名单（只追加，不改校验逻辑）
# ---------------------------------------------------------------------------

_FACTORLAB_FNS = [
    "factorlab.ic_series",
    "factorlab.ic_decay",
    "factorlab.quantile_returns",
    "factorlab.quantile_heatmap",
]
_EXPECTED_RENDERER = {
    "factorlab.ic_series": "lwc",           # IC 时间序列 → 时间序列
    "factorlab.ic_decay": "lwc",            # 衰减曲线 → 时间序列（横轴为期限，见报告备注）
    "factorlab.quantile_returns": "echarts",  # 分层收益柱状图
    "factorlab.quantile_heatmap": "echarts",  # 分层收益热力图
}


def test_factorlab_fns_registered():
    for fn in _FACTORLAB_FNS:
        assert is_registered(fn), f"{fn} 未注册进 alpha.registry"


def test_renderer_by_fn_appended():
    """新增条目必须登记；且不能动既有条目（只追加）。"""
    for fn, expected in _EXPECTED_RENDERER.items():
        assert page_spec.RENDERER_BY_FN.get(fn) == expected
    # 旧条目原样保留
    assert page_spec.RENDERER_BY_FN["backtest.equity"] == "lwc"
    assert page_spec.RENDERER_BY_FN["backtest.drawdown"] == "lwc"
    assert page_spec.RENDERER_BY_FN["correlation.overlay"] == "echarts"
    assert page_spec.RENDERER_BY_FN["correlation.matrix"] == "echarts"
    assert page_spec.RENDERER_BY_FN["correlation.rolling"] == "echarts"


def test_validate_spec_accepts_factorlab_chart_blocks():
    """spec 校验：factorlab fn + 正确 renderer 通过；错 renderer 仍拒。"""
    good = {
        "slug": "factor-lab",
        "title": "因子实验室",
        "kind": "builtin",
        "layout": "stack",
        "blocks": [
            {"kind": "chart", "renderer": "lwc", "analysis_ref": {"fn": "factorlab.ic_series"}},
            {"kind": "chart", "renderer": "echarts",
             "analysis_ref": {"fn": "factorlab.quantile_returns"}},
        ],
    }
    assert page_spec.validate_spec(good) is good
    bad = {**good, "blocks": [
        {"kind": "chart", "renderer": "echarts", "analysis_ref": {"fn": "factorlab.ic_series"}}]}
    with pytest.raises(ValueError):
        page_spec.validate_spec(bad)


# ---------------------------------------------------------------------------
# 注册 fn 的数据管线（monkeypatch 假数据，无网络）
# ---------------------------------------------------------------------------

_DATES_40 = [f"2024-01-{d:02d}" for d in range(1, 11)] + \
            [f"2024-02-{d:02d}" for d in range(1, 11)] + \
            [f"2024-03-{d:02d}" for d in range(1, 21)]
# 价格路径：S1 单调向上（动量因子将持续为正），S2 锯齿（动量在正负之间跳）。
_S1 = [10.0 + 0.2 * i for i in range(40)]
_S2 = [20.0 + (0.5 if i % 2 == 0 else -0.3) for i in range(40)]


@pytest.fixture
def fake_lab_data(monkeypatch):
    fake = {
        "000001": list(zip(_DATES_40, _S1, strict=True)),
        "000002": list(zip(_DATES_40, _S2, strict=True)),
    }
    monkeypatch.setattr(
        factor_lab.data, "closes_with_dates",
        lambda code, count=250: list(fake[code]),
    )
    monkeypatch.setattr(factor_lab.data, "names", lambda codes: {c: c for c in codes})


def test_registered_ic_series_fn_produces_lwc_payload(fake_lab_data):
    entry = __import__("alpha.registry", fromlist=["get"]).get("factorlab.ic_series")
    option = entry.fn(symbols=["000001", "000002"], momentum=5, range="1y")
    assert chart.validate_option(option) is option
    pts = lwc.option_to_series(option)          # renderer=lwc 的实际消费路径
    assert pts, "IC 时间序列应能转出 LWC points"
    assert {s["name"] for s in pts} == {"IC(pearson)", "RankIC"}
    for s in pts:
        values = [p["value"] for p in s["points"]]
        assert all(-1.0001 <= v <= 1.0001 for v in values)


def test_registered_decay_and_quantile_fns(fake_lab_data):
    reg = __import__("alpha.registry", fromlist=["get"])
    dec = reg.get("factorlab.ic_decay").fn(symbols=["000001", "000002"], momentum=5, range="1y")
    assert chart.validate_option(dec) is dec
    assert "t+1" in [str(x) for x in dec["xAxis"]["data"]]

    bar = reg.get("factorlab.quantile_returns").fn(
        symbols=["000001", "000002"], momentum=5, range="1y")
    assert chart.validate_option(bar) is bar
    assert bar["series"][0]["type"] == "bar"
    assert len(bar["xAxis"]["data"]) == 5       # Q1..Q5

    hm = reg.get("factorlab.quantile_heatmap").fn(
        symbols=["000001", "000002"], momentum=5, range="1y")
    assert chart.validate_option(hm) is hm
    assert hm["series"][0]["type"] == "heatmap"
    assert hm["yAxis"]["data"] == ["Q1", "Q2", "Q3", "Q4", "Q5"]


def test_registered_fns_degrade_when_no_data(monkeypatch):
    """数据源不可用 → 空图不崩（与 backtest_page 同一约定）。"""
    monkeypatch.setattr(factor_lab.data, "closes_with_dates", lambda code, count=250: [])
    monkeypatch.setattr(factor_lab.data, "names", lambda codes: {c: c for c in codes})
    reg = __import__("alpha.registry", fromlist=["get"])
    for fn in _FACTORLAB_FNS:
        option = reg.get(fn).fn(symbols=["000001"], momentum=5, range="1y")
        assert isinstance(option, dict)
