/**
 * 盘面类图表 option 构建（ROUND2 阶段 2 续）。
 *
 * 与 `emotion-charts.ts` 分开：那个是「情绪时间序列」，这里是「当日截面排名」，
 * 两者喂的数据形状与交互都不一样，混在一个文件里迟早变成杂物间。
 */
import { describe, expect, it } from "vitest";
import { sectorFlowOption, type SectorFlowRow } from "../market-charts";

const rows: SectorFlowRow[] = [
  { name: "半导体", net: 86.42, pct: 3.85, inflow: 412.56, outflow: 326.14, firms: 168 },
  { name: "证券", net: 64.18, pct: 2.31, inflow: 289.34, outflow: 225.16, firms: 54 },
  { name: "银行", net: -22.15, pct: -0.42, inflow: 88.72, outflow: 110.87, firms: 42 },
  { name: "房地产", net: -31.08, pct: -1.23, inflow: 104.23, outflow: 135.31, firms: 116 },
];

describe("板块资金流向图", () => {
  it("横向柱：y 轴是行业名，按净流入降序（最大流入在最上面）", () => {
    const opt = sectorFlowOption(rows) as any;
    // 横向柱的 y 分类轴从下往上画，所以要 reverse 才能让第一名在顶部
    expect(opt.yAxis.data).toEqual(["房地产", "银行", "证券", "半导体"]);
  });

  it("数据是净流入，逐柱按正负上色（semanticScale 而非写死颜色）", () => {
    const opt = sectorFlowOption(rows) as any;
    expect(opt.series[0].data).toEqual([-31.08, -22.15, 64.18, 86.42]);
    // 正负上色交给 EChart 的 retintBars（AGENTS 硬规则 7：不写颜色字面量）
    expect(opt.series[0].semanticScale).toBe("pnl-bars");
  });

  it("尊重 limit：只要前 N 个行业", () => {
    const opt = sectorFlowOption(rows, 2) as any;
    expect(opt.yAxis.data).toHaveLength(2);
  });

  it("空数据返回 null（调用方显式处理空态，不画空白图）", () => {
    expect(sectorFlowOption([])).toBeNull();
    expect(sectorFlowOption(null)).toBeNull();
  });

  it("不传 legend（窄容器会压绘图区）", () => {
    expect((sectorFlowOption(rows) as any).legend).toBeUndefined();
  });

  it("数值标签带单位，读图不用回头查表头", () => {
    const opt = sectorFlowOption(rows) as any;
    expect(opt.series[0].label.show).toBe(true);
    expect(opt.series[0].label.formatter).toContain("亿");
  });
});
