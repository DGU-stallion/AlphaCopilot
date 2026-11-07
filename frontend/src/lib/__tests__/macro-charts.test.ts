/**
 * 宏观图表 option（ROUND3 D4）。
 *
 * 用户的判定是「宏观看板**内容不足**」，不是密度不够 —— 所以这一层存在的
 * 唯一理由就是**把单点变成序列**。测试因此盯的是「序列有没有真的进去」，
 * 而不是样式细节。
 */
import { describe, expect, it } from "vitest";
import {
  latestPeriod, latestValue, levelSeriesOption, netFlowOption,
  pmiOption, socialFinancingOption, yieldCurveOption, type SeriesPoint,
} from "@/lib/macro-charts";

const pts = (vals: (number | null)[], base = "2026-01"): SeriesPoint[] =>
  vals.map((v, i) => ({ period: `${base}-${String(i + 1).padStart(2, "0")}`, value: v }));

describe("社融", () => {
  it("柱状 + 零轴，逐柱按正负上色（负的社融必须看得出来）", () => {
    const opt = socialFinancingOption(pts([100, -30, 50])) as any;
    expect(opt.series[0].type).toBe("bar");
    expect(opt.series[0].data).toEqual([100, -30, 50]);
    // 复用 EChart 已有的 pnl-bars 约定，而不是自己造一套 signTone
    expect(opt.series[0].semanticScale).toBe("pnl-bars");
  });

  it("空序列返回 null（宁可显示「暂不可用」，也不画空轴）", () => {
    // 空轴会被读成「数据是 0」，比不画更误导
    expect(socialFinancingOption([])).toBeNull();
  });
});

describe("PMI", () => {
  it("带 50 荣枯线 markLine（这条线是判读 PMI 的坐标系原点）", () => {
    const opt = pmiOption(pts([50.1, 49.8])) as any;
    const data = opt.series[0].markLine.data;
    expect(data).toHaveLength(1);
    expect(data[0].yAxis).toBe(50);
  });

  it("yAxis 必须 scale（从 0 起画会把 PMI 压成一条贴顶直线）", () => {
    const opt = pmiOption(pts([50.1, 49.8])) as any;
    expect(opt.yAxis.scale).toBe(true);
  });

  it("任何 option 都不带 legend（窄容器下 legend 会压绘图区）", () => {
    for (const o of [
      pmiOption(pts([50])), socialFinancingOption(pts([1])),
      levelSeriesOption(pts([1]), { name: "x", unit: "%" }),
      netFlowOption(pts([1])),
    ] as any[]) {
      expect(o.legend).toBeUndefined();
    }
  });
});

describe("国债收益率曲线", () => {
  it("横轴是期限（不是时间）—— 曲线看的是形状，倒挂只能在期限轴上看出", () => {
    const opt = yieldCurveOption([
      { tenor: "1y", value: 1.15 }, { tenor: "10y", value: 1.64 },
    ]) as any;
    expect(opt.xAxis.data).toEqual(["1Y", "10Y"]);
    expect(opt.series[0].data).toEqual([1.15, 1.64]);
    expect(opt.yAxis.scale).toBe(true);
  });
});

describe("水平值序列", () => {
  it("单值序列用折线（水平值可以「从上一期连过来」，增量不行）", () => {
    const opt = levelSeriesOption(pts([3.0, 2.95]), { name: "LPR 1Y", unit: "%" }) as any;
    expect(opt.series[0].type).toBe("line");
    expect(opt.yAxis.scale).toBe(true);
  });
});

describe("当前读数", () => {
  it("取最后一个**非空**值（当月未发布时留 null，直接取尾巴会显示「—」）", () => {
    expect(latestValue(pts([1, 2, null]))).toBe(2);
    expect(latestPeriod(pts([1, 2, null]))).toBe("2026-01-02");
  });

  it("全空序列返回 null，不返回 0", () => {
    // 返回 0 会在读数位置显示「0.00」，看起来像「真的算出来是 0」
    expect(latestValue(pts([null, null]))).toBeNull();
    expect(latestPeriod([])).toBeNull();
  });
});
