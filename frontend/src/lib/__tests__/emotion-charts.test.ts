/**
 * 情绪历史图表的 option 构建（ROUND2 阶段 2）。

 * 用户原话：「能用图表进行信息的表达就优先使用图表，因为单纯的独立的数字是
 * 看不出来什么的，需要跟之前的数据进行比对才知道」。
 *
 * 所以这里的每个函数都吃**一段历史序列**（不只是当天一个数），输出 ECharts option。
 * 纯函数：不碰 DOM、不读全局状态，可以直接单测。
 */
import { describe, expect, it } from "vitest";
import {
  maxBoardsOption,
  sealBreakOption,
  ladderOption,
  ztDtZbOption,
  type EmotionPoint,
} from "../emotion-charts";

const hist: EmotionPoint[] = [
  { date: "2026-10-20", zt_count: 54, dt_count: 6, zb_count: 29, max_boards: 4, seal_rate: 0.651, break_rate: 0.349, lianban_count: 14 },
  { date: "2026-10-21", zt_count: 50, dt_count: 5, zb_count: 19, max_boards: 4, seal_rate: 0.725, break_rate: 0.275, lianban_count: 16 },
  { date: "2026-10-22", zt_count: 33, dt_count: 49, zb_count: 23, max_boards: 5, seal_rate: 0.589, break_rate: 0.411, lianban_count: 9 },
];

describe("情绪图表 option 构建", () => {
  it("涨停/跌停/炸板：三条柱系列，x 轴是日期", () => {
    const opt = ztDtZbOption(hist) as any;
    expect(opt.xAxis.data).toEqual(["10-20", "10-21", "10-22"]);
    expect(opt.series).toHaveLength(3);
    expect(opt.series.map((s: any) => s.name)).toEqual(["涨停", "跌停", "炸板"]);
    // 每条 series 的数据长度必须与 x 轴一致，否则 ECharts 会错位画
    for (const s of opt.series) expect(s.data).toHaveLength(3);
  });

  it("涨停柱用涨色、跌停柱用跌色（靠语义标记，不写死颜色）", () => {
    const opt = ztDtZbOption(hist) as any;
    const zt = opt.series.find((s: any) => s.name === "涨停");
    const dt = opt.series.find((s: any) => s.name === "跌停");
    // 涨停不是「正负号」语义，而是「涨/跌」语义 —— 用 itemStyle 语义字段表达，
    // 由 chart-theme 按当前口径换成具体色值。
    expect(zt.semanticTone).toBe("up");
    expect(dt.semanticTone).toBe("down");
  });

  it("最高连板：单条折线，带数据点（点少的时候必须显示标记）", () => {
    const opt = maxBoardsOption(hist) as any;
    expect(opt.series).toHaveLength(1);
    expect(opt.series[0].type).toBe("line");
    expect(opt.series[0].data).toEqual([4, 4, 5]);
    // 15 个点画纯折线看不出具体值，必须带 symbol
    expect(opt.series[0].showSymbol).toBe(true);
  });

  it("封板率/炸板率：双折线，百分比轴", () => {
    const opt = sealBreakOption(hist) as any;
    expect(opt.series).toHaveLength(2);
    // 转成百分数（0.589 → 58.9），否则 y 轴显示 0.589 看着不像「率」
    expect(opt.series[0].data[2]).toBeCloseTo(58.9, 1);
    expect(opt.yAxis.axisLabel.formatter).toContain("%");
  });

  it("封板率缺失（null）时该点留空，不补 0", () => {
    // 补 0 会在图上造出一个假的「封板率归零」断崖 —— 比缺数据更危险。
    const withNull: EmotionPoint[] = [
      { ...hist[0], seal_rate: null },
      hist[1],
    ];
    const opt = sealBreakOption(withNull) as any;
    expect(opt.series[0].data[0]).toBeNull();
  });

  it("连板梯队：横向柱状，按板数升序", () => {
    const opt = ladderOption([
      { boards: 2, count: 5, plus: false },
      { boards: 5, count: 2, plus: true },
      { boards: 3, count: 2, plus: false },
    ]) as any;
    // 分类轴（y）从下往上，所以要 reverse 才让 2 板显示在底部
    expect(opt.yAxis.data).toEqual(["2板", "3板", "5板+"]);
    expect(opt.series[0].type).toBe("bar");
    expect(opt.series[0].data).toEqual([5, 2, 2]);
  });

  it("所有 option 都**不传 legend**（窄容器会压绘图区）", () => {
    for (const opt of [
      ztDtZbOption(hist),
      maxBoardsOption(hist),
      sealBreakOption(hist),
      ladderOption([{ boards: 2, count: 1, plus: false }]),
    ] as any[]) {
      expect(opt.legend).toBeUndefined();
    }
  });

  it("空历史返回 null（让调用方显式处理空态，而不是画一张空白图）", () => {
    expect(ztDtZbOption([])).toBeNull();
    expect(maxBoardsOption([])).toBeNull();
    expect(sealBreakOption([])).toBeNull();
    expect(ladderOption([])).toBeNull();
  });
});
