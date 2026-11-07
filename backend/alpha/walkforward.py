"""alpha.walkforward —— Walk-forward / 样本外验证（M4-4）。

参数扫描（M4-3）在全样本上挑「回测最好的参数」，样本内最优几乎必然在样本外崩。
Walk-forward 是唯一诚实的检验方式：把历史切成滚动的「训练段 → 紧邻测试段」，
每窗用**训练段**选最优参数，再去**没见过的测试段**上用它，最后把各窗测试段的
净值块拼接成一条**样本外净值曲线**（oos_equity）——本模块的核心产出。

纯计算层：只用标准库，不 import 框架，不读 env，不碰数据源。
与 alpha.tearsheet 同层的写法与口径约定。

════════ 设计约定（测试锁定，改动需同步改测试）════════

1. **索引区间一律用半开区间 [start, end)**，end 不含。
   「test 段长度」= test_end - test_start；窗口首尾相接时（step == test）
   前一窗的 test_end 就是后一窗的连续起点，无歧义。

2. **窗口不重叠（test 段之间），否则样本外被重复使用。**
   split_windows 用 step 控制：step 默认 == test（滚动不重叠）。允许 step < test
   生成重叠的 test 窗（如「逐日滚动」想更细致地观察参数选择随时间的漂移），
   但 **walk_forward 拒收 step < test**：oos_equity 是把各窗 test 段净值块
   首尾相乘拼接的，test 段重叠 = 同一批 OOS 日被计入两次，拼出来的曲线不诚实。
   想要重叠观察的人去看 windows 列表里的逐窗数字，不要拿拼接曲线。

3. **训练段与测试段严格不重叠，且测试段在训练段之后。**
   split_windows 生成的窗口恒满足 test_start >= train_end。这保证选参数时
   绝不用到未来数据——这是 walk-forward 与「全样本调参」的本质区别。

4. **选参数只用训练段（本模块最要害的一条，变异测试锁死）。**
   每窗对 param_grid 逐个调 engine(训练段收盘价, params)，取 metric 最高者。
   若在全样本（含测试段）上选参，就退化成「用未来挑参数」——这正是 M4-3
   参数扫出来的漂亮曲线过拟合的根源。变异测试：把选参输入换成全样本，
   测试必须变红（test_walkforward.TestChooseOnTrainOnly）。

5. **degradation = oos_mean / is_mean（样本外表现衰减比例）——本任务的核心指标。**
   is_mean = 各有效窗 in_sample_metric 的均值，oos_mean = 对应 out_sample_metric
   的均值（同一 metric 同一集合，均值才有比值意义）。
   解读经验阈值（写在这里，前端/agent 报警按此执行）：
     · >= 0.9     参数稳健，样本内外接近；
     · 0.6 ~ 0.9  可接受，注意观察；
     · 0.3 ~ 0.6  警告：参数大概率在追样本内噪声；
     · < 0.3      强警告：过拟合，样本内数字不可信。
   degradation > 1 不当「惊喜」报——更像测试段行情恰好顺参数（运气），提一句即可。
   is_mean ≈ 0 时比值无定义 → None（分母为 0，不是衰减，是没基准）。

6. **某窗训练段选不出参数（全部失败）→ 记录并跳过该窗，不整体失败。**
   vendor 数据在某个历史区间缺失、某参数组合触发上游崩溃，都是常态而不是
   事故。该窗在 windows 里留 {status: "skipped"/"failed", reason: str}，
   其 test 段不进 oos_equity（宁缺一段，不编一段）。operative 口径：
   is_mean / oos_mean / degradation / 参数稳定性都只统计有效窗（status == "ok"）。

7. **样本外净值 oos_equity 的拼接口径：**
   每窗 OOS 引擎跑在闭区间 [train_start, test_end) 的整段收盘价上（保证信号
   热身有完整历史、test 首日持仓由 train 末日的信号继承——无未来函数），
   取净值段相对**测试段前一日基点**的比值链
     local(t) = equity(t) / equity(test_start - 1)，t ∈ [test_start, test_end)
   与前窗累计值相乘相接。整条曲线从首个测试段前一日的名义 1.0 起算：
   首点就是首窗第一个 OOS 收益后的值（可能 ≠ 1.0），曲线长度 =
   各有效窗 test 段长度之和（约定 6 跳过的窗不计入）。
   相邻两窗 test 段首尾衔接时（step == test），曲线相邻点的日收益 = 各窗
   局部收益的原样拼接——这是按窗复合的恒等式，不做任何平滑。

8. **用 total_return 当 metric 时，train 与 test 应当等长。**
   degradation = oos_mean / is_mean 是拿两个数比值。但「总收益」天然随区间
   长度增长 —— 同样日收益下 120 天的总收益必然大于 60 天。于是
   train=120 / test=60 的配置会让 degradation 系统性偏低（实测 0.47 而不是
   1.0），看起来像过拟合、其实是**度量本身在骗人**。
   用 sharpe（已年化，与长度无关）当 metric 没有这个问题。
   本模块不强制 train == test（有时业务上就是要长训练短测试），但**调用方
   必须知道这个偏差**：默认 metric 是 "sharpe" 而不是 "total_return" 就是这个原因。

9. **除零与空输入全域防守：** 没有任何有效窗 → oos_equity 为空列表，
   summary 各值（含 oos_total_return / oos_sharpe）一律 None——
   「没数」不假装有数，也不造 0（与 tearsheet 同一立场）。
   Sharpe 口径与 alpha.backtest / alpha.tearsheet 完全一致：
   日收益样本标准差 ddof=1，×√252，rf=0，std=0 → 0.0。
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Sequence
from typing import Any

from alpha import chart, data
from alpha.registry import ParamSpec, register

_TRADING_DAYS = 252
_RANGE_COUNT = {"3m": 63, "6m": 126, "1y": 250}


# ── 窗口切分 ─────────────────────────────────────────────────────────

def split_windows(
    n_days: int, *, train: int, test: int, step: int | None = None
) -> list[dict[str, int]]:
    """切出滚动 walk-forward 窗口；返回半开索引区间 [{train_*, test_*}]。

    参数：n_days 总样本天数；train/test/step 均为天数（step 缺省 = test）。
    返回：[{"train_start","train_end","test_start","test_end"}, …]（半开区间）。

    · 窗口按 step 前进；step = test 时 test 段首尾相接不重叠（缺省口径）；
      step > test 时 test 段之间留洞（跳过一段再验）；step < test 时 test 段
      重叠——**允许生成**（如逐日滚动观察参数漂移），但 walk_forward 会拒收，
      因为拼接净值会把重叠的 OOS 日重复计入（见模块 docstring 约定 2）；
    · 总长度不够一整窗（train + test > n_days）→ 返回 []，不硬凑残窗
      （拿残窗冒充一整窗等于把「调参段」当「验证段」用，方向性造假）。
    """
    if train < 1 or test < 1:
        raise ValueError("train / test 必须 >= 1")
    step = test if step is None else step
    if step < 1:
        raise ValueError("step 必须 >= 1")
    windows: list[dict[str, int]] = []
    start = 0
    while start + train + test <= n_days:
        windows.append({
            "train_start": start,
            "train_end": start + train,
            "test_start": start + train,
            "test_end": start + train + test,
        })
        start += step
    return windows


# ── 引擎适配（engine 契约：engine(closes, params) -> 结果对象）──────────

def _metrics_of(res: Any) -> dict[str, Any]:
    """BacktestResult（.metrics）与 dict（["metrics"]）两种形状都认。"""
    if isinstance(res, dict):
        m = res.get("metrics")
    else:
        m = getattr(res, "metrics", None)
    return m if isinstance(m, dict) else {}


def _equity_of(res: Any) -> list[float] | None:
    if isinstance(res, dict):
        e = res.get("equity")
    else:
        e = getattr(res, "equity", None)
    if not isinstance(e, (list, tuple)):
        return None
    return [float(v) for v in e]


def _finite(v: Any) -> float | None:
    """有限数 → float；None/NaN/inf/非数值 → None（得分缺失 = 无效）。"""
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _golden_engine(closes: Sequence[float], params: dict[str, Any]) -> Any:
    """缺省引擎：alpha.backtest 的双均线金叉（fast/slow 来自私 params）。"""
    from alpha.backtest import backtest_golden_cross  # 局部 import，防模块环

    return backtest_golden_cross(
        list(closes), fast=int(params["fast"]), slow=int(params["slow"])
    )


# ── 指标（与 alpha.backtest 完全同口径，测试锁死）────────────────────

def _daily_returns_from(band: Sequence[float]) -> list[float]:
    """净值段 → 逐日收益（band[0] 为前一日基点，不产生收益点本身）。"""
    out: list[float] = []
    for t in range(1, len(band)):
        base = band[t - 1]
        out.append(band[t] / base - 1.0 if abs(base) > 1e-12 else 0.0)
    return out


def _metric_of_band(band: Sequence[float], metric: str) -> float | None:
    """在测试段净值带上按回测引擎同公式复算指标（band 含前一日基点）。

    支持 total_return / sharpe / max_drawdown；其它 metric 名 → None
    （宁缺不瞎算）。std=0 → sharpe 0.0（与 backtest.run 一致）。
    """
    if metric == "total_return":
        base = band[0] if band else None
        if base is None or abs(base) < 1e-12:
            return None
        return band[-1] / base - 1.0
    if metric == "sharpe":
        rets = _daily_returns_from(band)
        if len(rets) < 2:
            return 0.0
        m = sum(rets) / len(rets)
        var = sum((x - m) ** 2 for x in rets) / (len(rets) - 1)
        std = math.sqrt(var)
        if std <= 1e-12:
            return 0.0
        return (m / std) * math.sqrt(_TRADING_DAYS)
    if metric == "max_drawdown":
        peak = band[0] if band else 0.0
        dd = 0.0
        for v in band:
            peak = max(peak, v)
            dd = min(dd, v / peak - 1.0 if abs(peak) > 1e-12 else 0.0)
        return dd
    return None


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


# ── 对外：walk-forward 主流程 ────────────────────────────────────────

def walk_forward(
    closes: Sequence[float],
    dates: Sequence[str] | None,
    *,
    param_grid: Sequence[dict[str, Any]],
    train: int,
    test: int,
    step: int | None = None,
    engine: Callable[[Sequence[float], dict[str, Any]], Any] | None = None,
    metric: str = "sharpe",
) -> dict[str, Any]:
    """滚动调参 + 样本外验证。每窗：训练段选最优参数 → 紧邻测试段用它。

    参数：
      closes:     收盘价序列（全历史）。
      dates:      与 closes 等长的日期标签；None 用序号（仅拼图日期用）。
      param_grid: 候选参数列表（每个 dict 一组参数）。
      train/test: 训练/测试段天数；step 缺省 = test（滚动不重叠）。
      engine:     回测引擎 (closes, params) -> 结果（含 metrics/equity）；
                  缺省用双均线金叉（alpha.backtest）。engine 内部抛错视为
                  该组参数该窗失败，不会拖垮整体（约定 6）。
      metric:     选参用的指标名（同时在 out_sample_metric 用同一口径复算），
                  支持 total_return / sharpe / max_drawdown。

    返回 keys：windows / oos_equity / oos_dates / summary。
    step < test 拒收（test 段重叠会把 OOS 日重复计入拼接曲线，约定 2）。
    """
    if len(closes) and dates is not None and len(dates) != len(closes):
        raise ValueError("dates 与 closes 长度须一致")
    if train < 2:
        raise ValueError("train 必须 >= 2（训练段连双侧都放不下，没有参可调）")
    if test < 1:
        raise ValueError("test 必须 >= 1")
    step = test if step is None else step
    if step < test:
        raise ValueError(
            f"step ({step}) < test ({test})：test 段重叠会把样本外重复计入"
            "oos_equity（约定 2）。要观察参数漂移请用 split_windows 单独取窗口。"
        )
    engine = engine or _golden_engine

    windows = split_windows(len(closes), train=train, test=test, step=step)
    win_rows: list[dict[str, Any]] = []
    oos_equity: list[float] = []
    oos_dates: list[str] = []

    for win in windows:
        ts, te, ss, se = (win["train_start"], win["train_end"],
                          win["test_start"], win["test_end"])
        train_closes = list(closes[ts:te])
        # —— 训练段选参（只用训练段！约定 4）——
        best_score: float | None = None
        best_params: dict[str, Any] | None = None
        failures = 0
        for params in param_grid:
            try:
                res = engine(train_closes, params)
                score = _finite(_metrics_of(res).get(metric))
            except Exception:
                failures += 1
                continue
            if score is None:
                failures += 1
                continue
            if best_score is None or score > best_score:   # 并列取先出现者（稳定）
                best_score, best_params = score, params
        if best_params is None:
            win_rows.append({
                "train_range": [ts, te], "test_range": [ss, se],
                "chosen_params": None, "status": "skipped",
                "in_sample_metric": None, "out_sample_metric": None,
                "reason": f"训练段 {len(param_grid)} 组参数全部失败"
                          "（ret/取数/指标无效），跳过该窗（约定 6）",
            })
            continue

        # —— 紧邻测试段：用选出的参数跑 [train_start, test_end) 整段，
        #     信号热身有完整历史，test 首日持仓由 train 末日信号继承 ——
        slice_closes = list(closes[ts:se])
        base_local = te - ts                     # 测试段前一日基点（在 slice 内的下标）
        try:
            oos_res = engine(slice_closes, best_params)
            equity = _equity_of(oos_res)
            if equity is None or len(equity) != len(slice_closes):
                raise ValueError("equity 长度与输入收盘价不一致")
            base = equity[base_local - 1] if base_local >= 1 else None
            if base is None or abs(base) < 1e-12:
                raise ValueError("测试段前一日基点无效（equity<=0）")
            # local(t) = equity(t) / equity(base)，与累计链相乘（约定 7）
            band = [base] + [equity[i] for i in range(base_local, len(equity))]
            band_metric = _finite(_metric_of_band(band, metric))
            if band_metric is None:
                raise ValueError(f"测试段无法复算指标 {metric!r}")
            cum = oos_equity[-1] if oos_equity else 1.0
            for j, i in enumerate(range(base_local, len(equity))):
                oos_equity.append(round(cum * equity[i] / base, 10))
                if dates is None:
                    oos_dates.append(str(ss + j))
                else:
                    oos_dates.append(dates[ss + j])
        except Exception as exc:
            win_rows.append({
                "train_range": [ts, te], "test_range": [ss, se],
                "chosen_params": best_params, "status": "failed",
                "in_sample_metric": round(best_score, 6), "out_sample_metric": None,
                "reason": f"样本外回测失败：{exc}",
            })
            continue

        win_rows.append({
            "train_range": [ts, te], "test_range": [ss, se],
            "chosen_params": dict(best_params), "status": "ok",
            "in_sample_metric": round(best_score, 6),
            "out_sample_metric": round(band_metric, 6),
            "reason": None,
        })

    result = {
        "windows": win_rows,
        "oos_equity": oos_equity,
        "oos_dates": oos_dates,
        "metric": metric,
    }
    result["summary"] = aggregate(result)
    return result


# ── 对外：汇总（样本外总收益 / Sharpe / 参数稳定性 / 退化程度）─────────

def aggregate(wf_result: dict[str, Any]) -> dict[str, Any]:
    """从 walk_forward 的返回里汇总样本外画像（约定 6 只统计有效窗）。

    degradation = oos_mean / is_mean（约定 5，阈值见模块 docstring）。
    参数稳定性 = 最常被选中的参数组占比（1.0 = 每窗都选同一组）。空结果
    （无有效窗）各值 None，不崩、不编 0。
    """
    windows = wf_result.get("windows", [])
    ok = [w for w in windows if w.get("status") == "ok"]
    oos_cur: list[float] = list(wf_result.get("oos_equity") or [])

    # 样本外总收益：曲线从名义 1.0 起算（约定 7），首点即为当日收益后的值。
    total_return = (oos_cur[-1] - 1.0) if oos_cur else None

    # 样本外 Sharpe：口径与 backtest/tearsheet 一致（ddof=1 ×√252 rf=0）。
    sharpe: float | None = None
    if len(oos_cur) >= 3:
        rets = _daily_returns_from(oos_cur)
        m = _mean(rets)
        var = sum((x - m) ** 2 for x in rets) / (len(rets) - 1)
        std = math.sqrt(var)
        if std > 1e-12:
            sharpe = (m / std) * math.sqrt(_TRADING_DAYS)
        else:
            sharpe = 0.0

    is_vals = [w["in_sample_metric"] for w in ok if w.get("in_sample_metric") is not None]
    oos_vals = [w["out_sample_metric"] for w in ok if w.get("out_sample_metric") is not None]
    is_mean = _mean(is_vals) if is_vals else None
    oos_mean = _mean(oos_vals) if oos_vals else None
    degradation = (
        oos_mean / is_mean if (is_mean is not None and oos_mean is not None
                               and abs(is_mean) > 1e-12) else None
    )

    # 参数稳定性：最常被选中的参数组占比（元组化以便去重/计数）。
    picks = [tuple(sorted(w["chosen_params"].items()))
              for w in ok if w.get("chosen_params")]
    distinct = len(set(picks))
    stability = (Counter(picks).most_common(1)[0][1] / len(picks)) if picks else None

    return {
        "oos_total_return": round(total_return, 6) if total_return is not None else None,
        "oos_sharpe": round(sharpe, 6) if sharpe is not None else None,
        "is_mean": round(is_mean, 6) if is_mean is not None else None,
        "oos_mean": round(oos_mean, 6) if oos_mean is not None else None,
        "degradation": round(degradation, 6) if degradation is not None else None,
        "param_stability": round(stability, 6) if stability is not None else None,
        "distinct_params": distinct,
        "n_windows": len(windows),
        "n_windows_ok": len(ok),
    }


# ── 注册的图表 fn（机制同 backtest_page / factor_lab）────────────────

_PARAMS = [
    ParamSpec("symbol", "str", default="600519", label="标的"),
    ParamSpec("range", "date_range", default="1y", label="区间"),
    ParamSpec("train", "int", default=120, min=10, max=250, label="训练段(日)"),
    ParamSpec("test", "int", default=20, min=5, max=60, label="测试段(日)"),
    ParamSpec("fast_set", "str", default="5,10,20", label="快线候选(逗号分隔)"),
    ParamSpec("slow_set", "str", default="60,120,240", label="慢线候选(逗号分隔)"),
]


def _parse_ints(text: str) -> list[int]:
    out: list[int] = []
    for tok in str(text).replace("，", ",").split(","):
        tok = tok.strip()
        if tok and tok.lstrip("+-").isdigit():
            out.append(int(tok))
    return sorted(set(v for v in out if v >= 1))


def _build_grid(fast_set: str, slow_set: str) -> list[dict[str, int]]:
    """fast × slow 笛卡尔积（只保留 slow > fast）。为空 → 引发提示（空图）。"""
    return [
        {"fast": f, "slow": s}
        for f in _parse_ints(fast_set) for s in _parse_ints(slow_set) if s > f
    ]


@register("walkforward.oos_equity", params=_PARAMS)
def walkforward_oos_equity(symbol: str, range: str = "1y", train: int = 120,
                           test: int = 20, fast_set: str = "5,10,20",
                           slow_set: str = "60,120,240") -> dict:
    """Walk-forward 样本外拼接净值（renderer=lwc，净值时间序列）。

    每窗用训练段选金叉参数、紧邻测试段使用它；曲线只由「当时选出的参数在
    之后没见过的行情上」产生——这是参数扫描漂亮曲线的诚实对照线。
    summary 的 degradation（oos_mean/is_mean）远小于 1 → 参数过拟合。
    数据不可用 / 参数组合为空 / 窗口不足时优雅降级为空图 + 标题提示。
    """
    grid = _build_grid(fast_set, slow_set)
    if not grid:
        return chart.line([], {"样本外净值": []},
                          title="Walk-forward 样本外净值（参数组合为空：需 slow > fast）")
    rows = data.closes_for_range(symbol, range)
    if len(rows) < 2:
        return chart.line([], {"样本外净值": []},
                          title="Walk-forward 样本外净值（数据暂不可用）")
    dates = [d for d, _ in rows]
    closes = [c for _, c in rows]
    wf = walk_forward(closes, dates, param_grid=grid, train=train, test=test,
                      metric="sharpe")
    if not wf["oos_equity"]:
        return chart.line([], {"样本外净值": []},
                          title="Walk-forward 样本外净值（历史不足一个窗口或各窗全失败）")
    s = wf["summary"]
    deg = s["degradation"]
    deg_txt = "—" if deg is None else f"{deg:.2f}"
    return chart.line(
        wf["oos_dates"],
        {"样本外净值": [round(v, 6) for v in wf["oos_equity"]]},
        title=(f"Walk-forward 样本外净值（degradation={deg_txt}，"
               f" 有效窗 {s['n_windows_ok']}/{s['n_windows']}）"),
    )
