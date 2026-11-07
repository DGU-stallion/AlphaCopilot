/**
 * EChart 的语义上色（ROUND2 阶段 2）。
 *
 * 锁住一条：option 里**不允许出现颜色字面量**，只能标语义，
 * 由 chart-theme 换成当前 palette 的色值（AGENTS 硬规则 7）。
 */
import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const setOption = vi.fn();
vi.mock("@/lib/echarts", () => ({
  echarts: {
    init: () => ({ setOption, resize: vi.fn(), dispose: vi.fn(), clear: vi.fn() }),
  },
}));

import { EChart } from "@/components/ui/EChart";
import { getChartTheme } from "@/lib/chart-theme";

describe("EChart 的 semanticTone 上色", () => {
  it("semanticTone=up 的柱用涨色，down 用跌色", () => {
    const option = {
      series: [
        { name: "涨停", type: "bar", data: [1, 2], semanticTone: "up" },
        { name: "跌停", type: "bar", data: [3, 4], semanticTone: "down" },
      ],
    };
    render(<EChart option={option} />);
    const passed = setOption.mock.calls.at(-1)[0];
    const t = getChartTheme();
    expect(passed.series[0].itemStyle.color).toBe(t.upColor);
    expect(passed.series[1].itemStyle.color).toBe(t.downColor);
    // 语义字段不能传给 ECharts（它不认识，会当成未知配置）
    expect(passed.series[0].semanticTone).toBeUndefined();
  });

  it("semanticTone 用在折线上要改 lineStyle 颜色", () => {
    const option = {
      series: [{ name: "x", type: "line", data: [1], semanticTone: "down" }],
    };
    render(<EChart option={option} />);
    const passed = setOption.mock.calls.at(-1)[0];
    expect(passed.series[0].lineStyle.color).toBe(getChartTheme().downColor);
  });

  it("neutral 不加色（保持 seriesColors 默认序）", () => {
    const option = {
      series: [{ name: "炸板", type: "bar", data: [1], semanticTone: "neutral" }],
    };
    render(<EChart option={option} />);
    const passed = setOption.mock.calls.at(-1)[0];
    expect(passed.series[0].itemStyle).toBeUndefined();
  });
});
