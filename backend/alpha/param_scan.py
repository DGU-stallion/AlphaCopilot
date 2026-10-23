"""alpha.param_scan —— 参数扫描（M4-3，vectorbt 式）：网格回测 + 热力图 + 参数高原。

一次跑 100+ 组（fast, slow）参数，产出热力图与「最优解是否稳健」的判定。
纯计算层：只用标准库，不 import 框架，不读 env。引擎可注入（scan(engine=...)）。

════════ 设计约定（测试锁定，改动需同步改测试）════════

1. **fast >= slow 的组合必须跳过并记录，不许算。**
   双均线策略里 fast >= slow 是无效策略（两均线合一或恒序，金叉定义退化，
   信号恒定），算出来的指标（比如恒空仓的 sharpe=0、或噪声驱动的偶发高分）
   会**污染热力图的真实分布**——它不是「差」，是「无意义」，两者要分开看。

2. **单组合失败不中断整次扫描。**
   引擎抛错（数据不足 / gate 拒收 / 除零）只损失这一格，记账进 failed 继续跑。
   「一格失败 → 全部报废」是扫描工具最不可容忍的行为：100 组里 1 组坏数据
   不应该让其余 99 组的工作白付。**但不能静默丢**——失败会写出热力图上的
   空洞，空洞比错误数字安全（**宁可留白，不可撒谎**，同 tearsheet 口径）。

3. **best() 必须排除交易次数不足的组合。**
   「只交易 1 次但踩中了一段大行情」的组合，sharpe/收益可以无限高——那不是
   策略好，是**样本太少导致方差估计失效**（日收益序列里 0 占比过高反而
   稀释抬高 sharpe）。低于 min_trades（默认 3）的组合不许进 top N。

4. **stability() 回答「这是参数高原还是参数孤岛」。**
   定义见 stability() docstring：核心是**用网格邻域模拟参数不确定性**——
   「你料到的最优参数」在未来真实数据上等价于「你邻近的参数」；如果最优点的
   邻居们也都好，说明优势来自策略结构（高原，可依赖）；如果邻居都塌下去，
   说明那点优势是噪声恰好落在这一格（孤岛，过拟合的陷阱）。
   不用「全网格均值/方差」当稳健性：那回答的是「策略整体普适吗」，不是
   「**这个候选最优解**敢不敢用」——本模块 100% 是为后者服务的。

5. **热力图颜色必须正负双向（红涨绿跌），不许单向渐变。**
   metric 可正可负（sharpe、total_return），单向渐变会让负值和「没数据」
   视觉同质；双向色阶（绿↔白↔红）的**白**才是「无差异」，负值一眼可辨。
   色值沿用 frontend/src/theme/tokens.ts LIGHT 口径的 up/down（后端拿不到
   token 引用，复制并注明真源；国际口径切换由前端 themed() 管理）。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from alpha import backtest_engine as be
from alpha import chart, data
from alpha.registry import ParamSpec, register

# best() 的最低交易次数门槛（约定 3；测试锁定）。
_MIN_TRADES = 3

# stability() 的判定阈值（约定 4；测试锁定）：邻居平均保留≥70% → plateau；
# ≤30% → island；之间 → mixed（脊/坡）。不用中点 0.5：一口气丢 50% 的邻居
# 表现已不可用，70% 才敢说「结构还在」；30% 以下是纯噪声才有的塌法。
_PLATEAU_THRESHOLD = 0.7
_ISLAND_THRESHOLD = 0.3


# ── 引擎（可注入）────────────────────────────────────────────────────

def _dual_ma_engine(
    closes: list[float],
    dates: list[str] | None,
    *,
    fast: int,
    slow: int,
    **kwargs: Any,
) -> Any:
    """默认引擎：backtest_engine 的双均线金叉策略。

    kwargs 直接透传给 be.run（code / initial_cash / risk_free）；code 缺省按
    主板 ±10% 处理（占位，不省略——be.run 需要 code 判涨跌停）。
    """
    kwargs.setdefault("code", "000000")
    signal = be.golden_cross_signal(closes, fast, slow)
    return be.run(kwargs.pop("code"), closes, signal, dates=dates, **kwargs)


def _metrics_of(res: Any) -> dict[str, Any] | None:
    """统一取指标：引擎可返回带 .metrics 属性的对象或纯 dict；两者之外视为无效。"""
    if hasattr(res, "metrics"):
        m = res.metrics
    elif isinstance(res, dict):
        m = res
    else:
        return None
    return m if isinstance(m, dict) else None


# ── 核心 API ────────────────────────────────────────────────────────

def scan(
    closes: list[float],
    dates: list[str] | None,
    *,
    fast_grid: list[int],
    slow_grid: list[int],
    metric: str = "sharpe",
    engine: Callable[..., Any] | None = None,
    **engine_kwargs: Any,
) -> dict[str, Any]:
    """网格扫描：对每个 fast < slow 的组合跑一次回测，收集指标 + 失败清单。

    engine(closes, dates, fast=, slow=, **engine_kwargs) -> 回测结果
    （带 .metrics 属性的对象，或 metrics dict）。缺省用 backtest_engine 双均线。

    返回：{"grid": [...], "metric": .., "combos": .., "failed": [...]}
    failed 里 fast >= slow 与引擎异常都算，reason 写明差别。
    """
    if engine is None:
        engine = _dual_ma_engine

    fasts = sorted({int(f) for f in fast_grid})
    slows = sorted({int(s) for s in slow_grid})
    total = len(fasts) * len(slows)

    grid: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for f in fasts:
        for s in slows:
            combo = {"fast": f, "slow": s}
            if f >= s:  # 约定 1：无效策略不算数，但不能静默丢
                failed.append({**combo, "reason": f"fast({f}) >= slow({s})：无效组合"})
                continue
            try:
                res = engine(closes, dates, fast=f, slow=s, **engine_kwargs)
            except Exception as e:  # 约定 2：一格失败不断整次；捕获 Exception for 规模扫描
                failed.append({**combo, "reason": str(e) or type(e).__name__})
                continue
            m = _metrics_of(res)
            if m is None or metric not in m:
                failed.append({**combo, "reason": f"指标 {metric!r} 缺失"})
                continue
            grid.append({
                **combo,
                "metrics": {k: float(v) for k, v in m.items()},
            })

    return {"grid": grid, "metric": metric, "combos": total, "failed": failed}


def best(
    result: dict[str, Any],
    *,
    n: int = 5,
    min_trades: int = _MIN_TRADES,
) -> list[dict[str, Any]]:
    """前 n 组候选（约定 3：排除交易次数 < min_trades 的样本）。

    返回 [{"fast", "slow", "value", "metrics"}]，按 metric 从高到低。
    """
    metric = result["metric"]
    pool = [
        entry for entry in result["grid"]
        if entry["metrics"].get("trade_count", 0) >= min_trades
        and metric in entry["metrics"]
    ]
    pool.sort(key=lambda e: e["metrics"][metric], reverse=True)
    return [
        {
            "fast": e["fast"],
            "slow": e["slow"],
            "value": e["metrics"][metric],
            "metrics": e["metrics"],
        }
        for e in pool[:n]
    ]


def stability(result: dict[str, Any]) -> dict[str, Any]:
    """判定最优点是「参数高原」还是「参数孤岛」。

    ── 为什么这样定义（本任务最有价值的部分）──

    用**网格邻域**模拟参数不确定性：你不会把最优参数原样搬进未来，实践中
    参数是估计出来的，未来数据上的「真实好参数」分布在你所选点的邻域里。
    所以问题从「最优点分数多高」变成「**最优点周围一圈还站得住吗**」。

    · 高原（plateau）：优势来自策略结构 —— 参数怎么浮动都还有效。三年样本
      有限、引擎有噪声，任何网格都是从一个大面里采样，**平坦的顶部说明
      「好」不是这一格的巧合，而是一个趋势**。这种最优解才敢用。
    · 孤岛（island）：优势来自噪声恰好落进这一格。换个参数（哪怕只动一档）
      崩掉 —— 正是过拟合最经典的形状。**这是参数扫描最危险的输出**：热力图
      上它是亮的，但它比邻域里平庸的格子更危险，因为它伪装成「最优」。

    不用全网格均值/方差：那衡量「这套策略普适吗」（稳/不稳整体），而我们要
    回答的是「**这个具体最优解**敢不敢上线」。一个整体平庸但顶部平坦的网格，
    比整体亮眼但顶部尖峰的网格更可用 —— 全网格统计会把这两者的结论弄反。

    实现：对每个格点取 min-max 归一化相对排名 score（回避 metric 可能
    为 0/负导致的 ratio 翻转），取 best 的 4-邻域（格序相邻，±1 档），
    邻居均值 score 高 → plateau，低 → island，中间 → mixed。
    邻居不足（唯一点 / 单行网格）→ "unknown"，不硬给结论。
    """
    metric = result["metric"]
    values: dict[tuple[int, int], float] = {
        (e["fast"], e["slow"]): e["metrics"][metric] for e in result["grid"]
    }
    if not values:
        return {
            "metric": metric,
            "best": None,
            "verdict": "unknown",
            "neighbor_mean_score": None,
            "neighbors": [],
            "note": "网格为空，无法判定",
        }
    if len(values) == 1:
        f, s = next(iter(values))
        return {
            "metric": metric,
            "best": {"fast": f, "slow": s, "value": values[(f, s)]},
            "verdict": "unknown",
            "neighbor_mean_score": None,
            "neighbors": [],
            "note": "只有一个有效组合，没有邻域可比",
        }

    vmax, vmin = max(values.values()), min(values.values())
    span = vmax - vmin
    if span < 1e-12:
        return {
            "metric": metric,
            "best": None,
            "verdict": "unknown",
            "neighbor_mean_score": None,
            "neighbors": [],
            "note": "全部组合指标相同，无差异可比",
        }

    def score(v: float) -> float:
        return (v - vmin) / span

    best_key = max(values, key=values.__getitem__)
    bf, bs = best_key
    fasts = sorted({f for f, _ in values})
    slows = sorted({s for _, s in values})

    neighbors: list[dict[str, Any]] = []
    # 「邻域」 = 网格序上的相邻格：网格步长不一定为 1（如 20→30→60），
    # 所以按排序位次 ±1 取，表示「参数往邻近档位动一格」。
    fi, si = fasts.index(bf), slows.index(bs)
    for f in (fasts[fi - 1] if fi > 0 else None, fasts[fi + 1] if fi + 1 < len(fasts) else None):
        if f is not None and (f, bs) in values:
            neighbors.append({"fast": f, "slow": bs, "value": values[(f, bs)],
                              "score": round(score(values[(f, bs)]), 4)})
    for s in (slows[si - 1] if si > 0 else None, slows[si + 1] if si + 1 < len(slows) else None):
        if s is not None and (bf, s) in values:
            neighbors.append({"fast": bf, "slow": s, "value": values[(bf, s)],
                              "score": round(score(values[(bf, s)]), 4)})

    if not neighbors:
        return {
            "metric": metric,
            "best": {"fast": bf, "slow": bs, "value": values[best_key],
                     "score": round(score(values[best_key]), 4)},
            "verdict": "unknown",
            "neighbor_mean_score": None,
            "neighbors": [],
            "note": "最优点在网格边缘且无有效相邻格，无法判定高原/孤岛",
        }

    nb_mean = sum(nb["score"] for nb in neighbors) / len(neighbors)
    if nb_mean >= _PLATEAU_THRESHOLD:
        verdict = "plateau"
        note = "最优点的邻居保有高相对排名→ 优势来自结构，敢用"
    elif nb_mean <= _ISLAND_THRESHOLD:
        verdict = "island"
        note = "邻居全塌 → 这是一格噪声伪装的「最优」，换参数就崩，极危险"
    else:
        verdict = "mixed"
        note = "部分邻居还行 → 脊状/坡状；建议向邻居更好的方向扩格验证"

    return {
        "metric": metric,
        "best": {"fast": bf, "slow": bs, "value": values[best_key],
                 "score": round(score(values[best_key]), 4)},
        "verdict": verdict,
        "neighbor_mean_score": round(nb_mean, 4),
        "neighbors": neighbors,
        "note": note,
    }


# ── 热力图（约定 5：双向红绿）────────────────────────────────────────

# ⚠️ 这里的颜色是**兜底默认值**，不是真源。
#
# AGENTS 硬规则 7：颜色真源只有 frontend/src/theme/tokens.ts。
# 后端不该定义颜色 —— 但它产出的 option 需要 visualMap 色阶才能渲染。
# 解决方式：option 里输出一个**语义标记**（`semanticScale: "pnl"`），
# 前端 themed() 见到它就用 palette 的实际色值覆盖掉这里的兜底值。
# 这样：口径切换（涨红跌绿 ↔ 涨绿跌红）由前端 palette 决定，
# 后端不参与，也不会出现「后端说涨是红、前端切成国际口径」的矛盾。
#
# 下面的常量只在「前端没有 themed 覆盖」（比如直接看裸 option）时生效。
# 国际口径翻转由前端 themed() 层负责（本 option 是数据 + 结构，不是皮肤）。
_NEGATIVE_COLOR = "#3FAE7A"   # tokens.ts palette.down（跌=绿，A股口径）
_NEUTRAL_COLOR = "#EFEFEF"    # 中性白（≈ tokens 的 panel 底色，用于「无差异」格）
_POSITIVE_COLOR = "#D9534F"   # tokens.ts palette.up（涨=红，A股口径）


def to_heatmap(result: dict[str, Any]) -> dict[str, Any]:
    """ECharts option：x=fast，y=slow，每格=metric 值；正负双向色阶（红涨绿跌）。"""
    metric = result["metric"]
    fasts = sorted({e["fast"] for e in result["grid"]})
    slows = sorted({e["slow"] for e in result["grid"]})
    cells = [
        [fasts.index(e["fast"]), slows.index(e["slow"]),
         round(float(e["metrics"][metric]), 6)]
        for e in result["grid"]
        if metric in e["metrics"]
    ]
    vals = [c[2] for c in cells]
    bound = max((abs(v) for v in vals), default=1.0) or 1.0
    return chart.validate_option({
        "title": {"text": f"参数扫描热力图（{metric}）"},
        "tooltip": {"trigger": "item"},
        "grid": {"left": 64, "right": 24, "top": 48, "bottom": 80, "containLabel": True},
        "xAxis": {"type": "category", "name": "fast", "data": [str(f) for f in fasts],
                  "splitArea": {"show": True}},
        "yAxis": {"type": "category", "name": "slow", "data": [str(s) for s in slows],
                  "splitArea": {"show": True}},
        "visualMap": {
            "min": -bound,
            "max": bound,
            "calculable": True,
            "orient": "horizontal",
            "left": "center",
            "bottom": 16,
            # 前端 themed() 用这行判断「这个色阶要按涨跌口径重上色」，
            # 而不是照抄后端写死的 hex。
            "semanticScale": "pnl",
            "inRange": {
                # 双向 + 中性白：负值=绿、0=白、正值=红。**不许单向渐变**。
                "color": [_NEGATIVE_COLOR, _NEUTRAL_COLOR, _POSITIVE_COLOR],
            },
        },
        "series": [{
            "name": f"{metric}",
            "type": "heatmap",
            "data": cells,
            "label": {"show": True},
        }],
    })


# ── 页面注册（同 tearsheet / factor_lab 机制）────────────────────────

def _parse_grid(raw: str, fallback: list[int]) -> list[int]:
    """"20,30,60" → [20, 30, 60]；解析失败/为空 → fallback。"""
    try:
        vals = [int(x.strip()) for x in raw.split(",") if x.strip()]
    except (AttributeError, ValueError):
        return fallback
    return vals or fallback


_PARAMS: list[ParamSpec] = [
    ParamSpec("symbol", "str", default="600519", label="标的"),
    ParamSpec("fast_grid", "str", default="20,30,60", label="快线网格"),
    ParamSpec("slow_grid", "str", default="120,180,250", label="慢线网格"),
    ParamSpec("range", "date_range", default="1y", label="区间"),
    ParamSpec("metric", "enum", default="sharpe",
              choices=["sharpe", "total_return", "annual_return", "max_drawdown"],
              label="指标"),
]


@register("paramscan.heatmap", params=_PARAMS)
def paramscan_heatmap(
    symbol: str,
    fast_grid: str = "20,30,60",
    slow_grid: str = "120,180,250",
    range: str = "1y",
    metric: str = "sharpe",
) -> dict:
    """参数扫描热力图：x=fast，y=slow，值=metric；renderer=echarts（二维聚合）。

    数据不可用时降级为空热力图（留白，不编数字）。
    """
    fg = _parse_grid(fast_grid, [20, 30, 60])
    sg = _parse_grid(slow_grid, [120, 180, 250])
    rows = data.closes_for_range(symbol, range)
    closes = [c for _, c in rows]
    dates = [d for d, _ in rows]
    if len(closes) < 2:
        res: dict[str, Any] = {
            "grid": [], "metric": metric, "combos": 0,
            "failed": [{"fast": "-", "slow": "-",
                        "reason": "数据源暂不可用或历史不足"}],
        }
    else:
        try:
            res = scan(closes, dates, fast_grid=fg, slow_grid=sg, metric=metric)
        except Exception as e:
            return to_heatmap({"grid": [], "metric": metric, "combos": 0,
                               "failed": [{"reason": str(e)}]})
    return to_heatmap(res)
