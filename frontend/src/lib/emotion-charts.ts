/**
 * 情绪历史图表的 option 构建（ROUND2 阶段 2）。
 *
 * 用户原话：「能用图表进行信息的表达就优先使用图表，因为单纯的独立的数字是
 * 看不出来什么的，需要跟之前的数据进行比对才知道」。
 *
 * 所以这些函数都吃**一段历史序列**（不只是当天一个数），输出 ECharts option。
 * 纯函数：不碰 DOM、不读全局状态，可以直接单测。
 *
 * 配色纪律（AGENTS 硬规则 7 + ADR-0014）：
 *   · 不写 `#` 开头颜色字面量 —— 交给 `EChart` 的 `themed()` 按当前 palette 上色
 *   · 涨跌用 `semanticTone` 语义标记，切国际口径时自动反向
 *   · **不传 legend**（窄容器下 ECharts legend 会压绘图区，实测踩过）
 */

/** 与后端 `GET /api/market/emotion-history` 的一行对应。 */
export interface EmotionPoint {
  date: string;
  zt_count: number;
  dt_count: number;
  zb_count: number;
  max_boards: number;
  lianban_count: number;
  seal_rate: number | null;
  break_rate: number | null;
  promotion_rate?: number | null;
}

export interface LadderRow {
  boards: number;
  count: number;
  plus?: boolean;
}

type Tone = "up" | "down" | "neutral";

/** 语义色标记：由 EChart 的 themed() 换成当前 palette 的具体色值。 */
function toneSeries(name: string, data: number[], type: "bar" | "line", tone: Tone) {
  return {
    name,
    type,
    data,
    semanticTone: tone,
    ...(type === "bar" ? { barMaxWidth: 14, barGap: "10%" } : { smooth: false }),
  };
}

/** 日期 → "MM-DD"（省宽度；完整日期放在 tooltip）。 */
function shortDates(hist: EmotionPoint[]): string[] {
  return hist.map((p) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(p.date);
    return m ? `${m[2]}-${m[3]}` : p.date;
  });
}

/** 公共底座：网格贴边、无 legend、tooltip 走轴触发。 */
function base(hist: EmotionPoint[]) {
  return {
    grid: { left: 40, right: 12, top: 12, bottom: 24 },
    tooltip: { trigger: "axis" as const },
    xAxis: {
      type: "category" as const,
      data: shortDates(hist),
      axisTick: { show: false },
    },
  };
}

/**
 * 涨停 vs 跌停 vs 炸板：三条柱。
 *
 * 为什么这三个并排：它们是同一件事的三个侧面（尝试涨停 → 封住/炸板），
 * 分开看没有意义。10-22 那天涨停 33、跌停 49，单独看数字感知不到
 * 「跌停超过涨停」这种转折。
 */
export function ztDtZbOption(hist: EmotionPoint[]): Record<string, unknown> | null {
  if (hist.length === 0) return null;
  return {
    ...base(hist),
    yAxis: { type: "value", name: "家数", nameTextStyle: { align: "right" } },
    series: [
      toneSeries("涨停", hist.map((p) => p.zt_count), "bar", "up"),
      toneSeries("跌停", hist.map((p) => p.dt_count), "bar", "down"),
      toneSeries("炸板", hist.map((p) => p.zb_count), "bar", "neutral"),
    ],
  };
}

/**
 * 最高连板高度：折线。
 *
 * 这是短线情绪最关键的一条线 —— 高度代表资金愿意接力的意愿。
 * 实测数据里 10-12 是 10 板、10-13 骤降到 3 板，画成折线是明显的断崖，
 * 而两个孤立数字「10」和「3」看不出这是同一段情绪的崩塌。
 */
export function maxBoardsOption(hist: EmotionPoint[]): Record<string, unknown> | null {
  if (hist.length === 0) return null;
  return {
    ...base(hist),
    yAxis: { type: "value", name: "板", minInterval: 1 },
    series: [
      {
        name: "最高连板",
        type: "line",
        data: hist.map((p) => p.max_boards),
        // 只有 15 个点左右，纯折线看不出具体值，必须带点
        showSymbol: true,
        symbolSize: 5,
        lineStyle: { width: 2 },
      },
    ],
  };
}

/**
 * 封板率 vs 炸板率：双折线，百分比轴。
 *
 * 为什么这两个放一张图：它们互补（封板率 + 炸板率 = 1），一起看才能判断
 * 「是封得住的强，还是炸得多的弱」。封板率单独下滑可能是尝试数变多。
 */
export function sealBreakOption(hist: EmotionPoint[]): Record<string, unknown> | null {
  if (hist.length === 0) return null;
  // null 必须保留成 null（ECharts 会留空），不能补 0 ——
  // 补 0 会造出一个假的「封板率归零」断崖，比缺数据更危险。
  const pct = (v: number | null | undefined) =>
    v === null || v === undefined || !Number.isFinite(v) ? null : Math.round(v * 1000) / 10;

  return {
    ...base(hist),
    yAxis: {
      type: "value",
      name: "%",
      max: 100,
      axisLabel: { formatter: "{value}%" },
    },
    series: [
      {
        name: "封板率",
        type: "line",
        data: hist.map((p) => pct(p.seal_rate)),
        showSymbol: true,
        symbolSize: 5,
        lineStyle: { width: 2 },
      },
      {
        name: "炸板率",
        type: "line",
        data: hist.map((p) => pct(p.break_rate)),
        showSymbol: true,
        symbolSize: 5,
        lineStyle: { width: 2, type: "dashed" },
      },
    ],
  };
}

/**
 * 连板梯队：横向柱状。
 *
 * 为什么横向：分类标签是「2板 / 3板 / 5板+」，横排读起来比竖排省眼睛，
 * 而且阶梯形状本身就是信息（是不是只有一个高标孤零零挂着）。
 */
export function ladderOption(ladder: LadderRow[] | null | undefined): Record<string, unknown> | null {
  const rows = [...(ladder ?? [])].sort((a, b) => a.boards - b.boards);
  if (rows.length === 0) return null;
  return {
    // right 要留够标签宽度：数值标在柱子右端，24px 会被裁掉（实测截图发现）
    grid: { left: 48, right: 44, top: 12, bottom: 20 },
    tooltip: { trigger: "axis" as const, axisPointer: { type: "shadow" as const } },
    xAxis: { type: "value", minInterval: 1, name: "家数" },
    yAxis: {
      type: "category",
      // 分类轴从下往上，排序后正序即「2板在底部、高板在顶部」，符合阶梯直觉
      data: rows.map((r) => (r.plus ? `${r.boards}板+` : `${r.boards}板`)),
      axisTick: { show: false },
    },
    series: [
      {
        name: "家数",
        type: "bar",
        data: rows.map((r) => r.count),
        barMaxWidth: 16,
        label: { show: true, position: "right" },
      },
    ],
  };
}
