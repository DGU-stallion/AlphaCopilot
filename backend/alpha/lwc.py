"""净值 / 回撤的时间序列整形（M2-6，派生自 ECharts option）。

为什么需要这个：backtest.equity / backtest.drawdown 按 ADR-0014 §6 应走
Lightweight Charts（金融时间序列：金融坐标轴、十字光标、缩放联动），
但现有 analysis fn 产出的是 ECharts option。前端拿 option 画 LWC 只有两条路：

  ① 在前端解析 ECharts option（series[].data + xAxis.data）—— 脆：option 是
     渲染层结构，任何样式改动都可能顺带改坏数据通路；而且「后端产 option、
     前端反解」本身就是错的方向（ADR-0012：数字与图形契约分离）。
  ② 后端在 renderer=lwc 时额外产出**时间序列载荷** `series: [{name, points}]`，
     前端直接吃 points。option 仍然给（向后兼容 ECharts 消费方）。

这里选 ②。解析仍然只发生在一处（后端），且解析的是我们自己产出的 option 结构，
只依赖 series[].data / name 与 xAxis.data 三个字段。
"""
from __future__ import annotations

from typing import Any


def _as_label_list(x: Any) -> list[str]:
    """取出横轴类目。xAxis 可能是对象或数组（多轴），data 可能是空。"""
    axes = x if isinstance(x, list) else [x]
    for ax in axes:
        if isinstance(ax, dict):
            data = ax.get("data")
            if isinstance(data, list) and data:
                return [str(v) for v in data]
    return []


def option_to_series(option: Any) -> list[dict[str, Any]]:
    """把 ECharts line option 转成 [{name, points:[{time, value}]}]。

    规则：
      - 只认能对齐到横轴的数值；长度不匹配的系列整条丢弃（宁可少画一条，
        也不要把错位的数据画上去 —— 错位的净值曲线比没有曲线更危险）
      - 非有限数（None/NaN/Infinity）对应的点直接跳过，不补 0
        （补 0 会在曲线上造出一个假的断崖）
      - 时间轴严格递增去重（LWC 的内部断言要求）
    """
    if not isinstance(option, dict):
        return []
    times = _as_label_list(option.get("xAxis"))
    if not times:
        return []
    series = option.get("series")
    if not isinstance(series, list):
        return []

    out: list[dict[str, Any]] = []
    for s in series:
        if not isinstance(s, dict):
            continue
        data = s.get("data")
        if not isinstance(data, list) or not data:
            continue
        # 长度必须与横轴一致，否则说明 series 与 xAxis 不同源
        if len(data) != len(times):
            continue
        points: dict[str, float] = {}
        # strict=True：上面已确认 len(data) == len(times)，这里再让不匹配直接抛错
        for t, v in zip(times, data, strict=True):
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                continue
            val = float(v)
            if val != val or val in (float("inf"), float("-inf")):
                continue
            points[t] = val
        if not points:
            continue
        out.append({
            "name": str(s.get("name") or ""),
            "points": [
                {"time": t, "value": points[t]}
                for t in sorted(points)
            ],
        })
    return out


def lwc_payload(option: Any) -> dict[str, Any]:
    """renderer=lwc 的 chart 块载荷。

    `series` 是各系列的 {time,value} 序列（pane 0 用第一个/前几个）；
    `drawdown` 是第一条系列的回撤（相对历史最高点的百分比，≤0）。

    回撤在这里算而不是让前端算：一是前端算等于把确定性计算搬到 UI 层
    （违反硬规则 6）；二是净值与回撤必须来自同一条序列，分开算容易错位。
    """
    series = option_to_series(option)
    drawdown: list[dict[str, Any]] = []
    if series:
        base = series[0]["points"]
        peak = float("-inf")
        dd: list[dict[str, Any]] = []
        for p in base:
            v = p["value"]
            if v > peak:
                peak = v
            # peak 为 0 或负时没法算比率（净值不会这样，但防御）
            if peak > 0:
                dd.append({"time": p["time"], "value": (v - peak) / peak})
        drawdown = dd
    return {"series": series, "drawdown": drawdown}
