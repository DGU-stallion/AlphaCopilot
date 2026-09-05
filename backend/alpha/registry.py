"""分析函数注册表（ADR-0007）——**契约桩，签名已定稿，实现见 T44**。

安全边界（不可协商）：page spec 的 `analysis_ref.fn` 是字符串键，只能经本注册表
解析为函数。**禁止 importlib / eval 动态解析**——AI 能建 draft spec，动态解析等于
把任意代码执行权交给幻觉。未注册的 fn 一律拒收（get 抛 KeyError → api 层转 400）。

用法（T42 相关性分析在 alpha/factor.py 里注册）：

    from alpha.registry import register, ParamSpec

    @register(
        "correlation.overlay",
        params=[
            ParamSpec("symbols", "symbol_list", default=["600519"], max_len=8),
            ParamSpec("range", "date_range", default="1y"),
        ],
    )
    def correlation_overlay(symbols: list[str], range: str) -> dict:
        '''归一化叠加走势图，返回 ECharts option。'''
        ...

渲染时：api 层 get(fn) → 用 ParamSpec 校验并强转参数 → 调函数 → 得 option JSON。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# 支持的参数类型（对应前端自动生成的控件）。
PARAM_TYPES = ("symbol_list", "int", "float", "date_range", "str", "enum")


@dataclass
class ParamSpec:
    """一个参数的规格：类型 + 默认值 + 取值域。用于校验与前端控件生成。"""

    name: str
    type: str
    default: Any = None
    label: str = ""
    min: float | None = None          # int/float 下界
    max: float | None = None          # int/float 上界
    max_len: int | None = None        # symbol_list 最大长度
    choices: list[str] | None = None  # enum 可选值

    def __post_init__(self) -> None:
        if self.type not in PARAM_TYPES:
            raise ValueError(f"未知参数类型: {self.type}（支持 {PARAM_TYPES}）")

    def coerce(self, value: Any) -> Any:
        """校验并强转一个传入值；非法抛 ValueError（api 层转 400）。

        各类型规则：
          symbol_list: 必须是 list，每个元素是 6 位数字字符串；有 max_len 则限长。
          int/float:   可强转为数值，且在 [min, max]（若设）闭区间内。
          date_range:  预设 '1y'/'6m'/'3m'，或 'YYYY-MM-DD:YYYY-MM-DD' 的 ISO 起止。
          enum:        必须在 choices 内。
          str:         强转为 str。
        非法（类型错/越界/格式错）一律抛 ValueError。
        """
        if self.type == "symbol_list":
            return self._coerce_symbol_list(value)
        if self.type == "int":
            return self._coerce_number(value, int)
        if self.type == "float":
            return self._coerce_number(value, float)
        if self.type == "date_range":
            return self._coerce_date_range(value)
        if self.type == "enum":
            return self._coerce_enum(value)
        # str
        return str(value)

    def _coerce_symbol_list(self, value: Any) -> list[str]:
        if not isinstance(value, (list, tuple)):
            raise ValueError(f"{self.name}: 期望标的列表，得到 {type(value).__name__}")
        codes = [str(v) for v in value]
        for c in codes:
            if not (len(c) == 6 and c.isdigit()):
                raise ValueError(f"{self.name}: 非法标的代码 {c!r}（须 6 位数字）")
        if self.max_len is not None and len(codes) > self.max_len:
            raise ValueError(f"{self.name}: 标的数 {len(codes)} 超上限 {self.max_len}")
        return codes

    def _coerce_number(self, value: Any, cast):
        try:
            n = cast(value)
        except (TypeError, ValueError) as e:
            raise ValueError(f"{self.name}: 无法转为 {cast.__name__}: {value!r}") from e
        if self.min is not None and n < self.min:
            raise ValueError(f"{self.name}: {n} 小于下界 {self.min}")
        if self.max is not None and n > self.max:
            raise ValueError(f"{self.name}: {n} 大于上界 {self.max}")
        return n

    def _coerce_date_range(self, value: Any) -> str:
        if value in ("1y", "6m", "3m"):
            return value
        if isinstance(value, str) and ":" in value:
            from datetime import date

            start, sep, end = value.partition(":")
            try:
                date.fromisoformat(start)
                date.fromisoformat(end)
            except ValueError as e:
                raise ValueError(f"{self.name}: 非法 ISO 日期区间 {value!r}") from e
            return value
        raise ValueError(
            f"{self.name}: 非法区间 {value!r}（预设 1y/6m/3m 或 'YYYY-MM-DD:YYYY-MM-DD'）"
        )

    def _coerce_enum(self, value: Any) -> str:
        v = str(value)
        if not self.choices or v not in self.choices:
            raise ValueError(f"{self.name}: {v!r} 不在可选值 {self.choices} 内")
        return v


@dataclass
class RegisteredFn:
    fn: Callable[..., dict]
    params: list[ParamSpec] = field(default_factory=list)


_REGISTRY: dict[str, RegisteredFn] = {}


def register(name: str, *, params: list[ParamSpec] | None = None):
    """装饰器：把分析函数登记进白名单。name 即 spec 里的 analysis_ref.fn。"""

    def deco(fn: Callable[..., dict]) -> Callable[..., dict]:
        if name in _REGISTRY:
            raise ValueError(f"分析函数重复注册: {name}")
        _REGISTRY[name] = RegisteredFn(fn=fn, params=list(params or []))
        return fn

    return deco


def get(name: str) -> RegisteredFn:
    """取已注册函数；未注册抛 KeyError（api 层据此拒收 spec）。"""
    return _REGISTRY[name]


def is_registered(name: str) -> bool:
    return name in _REGISTRY


def all_names() -> list[str]:
    return sorted(_REGISTRY)
