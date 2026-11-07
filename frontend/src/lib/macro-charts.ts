/**
 * 宏观图表的 option 构建（ROUND3 D4）。
 *
 * 为什么要有这一层：宏观看板原来只有「一行数字 + 涨跌幅」。用户判定那是
 * **内容不足**而不是密度不够 —— 孤立的「PMI 50.1」「10Y 1.64%」看不出
 * 现在处于历史什么位置，只有序列能回答「连续几个月在荣枯线下」「利率
 * 从 2.7 掉到 1.6 用了多久」。
 *
 * 纯函数：不碰 DOM、不读全局状态，可直接单测。
 *
 * 配色纪律（AGENTS 硬规则 7 + ADR-0014）：
 *   · 不写 `#` 开头颜色字面量 —— 交给 `EChart` 的 `themed()` 按当前 palette 上色
 *   · **不传 legend** —— 窄容器下 ECharts legend 会压绘图区（实测踩过两次），
 *     图例由 `<ChartLegend>` / `<ToneLegend>` 在 HTML 层自绘
 *   · 取不到数据一律返回 null，由调用方渲染「暂不可用」，**不画空轴**
 *     （空轴看起来像「数据是 0」，比不画更误导）
 */

type Tone = "up" | "down" | "neutral";

/** 与后端 `GET /api/macro/*` 的 series 形状对齐（见 lib/api.ts MacroSeries）。 */
export interface SeriesPoint {
  period: string;
  value: number | null;
}

/** 曲线形状：期限 → 收益率。 */
export interface CurvePoint {
  tenor: string;
  value: number;
}

/** 语义色标记：由 EChart 的 themed() 换成当前 palette 的具体色值。 */
function toneSeries(name: string, data: (number | null)[], type: "bar" | "line", tone: Tone) {
  return {
    name,
    type,
    data,
    semanticTone: tone,
    ...(type === "bar" ? { barMaxWidth: 14, barGap: "10%" } : { smooth: false }),
  };
}

/** "2026-09" / "2026-09-01" → "26-09" / "09-01"（省横轴宽度；完整值放 tooltip）。 */
function shortPeriod(p: string): string {
  const m = /^(\d{4})-(\d{2})(?:-(\d{2}))?$/.exec(p);
  if (!m) return p;
  return m[3] ? `${m[2]}-${m[3]}` : `${m[1].slice(2)}-${m[2]}`;
}

/** 公共底座：网格贴边、无 legend、tooltip 走轴触发。 */
function base(periods: string[], opts: { bottom?: number } = {}) {
  return {
    grid: { left: 44, right: 12, top: 14, bottom: opts.bottom ?? 24 },
    tooltip: { trigger: "axis" as const },
    xAxis: {
      type: "category" as const,
      data: periods.map(shortPeriod),
      axisTick: { show: false },
    },
  };
}

/**
 * 社融增量：柱状 + 零轴。
 *
 * 为什么是柱不是折线：社融是**月度增量**（流量），不是存量水平。
 * 折线会让人以为可以「从 3 月连到 4 月」，而增量的含义是每月独立一笔。
 * 负值（当月净偿还/收缩）必须能看见，所以零轴显式画出来。
 */
export function socialFinancingOption(points: SeriesPoint[]): Record<string, unknown> | null {
  if (points.length === 0) return null;
  return {
    ...base(points.map((p) => p.period)),
    yAxis: {
      type: "value",
      name: "亿元",
      nameTextStyle: { align: "right" },
      // 零轴：负的社融（罕见但真实存在）必须能看出来，不能和正值同色
      splitLine: { show: true, lineStyle: { opacity: 0.25 } },
    },
    series: [
      {
        ...toneSeries("社融增量", points.map((p) => p.value), "bar", "neutral"),
        // 逐柱按**数值正负**上色（复用 EChart 已有的 `pnl-bars` 约定）：
        // 社融可以是负的（当月净偿还），负值同色会被读成「小一点的正值」。
        semanticScale: "pnl-bars",
      },
    ],
  };
}

/**
 * PMI：折线 + 50 荣枯线。
 *
 * 50 这条线是**整个指标的坐标系原点**：51 和 49 的差别不是 2 个数，
 * 是「扩张」和「收缩」。不画这条线的话，读者看到 49.8 会以为「还行」。
 *
 * 注意 yAxis 不设 min/max：PMI 常年 47~53 之间波动，若从 0 起画，
 * 整条线会变成一条贴顶的直线，完全看不出变化。
 */
export function pmiOption(points: SeriesPoint[], seriesName = "制造业 PMI"): Record<string, unknown> | null {
  if (points.length === 0) return null;
  return {
    ...base(points.map((p) => p.period)),
    yAxis: { type: "value", name: "指数", scale: true },
    series: [
      {
        ...toneSeries(seriesName, points.map((p) => p.value), "line", "neutral"),
        showSymbol: true,
        symbolSize: 5,
        lineStyle: { width: 2 },
        // 荣枯线用 markLine：它是**参考基准**，不是一条数据系列。
        // 做成 series 会多出一条假数据线（还进 tooltip），语义也错。
        markLine: {
          silent: true,
          symbol: "none",
          data: [{ yAxis: 50, name: "荣枯线 50" }],
          lineStyle: { type: "dashed" },
          label: { formatter: "荣枯线 50", position: "insideEndTop" },
        },
      },
    ],
  };
}

/**
 * 国债收益率曲线：横轴是**期限**（不是时间），一条当日的线。
 *
 * 为什么不用折线连期数、也不画历史：曲线的信息在**形状**——
 * 正常（上斜）/ 平坦 / 倒挂。换成时间序列就看不出倒挂了。
 */
export function yieldCurveOption(points: CurvePoint[]): Record<string, unknown> | null {
  if (points.length === 0) return null;
  return {
    grid: { left: 44, right: 16, top: 14, bottom: 24 },
    tooltip: { trigger: "axis" as const },
    xAxis: {
      type: "category" as const,
      data: points.map((p) => p.tenor.toUpperCase()),
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      name: "%",
      nameTextStyle: { align: "right" },
      // 曲线也要 scale：国债收益率在 1.2~2.2 之间，从 0 起画就是一条直线
      scale: true,
    },
    series: [
      {
        name: "国债收益率",
        type: "line",
        data: points.map((p) => p.value),
        showSymbol: true,
        symbolSize: 5,
        lineStyle: { width: 2 },
      },
    ],
  };
}

/**
 * 单值序列（LPR / 回购利率 / 两融余额）：折线。
 *
 * 这类**水平值**用折线（可以「从上一期连过来」），与社融那种流量值相反。
 */
export function levelSeriesOption(
  points: SeriesPoint[],
  opts: { name: string; unit: string },
): Record<string, unknown> | null {
  if (points.length === 0) return null;
  return {
    ...base(points.map((p) => p.period)),
    yAxis: {
      type: "value",
      name: opts.unit,
      nameTextStyle: { align: "right" },
      scale: true,
    },
    series: [
      {
        ...toneSeries(opts.name, points.map((p) => p.value), "line", "neutral"),
        showSymbol: false,
        lineStyle: { width: 2 },
      },
    ],
  };
}

/**
 * 净流入（北向资金）：正负双向柱。
 *
 * 与 `market-charts.ts` 的板块资金同一个套路：正负分色。
 * 净流出的规模比流入更能说明情绪转折，同色柱会让读者只看到「柱子高低」。
 */
export function netFlowOption(points: SeriesPoint[], name = "净流入"): Record<string, unknown> | null {
  if (points.length === 0) return null;
  return {
    ...base(points.map((p) => p.period)),
    yAxis: { type: "value", name: "亿元", nameTextStyle: { align: "right" } },
    series: [
      {
        ...toneSeries(name, points.map((p) => p.value), "bar", "neutral"),
        // 同上：净流出必须与净流入异色，否则「柱子高低」会盖掉「方向」。
        semanticScale: "pnl-bars",
      },
    ],
  };
}

/**
 * 取序列里最后一个非空值 → 「当前读数」。
 *
 * 为什么不用 `points.at(-1)`：后端可能把「未发布」的月份留成 null
 * （社融当月还没公布），取到 null 会让面板显示「—」，看起来像取数失败。
 */
export function latestValue(points: SeriesPoint[]): number | null {
  for (let i = points.length - 1; i >= 0; i -= 1) {
    const v = points[i]?.value;
    if (typeof v === "number" && Number.isFinite(v)) return v;
  }
  return null;
}

/**
 * 取序列里最后一个非空点的时间标签（与 `latestValue` 配套）。
 *
 * 不用 `points.at(-1)`：tsconfig 的 lib 是 ES2021，`Array.prototype.at`
 * 不在其中（tsc 直接报 TS2550）。也别改成 `points[len-1]` 就算完 ——
 * 最后一个点的 value 可能为 null（当月未发布），那样读数与时间会错位一格。
 */
export function latestPeriod(points: SeriesPoint[]): string | null {
  for (let i = points.length - 1; i >= 0; i -= 1) {
    const v = points[i]?.value;
    if (typeof v === "number" && Number.isFinite(v)) return points[i]?.period ?? null;
  }
  return null;
}
