/**
 * 盘面类图表 option 构建（ROUND2 阶段 2 续）。
 *
 * 与 `emotion-charts.ts` 分开：那个是「情绪时间序列」，这里是「当日截面排名」，
 * 两者喂的数据形状与交互都不一样，混在一个文件里迟早变成杂物间。
 *
 * 用户原话：「资金流入流出可以做成面积图或者 whatever」。选横向双向柱而不是
 * 面积图，因为这是**截面排名**不是时间序列 —— 面积图表达「累积/取舍」，
 * 排行表达「谁多谁少」，用错图形会让人以为在看趋势。
 */

export interface SectorFlowRow {
  name: string;
  /** 净流入（亿元）= inflow - outflow */
  net: number;
  /** 行业整体涨跌% */
  pct: number;
  inflow: number;
  outflow: number;
  firms: number;
}

/**
 * 板块资金净流入横向柱（正负双向）。
 *
 * 三个设计决定：
 *   · **横向**：行业名是中文长标签，竖排柱的 x 轴会挤成两行甚至重叠。
 *   · **按净流入降序**：排行榜的第一名就是读者想先看的那个。
 *   · **正负同色系**：靠 `semanticScale: "pnl-bars"` 让 EChart 按正负上
 *     涨/跌色（切国际口径自动反向），不在这里写颜色。
 */
export function sectorFlowOption(
  rows: SectorFlowRow[] | null | undefined,
  limit = 15,
): Record<string, unknown> | null {
  const picked = [...(rows ?? [])]
    .filter((r) => typeof r?.net === "number" && Number.isFinite(r.net))
    .sort((a, b) => b.net - a.net)
    .slice(0, limit);

  if (picked.length === 0) return null;

  return {
    grid: { left: 68, right: 56, top: 8, bottom: 20 },
    tooltip: { trigger: "axis" as const, axisPointer: { type: "shadow" as const } },
    xAxis: { type: "value", name: "亿", nameTextStyle: { align: "right" } },
    yAxis: {
      type: "category",
      // 横向柱的分类轴从下往上画：reverse 后「最大流入」在顶部
      data: picked.map((r) => r.name).reverse(),
      axisTick: { show: false },
    },
    series: [
      {
        name: "净流入",
        type: "bar",
        data: picked.map((r) => r.net).reverse(),
        // 逐柱按正负上色（EChart 的 retintBars 消费该标记）
        semanticScale: "pnl-bars",
        barMaxWidth: 14,
        // 标签带单位：读图不用回头查表头
        label: { show: true, position: "right", formatter: "{c} 亿" },
      },
    ],
  };
}
