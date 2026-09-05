"""T45 page spec 校验测试 —— schema 形状 + analysis_ref.fn 白名单（任意代码执行防线）。

先 import alpha.factor 确保 correlation.* 已注册（注册在模块 import 副作用里）。
"""

import pytest

import alpha.factor  # noqa: F401  —— 触发 correlation.* 注册
from api.page_spec import validate_spec


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
            {"kind": "chart", "span": 2, "analysis_ref": {"fn": "correlation.overlay"}},
            {"kind": "chart", "span": 1, "analysis_ref": {"fn": "correlation.matrix"}},
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
        {"kind": "chart", "analysis_ref": {"fn": "os.system"}},
    ]
    with pytest.raises(ValueError, match="未注册"):
        validate_spec(spec)
