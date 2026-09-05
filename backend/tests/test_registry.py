"""T44 alpha.registry —— 白名单注册表 + ParamSpec.coerce 校验（安全边界）。

安全边界（ADR-0007，不可协商）：analysis_ref.fn 只能经白名单解析；参数值经 ParamSpec
校验/强转，越界或类型错必须拒收（api 层转 400）。负向断言是这里的主角——它们守护的是
「AI 幻觉产出的 draft spec 不能带着非法参数进业务层」。
"""

import pytest

from alpha import registry
from alpha.registry import ParamSpec


def test_duplicate_registration_rejected():
    name = "test.dup.fn"
    # 直接操作模块级注册表以隔离用例（不污染真实注册）
    registry._REGISTRY.pop(name, None)

    @registry.register(name)
    def _fn() -> dict:
        return {}

    with pytest.raises(ValueError, match="重复注册"):
        @registry.register(name)
        def _fn2() -> dict:
            return {}

    registry._REGISTRY.pop(name, None)


def test_get_unregistered_raises_keyerror():
    with pytest.raises(KeyError):
        registry.get("no.such.fn.__nope__")


# ---- symbol_list ----

def test_coerce_symbol_list_ok():
    spec = ParamSpec("symbols", "symbol_list", max_len=3)
    assert spec.coerce(["600519", "000858"]) == ["600519", "000858"]


def test_coerce_symbol_list_too_long_rejected():
    spec = ParamSpec("symbols", "symbol_list", max_len=2)
    with pytest.raises(ValueError):
        spec.coerce(["600519", "000858", "601318"])


def test_coerce_symbol_list_bad_code_rejected():
    spec = ParamSpec("symbols", "symbol_list", max_len=8)
    with pytest.raises(ValueError):
        spec.coerce(["600519", "ABC"])       # 非 6 位数字
    with pytest.raises(ValueError):
        spec.coerce("600519")                 # 不是 list


# ---- int ----

def test_coerce_int_ok_and_bounds():
    spec = ParamSpec("window", "int", min=5, max=250)
    assert spec.coerce("60") == 60
    assert spec.coerce(5) == 5


def test_coerce_int_out_of_range_rejected():
    spec = ParamSpec("window", "int", min=5, max=250)
    with pytest.raises(ValueError):
        spec.coerce(4)
    with pytest.raises(ValueError):
        spec.coerce(251)


def test_coerce_int_type_error_rejected():
    spec = ParamSpec("window", "int")
    with pytest.raises(ValueError):
        spec.coerce("abc")


# ---- float ----

def test_coerce_float_ok_and_bounds():
    spec = ParamSpec("threshold", "float", min=0.0, max=1.0)
    assert spec.coerce("0.5") == 0.5


def test_coerce_float_out_of_range_rejected():
    spec = ParamSpec("threshold", "float", min=0.0, max=1.0)
    with pytest.raises(ValueError):
        spec.coerce(1.5)


# ---- date_range ----

def test_coerce_date_range_presets():
    spec = ParamSpec("range", "date_range")
    for preset in ("1y", "6m", "3m"):
        assert spec.coerce(preset) == preset


def test_coerce_date_range_iso_ok():
    spec = ParamSpec("range", "date_range")
    assert spec.coerce("2024-01-01:2024-12-31") == "2024-01-01:2024-12-31"


def test_coerce_date_range_invalid_rejected():
    spec = ParamSpec("range", "date_range")
    with pytest.raises(ValueError):
        spec.coerce("5y")                     # 非法预设
    with pytest.raises(ValueError):
        spec.coerce("2024-13-01:2024-12-31")  # 非法月份


# ---- enum ----

def test_coerce_enum_ok():
    spec = ParamSpec("mode", "enum", choices=["a", "b"])
    assert spec.coerce("a") == "a"


def test_coerce_enum_out_of_choices_rejected():
    spec = ParamSpec("mode", "enum", choices=["a", "b"])
    with pytest.raises(ValueError):
        spec.coerce("c")


# ---- str ----

def test_coerce_str_ok():
    spec = ParamSpec("label", "str")
    assert spec.coerce("hello") == "hello"
    assert spec.coerce(123) == "123"
