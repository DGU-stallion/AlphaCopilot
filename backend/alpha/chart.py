"""alpha.chart —— ECharts option 契约 + helper（T32）。

图表默认产 ECharts option JSON（可交互：legend/hover/dataZoom），由这些 helper 生成，
前端 ChartBlock 直接 setOption 渲染。颜色/主题不在这里写死（前端 chart-theme.ts 注入），
本模块只产结构化 option。

四个 helper：line / bar / heatmap（相关性，E2E-1）/ candlestick（K 线，E2E-2）。
每个产出的 option 都能通过 validate_option；非法 option 被 validate_option 拒绝。

docstring 即 LLM schema：agent 通过 run_python 调这些 helper 画图，docstring 要讲清参数。
"""

from __future__ import annotations

from typing import Any

from jsonschema import Draft7Validator, ValidationError

# ---- ECharts option 契约（最小充分集，够校验 4 类图不畸形）----
# 要求：有 series（非空数组），每个 series 有 type，且 type ∈ 支持集合。
_OPTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["series"],
    "properties": {
        "title": {"type": "object"},
        "tooltip": {"type": "object"},
        "legend": {"type": "object"},
        "grid": {"type": "object"},
        "xAxis": {"type": ["object", "array"]},
        "yAxis": {"type": ["object", "array"]},
        "visualMap": {"type": ["object", "array"]},
        "dataZoom": {"type": "array"},
        "series": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["type"],
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["line", "bar", "heatmap", "candlestick", "scatter"],
                    }
                },
            },
        },
    },
    "additionalProperties": True,
}

_VALIDATOR = Draft7Validator(_OPTION_SCHEMA)


def validate_option(option: dict[str, Any]) -> dict[str, Any]:
    """校验 option 是否符合契约；不符抛 ValueError（业务层不信任 agent 输出）。

    返回原 option（校验通过），方便链式使用。
    """
    try:
        _VALIDATOR.validate(option)
    except ValidationError as e:
        raise ValueError(f"非法 ECharts option: {e.message}") from e
    return option


def _tooltip(trigger: str = "axis") -> dict[str, Any]:
    return {"trigger": trigger}


def line(
    x: list[Any],
    series: dict[str, list[float]],
    *,
    title: str = "",
) -> dict[str, Any]:
    """折线图。

    x: 横轴类目（如日期列表）；series: {系列名: 数值列表}（长度应与 x 对齐）。
    产出带 legend（多系列可切换）、tooltip（axis 十字对齐）、dataZoom（可缩放）的 option。
    """
    return validate_option({
        "title": {"text": title},
        "tooltip": _tooltip("axis"),
        "legend": {"data": list(series.keys())},
        "grid": {"left": 48, "right": 24, "top": 48, "bottom": 56, "containLabel": True},
        "xAxis": {"type": "category", "data": list(x), "boundaryGap": False},
        "yAxis": {"type": "value", "scale": True},
        "dataZoom": [{"type": "inside"}, {"type": "slider"}],
        "series": [
            {"name": name, "type": "line", "data": vals, "showSymbol": False}
            for name, vals in series.items()
        ],
    })


def bar(
    x: list[Any],
    series: dict[str, list[float]],
    *,
    title: str = "",
) -> dict[str, Any]:
    """柱状图。参数同 line；产出带 legend/tooltip 的柱状 option。"""
    return validate_option({
        "title": {"text": title},
        "tooltip": _tooltip("axis"),
        "legend": {"data": list(series.keys())},
        "grid": {"left": 48, "right": 24, "top": 48, "bottom": 40, "containLabel": True},
        "xAxis": {"type": "category", "data": list(x)},
        "yAxis": {"type": "value", "scale": True},
        "series": [
            {"name": name, "type": "bar", "data": vals}
            for name, vals in series.items()
        ],
    })


def heatmap(
    labels: list[str],
    matrix: list[list[float]],
    *,
    title: str = "",
    vmin: float = -1.0,
    vmax: float = 1.0,
) -> dict[str, Any]:
    """相关性热力图（E2E-1 用）。

    labels: N 个标的名；matrix: N×N 相关系数矩阵（对称，对角=1）。
    产出 heatmap option：visualMap 连续色阶（vmin..vmax，默认 [-1,1] 相关系数域），
    每格显示数值，tooltip item 触发。
    """
    n = len(labels)
    if len(matrix) != n or any(len(row) != n for row in matrix):
        raise ValueError(f"matrix 必须是 {n}×{n} 方阵")
    data = [
        [j, i, round(float(matrix[i][j]), 4)]
        for i in range(n)
        for j in range(n)
    ]
    return validate_option({
        "title": {"text": title},
        "tooltip": _tooltip("item"),
        "grid": {"left": 80, "right": 24, "top": 48, "bottom": 80, "containLabel": True},
        "xAxis": {"type": "category", "data": list(labels), "splitArea": {"show": True}},
        "yAxis": {"type": "category", "data": list(labels), "splitArea": {"show": True}},
        "visualMap": {
            "min": vmin,
            "max": vmax,
            "calculable": True,
            "orient": "horizontal",
            "left": "center",
            "bottom": 16,
        },
        "series": [
            {
                "name": "相关系数",
                "type": "heatmap",
                "data": data,
                "label": {"show": True},
            }
        ],
    })


def candlestick(
    dates: list[str],
    ohlc: list[list[float]],
    *,
    title: str = "",
    overlays: dict[str, list[float]] | None = None,
) -> dict[str, Any]:
    """K 线图（E2E-2 用）。

    dates: 日期列表；ohlc: 每行 [open, close, low, high]（ECharts candlestick 约定顺序）。
    overlays: 可选叠加线（如 {'MA20': [...], 'MA60': [...]}，长度与 dates 对齐），
    用于展示均线/金叉。产出带 dataZoom（可缩放看长周期）的 option。
    """
    if any(len(row) != 4 for row in ohlc):
        raise ValueError("ohlc 每行必须是 [open, close, low, high] 四个值")
    series: list[dict[str, Any]] = [
        {"name": "K线", "type": "candlestick", "data": ohlc}
    ]
    legend = ["K线"]
    for name, vals in (overlays or {}).items():
        series.append({"name": name, "type": "line", "data": vals, "showSymbol": False,
                       "smooth": True})
        legend.append(name)
    return validate_option({
        "title": {"text": title},
        "tooltip": _tooltip("axis"),
        "legend": {"data": legend},
        "grid": {"left": 48, "right": 24, "top": 48, "bottom": 56, "containLabel": True},
        "xAxis": {"type": "category", "data": list(dates)},
        "yAxis": {"type": "value", "scale": True},
        "dataZoom": [{"type": "inside"}, {"type": "slider"}],
        "series": series,
    })
