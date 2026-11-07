/**
 * MultiLineChart（ROUND3 D5）—— 相关性叠加走势：**一个 chart 实例，N 条线同 pane**。
 *
 * 这里测的是三条纪律（图本身好不好看靠人工截图）：
 *   1. 只有一个 createChart 实例（两个实例会让左右边缘差 5px、缩放/光标不联动）。
 *   2. 每个 payload series 一条 LineSeries，且 paneIndex 都是 0
 *      （相关性叠图量纲相同，不分 pane；分 pane 是「净值 vs 回撤」那种量纲不同的场景）。
 *   3. 0 基线画成一条 price line（相关性为负时能看出上下分界）。
 *
 * canvas 在 jsdom 里不可用 → 把 lightweight-charts 整个 mock 掉，
 * 断言的是「对 LWC 下发了什么指令」，不是「画出了什么像素」。
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const lwc = vi.hoisted(() => {
  const charts: {
    series: { api: unknown; paneIndex: number | undefined }[];
    addSeries: ReturnType<typeof vi.fn>;
    createPriceLineCalls: unknown[];
  }[] = [];

  const makeSeries = () => ({
    setData: vi.fn(),
    applyOptions: vi.fn(),
    createPriceLine: vi.fn((opts: unknown) => {
      const line = { applyOptions: vi.fn(), options: opts };
      lastPriceLines.push(opts);
      return line;
    }),
  });
  const lastPriceLines: unknown[] = [];

  const makeChart = () => {
    const chart = {
      series: [] as { api: unknown; paneIndex: number | undefined }[],
      addSeries: vi.fn((_def: unknown, _opts: unknown, paneIndex?: number) => {
        const api = makeSeries();
        chart.series.push({ api, paneIndex });
        return api;
      }),
      removeSeries: vi.fn(),
      applyOptions: vi.fn(),
      remove: vi.fn(),
      panes: () => [{}],
      priceScale: () => ({ applyOptions: vi.fn() }),
      timeScale: () => ({ fitContent: vi.fn() }),
      createPriceLineCalls: [] as unknown[],
    };
    charts.push(chart);
    return chart;
  };

  return { charts, makeChart, lastPriceLines };
});

vi.mock("lightweight-charts", () => ({
  LineSeries: "LineSeries",
  LineStyle: { Solid: 0, Dotted: 1, Dashed: 2 },
  createChart: lwc.makeChart,
}));

import { MultiLineChart } from "../MultiLineChart";
import type { LwcPayload } from "../equity-data";

const PAYLOAD: LwcPayload = {
  series: [
    {
      name: "贵州茅台",
      points: [
        { time: "2025-01-02", value: 100 },
        { time: "2025-01-03", value: 101.5 },
      ],
    },
    {
      name: "五粮液",
      points: [
        { time: "2025-01-02", value: 100 },
        { time: "2025-01-03", value: 98.5 },
      ],
    },
    {
      name: "泸州老窖",
      points: [
        { time: "2025-01-02", value: 100 },
        { time: "2025-01-03", value: 102 },
      ],
    },
  ],
  drawdown: [],
};

/** 最近一次渲染的 chart（每个用例前清空，避免跨用例串味）。 */
const chartOfLastRender = () => lwc.charts[lwc.charts.length - 1];

beforeEach(() => {
  lwc.charts.length = 0;
  lwc.lastPriceLines.length = 0;
});

describe("MultiLineChart", () => {
  it("只创建一个 chart 实例（多实例会让边缘不齐、缩放不联动）", () => {
    render(<MultiLineChart payload={PAYLOAD} />);
    expect(lwc.charts).toHaveLength(1);
  });

  it("每个 series 一条 LineSeries，且全部落在 pane 0（量纲相同不分区）", () => {
    render(<MultiLineChart payload={PAYLOAD} />);
    const chart = chartOfLastRender();
    expect(chart.addSeries).toHaveBeenCalledTimes(PAYLOAD.series.length);
    expect(chart.series.map((s) => s.paneIndex)).toEqual([0, 0, 0]);
  });

  it("数据只 setData，逐条传给对应 series", () => {
    render(<MultiLineChart payload={PAYLOAD} />);
    const chart = chartOfLastRender();
    PAYLOAD.series.forEach((s, i) => {
      const api = chart.series[i].api as { setData: ReturnType<typeof vi.fn> };
      const fed = api.setData.mock.calls[0][0] as { time: string; value: number }[];
      expect(fed).toHaveLength(s.points.length);
      expect(fed[0]).toEqual(s.points[0]);
    });
  });

  it("画一条 0 基线（相关性为负时要能看出上下分界）", () => {
    render(<MultiLineChart payload={PAYLOAD} />);
    expect(lwc.lastPriceLines).toHaveLength(1);
    expect((lwc.lastPriceLines[0] as { price: number }).price).toBe(0);
  });

  it("HTML 层自绘图例显示各 series 名字（图里没有 legend，线颜色需要对照）", () => {
    render(<MultiLineChart payload={PAYLOAD} />);
    for (const s of PAYLOAD.series) {
      expect(screen.getByText(s.name)).toBeTruthy();
    }
  });

  it("单条 series 不画图例（一条线不需要图例）", () => {
    render(<MultiLineChart payload={{ series: [PAYLOAD.series[0]], drawdown: [] }} />);
    expect(screen.queryByText("贵州茅台")).toBeNull();
  });

  it("载荷为空时给提示，不白屏；容器常驻所以实例只建一次", () => {
    render(<MultiLineChart payload={null} />);
    expect(screen.getByText(/无数据|暂不可用/)).toBeTruthy();
    // 实例随容器常驻，不因空载荷反复建/毁（反复重建会丢缩放与光标状态）
    expect(lwc.charts).toHaveLength(1);
  });
});
