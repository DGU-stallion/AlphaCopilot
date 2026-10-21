"""T45 page spec 校验测试 —— schema 形状 + analysis_ref.fn 白名单（任意代码执行防线）。

M2-7 起（ADR-0012 未决 1 / ADR-0014 §6）另校验 chart block 的 renderer 判别符：
  · kind=="chart" 必须显式声明 renderer ∈ {"lwc","echarts"}（不猜——猜错即两套实现）
  · 非 chart 块不允许带 renderer
  · chart.renderer 必须与 RENDERER_BY_FN 映射一致（fn 与 renderer 的绑定是白名单，
    不是自由字段）；已注册但未登记映射的 fn 拒收（要求先登记）
先 import alpha.factor / alpha.backtest_page 触发注册（注册在模块 import 副作用里）。
"""

import pytest

import alpha.backtest_page  # noqa: F401  —— 触发 backtest.* 注册
import alpha.factor  # noqa: F401  —— 触发 correlation.* 注册
from api.page_spec import RENDERER_BY_FN, normalize_spec, validate_spec


def _valid_spec() -> dict:
    return {
        "slug": "correlation",
        "title": "相关性分析",
        "kind": "builtin",
        "status": "published",
        "layout": "grid",
        "params": [
            {"name": "symbols", "type": "symbol_list", "label": "标的",
             "default": ["600519", "000858"], "max": 8},
        ],
        "blocks": [
            {"kind": "chart", "span": 2, "renderer": "echarts",
             "analysis_ref": {"fn": "correlation.overlay"}},
            {"kind": "chart", "span": 1, "renderer": "echarts",
             "analysis_ref": {"fn": "correlation.matrix"}},
        ],
    }


def test_valid_spec_passes():
    spec = _valid_spec()
    assert validate_spec(spec) is spec


def test_missing_required_field_rejected():
    spec = _valid_spec()
    del spec["blocks"]  # blocks 必填
    with pytest.raises(ValueError):
        validate_spec(spec)


def test_markdown_block_without_analysis_ref_passes():
    """非 analysis_ref 的 block（markdown text）不触发白名单校验。"""
    spec = _valid_spec()
    spec["blocks"] = [{"kind": "markdown", "text": "结论文字"}]
    assert validate_spec(spec) is spec


def test_unregistered_fn_rejected():
    """关键负向：analysis_ref.fn 为未注册名时必须被拒（任意代码执行防线）。"""
    spec = _valid_spec()
    spec["blocks"] = [
        {"kind": "chart", "renderer": "echarts", "analysis_ref": {"fn": "os.system"}},
    ]
    with pytest.raises(ValueError, match="未注册"):
        validate_spec(spec)


# ---------------------------------------------------------------------------
# M2-7：renderer 判别符（先写测试，后实现）
# ---------------------------------------------------------------------------

# 变异测试基准 fn：注册一个白名单内、但刻意不进 RENDERER_BY_FN 映射的测试 fn。
# 相当于现实中「新 fn 上线、忘了分类」的场景——必须拒收，不能默认放行。
def _m2_7_dummy(payload: dict) -> dict:
    return payload


@pytest.fixture(scope="module")
def unmapped_fn():
    from alpha.registry import register

    name = "test.m2_7.unmapped.chart"
    try:
        register(name, params=[])(lambda **_: {"chart": {}})
    except ValueError:
        pass  # 重复执行本模块时已注册
    return name


def test_valid_renderers_pass():
    """合法组合：LWC 语义一对、ECharts 语义一对，均通过。"""
    spec = {
        "slug": "mixed",
        "title": "混合",
        "kind": "user",
        "layout": "grid",
        "blocks": [
            {"kind": "chart", "span": 2, "renderer": "lwc",
             "analysis_ref": {"fn": "backtest.equity"}},
            {"kind": "chart", "span": 1, "renderer": "lwc",
             "analysis_ref": {"fn": "backtest.drawdown"}},
            {"kind": "chart", "span": 1, "renderer": "echarts",
             "analysis_ref": {"fn": "correlation.matrix"}},
            {"kind": "chart", "span": 1, "renderer": "echarts",
             "analysis_ref": {"fn": "correlation.overlay"}},
            {"kind": "metric", "span": 3, "analysis_ref": {"fn": "backtest.metrics"}},
        ],
    }
    assert validate_spec(spec) is spec


def test_chart_without_renderer_rejected():
    """chart 缺 renderer → 拒（允许默认即允许两套实现并存）。

    两边都验：lwc 语义 fn（backtest.equity）缺声明时也不能被「默认 lwc」
    类默许放行——否则 mutation 1 那种实现会被 mismatch 守门意外豁免。
    """
    spec = _valid_spec()
    del spec["blocks"][0]["renderer"]
    with pytest.raises(ValueError, match="renderer"):
        validate_spec(spec)

    spec2 = {
        "slug": "equity-no-renderer",
        "title": "回测",
        "kind": "user",
        "layout": "grid",
        "blocks": [{"kind": "chart", "analysis_ref": {"fn": "backtest.equity"}}],
    }
    with pytest.raises(ValueError, match="renderer"):
        validate_spec(spec2)


def test_renderer_mismatch_rejected():
    """renderer 与 fn 映射不一致 → 拒。热力图声明 LWC、净值声明 ECharts，双向都验。"""
    spec = _valid_spec()
    spec["blocks"][0] = {"kind": "chart", "span": 1, "renderer": "lwc",
                         "analysis_ref": {"fn": "correlation.matrix"}}
    with pytest.raises(ValueError, match="correlation.matrix"):
        validate_spec(spec)

    spec2 = {
        "slug": "bt-mismatch",
        "title": "回测",
        "kind": "user",
        "layout": "grid",
        "blocks": [{"kind": "chart", "renderer": "echarts",
                    "analysis_ref": {"fn": "backtest.equity"}}],
    }
    with pytest.raises(ValueError, match="backtest.equity"):
        validate_spec(spec2)


def test_renderer_on_non_chart_block_rejected():
    """非 chart 带 renderer → 拒（防噪音字段扩散）。"""
    for kind in ("metric", "table", "markdown"):
        spec = _valid_spec()
        spec["blocks"] = [{"kind": kind, "renderer": "echarts",
                           "analysis_ref": {"fn": "backtest.metrics"}}]
        with pytest.raises(ValueError, match="renderer"):
            validate_spec(spec)


def test_invalid_renderer_value_rejected():
    """renderer 只允许 lwc / echarts，其他值（拼错、大小写、未知名）一律拒。"""
    for bad in ("highcharts", "LWC", "", None):
        spec = _valid_spec()
        spec["blocks"][0]["renderer"] = bad
        with pytest.raises(ValueError, match="renderer"):
            validate_spec(spec)


def test_registered_fn_without_renderer_mapping_rejected(unmapped_fn):
    """已注册但未进 RENDERER_BY_FN 映射的 fn → 拒（要求先登记，不默认放行）。"""
    spec = _valid_spec()
    spec["blocks"] = [{"kind": "chart", "renderer": "echarts",
                       "analysis_ref": {"fn": unmapped_fn}}]
    with pytest.raises(ValueError, match="映射"):
        validate_spec(spec)


def test_renderer_mapping_covers_all_chart_fns():
    """映射表自身的一致性：每个映射里的 fn 必须已在 registry 注册（防映射漂移）。

    必须显式 import 各分析模块：它们的 fn 靠 import 副作用注册。
    少了任何一个，这条测试就会红 —— 而那是**测试环境**缺 import，
    不是映射真的漂移了。所以这里把「所有会往 RENDERER_BY_FN 里登记 fn 的
    模块」都 import 齐。
    """
    import alpha.attribution  # noqa: F401
    import alpha.backtest_page  # noqa: F401
    import alpha.factor  # noqa: F401
    import alpha.factor_lab  # noqa: F401
    import alpha.param_scan  # noqa: F401 —— paramscan.heatmap（M4-3）
    import alpha.tearsheet  # noqa: F401
    import alpha.walkforward  # noqa: F401
    from alpha import registry

    for fn in RENDERER_BY_FN:
        assert registry.is_registered(fn), f"RENDERER_BY_FN 里 {fn} 未注册（映射漂移）"


# ---------------------------------------------------------------------------
# M2-7：老 spec 兼容 —— 读时按映射表补全（normalize_spec），不写迁移脚本
# ---------------------------------------------------------------------------

def test_normalize_spec_fills_renderer_by_fn():
    """老 spec 无 renderer：chart 块按 RENDERER_BY_FN 补全；非 chart 不动。"""
    spec = {
        "slug": "legacy",
        "title": "旧页",
        "kind": "user",
        "layout": "grid",
        "blocks": [
            {"kind": "chart", "span": 2, "analysis_ref": {"fn": "backtest.equity"}},
            {"kind": "chart", "span": 1, "analysis_ref": {"fn": "correlation.matrix"}},
            {"kind": "chart", "span": 1, "analysis_ref": {"fn": "os.system"}},  # 未注册：留白，不补
            {"kind": "metric", "analysis_ref": {"fn": "backtest.metrics"}},     # 非 chart：不补
        ],
    }
    out = normalize_spec(spec)
    assert out["blocks"][0]["renderer"] == "lwc"
    assert out["blocks"][1]["renderer"] == "echarts"
    assert "renderer" not in out["blocks"][2]
    assert "renderer" not in out["blocks"][3]


def test_normalize_spec_idempotent_and_not_mutating():
    """补全幂等，且不改原 dict（读路径安全加固）。"""
    spec = {"slug": "x", "title": "x", "kind": "user", "layout": "grid",
            "blocks": [{"kind": "chart", "analysis_ref": {"fn": "correlation.overlay"}}]}
    snapshot = [dict(b) for b in spec["blocks"]]
    out1 = normalize_spec(spec)
    out2 = normalize_spec(out1)
    assert out1["blocks"][0]["renderer"] == "echarts"
    assert out2["blocks"][0]["renderer"] == "echarts"
    assert spec["blocks"] == snapshot


def test_legacy_spec_without_renderer_fails_validation():
    """写路径不因 normalize 而放宽：validate_spec 仍要求显式声明（只有读路径补全）。"""
    spec = _valid_spec()
    del spec["blocks"][0]["renderer"]
    with pytest.raises(ValueError):
        validate_spec(spec)
