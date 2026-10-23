/**
 * 通用 block 渲染器（ADR-0016 决定 2）。
 *
 * 为什么需要它：`Backtest.tsx` 里已有一段「按 renderer 分派 lwc / echarts」的
 * 逻辑，但写死在一个页面里 —— 加一个新分析页就要复制一遍。抽出来之后，
 * 「加一个分析页」= 写一条 spec，不写 React。
 *
 * 这一层的测试只测**分派是否正确**，不测图画得好不好（那是截图人工验收）：
 * 分派错了就是「该用 LWC 的图被 ECharts 画了」，而 LWC 根本吃不了 ECharts option。
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { RenderBlock } from "@/lib/research";

// LWC / ECharts 都要 mock：jsdom 里 canvas 不可用，真跑会报错。
// mock 成带 data-* 的 div，断言「选对了哪个渲染器」而不是「画出了什么」。
vi.mock("@/components/charts/EquityChart", () => ({
  EquityChart: ({ payload }: { payload: { series?: unknown[] } }) => (
    <div data-testid="lwc-equity" data-series={payload?.series?.length ?? 0} />
  ),
}));
vi.mock("@/components/charts/PriceChart", () => ({
  PriceChart: ({ bars }: { bars: unknown[] }) => (
    <div data-testid="lwc-price" data-bars={bars.length} />
  ),
}));
// ROUND3 D5：无 drawdown + 多条 series 走 MultiLineChart（相关性叠加走势）。
// 这里也 mock：jsdom 里 canvas 不可用，真跑会报 matchMedia 不存在。
vi.mock("@/components/charts/MultiLineChart", () => ({
  MultiLineChart: ({ payload }: { payload: { series?: unknown[] } }) => (
    <div data-testid="lwc-multiline" data-series={payload?.series?.length ?? 0} />
  ),
}));
vi.mock("@/components/ui/EChart", () => ({
  EChart: ({ option }: { option: Record<string, unknown> | null }) => (
    <div data-testid="echarts" data-has-option={option ? "1" : "0"} />
  ),
}));

import { BlockRenderer } from "../BlockRenderer";

const base = { span: 1 } as const;

describe("BlockRenderer 的分派", () => {
  it("metric 块渲染成指标项，不走任何图表", () => {
    const block: RenderBlock = {
      ...base,
      kind: "metric",
      metric: { items: [{ label: "总收益", value: "12.3%", tone: "up" }] },
    };
    render(<BlockRenderer block={block} />);
    expect(screen.getByText("总收益")).toBeTruthy();
    expect(screen.getByText("12.3%")).toBeTruthy();
    expect(screen.queryByTestId("echarts")).toBeNull();
    expect(screen.queryByTestId("lwc-equity")).toBeNull();
  });

  it("table 块渲染成表格，表头与单元格都对", () => {
    const block: RenderBlock = {
      ...base,
      kind: "table",
      table: { columns: ["标的一", "权重"], rows: [["600519", 0.4]] },
    };
    render(<BlockRenderer block={block} />);
    expect(screen.getByText("标的一")).toBeTruthy();
    expect(screen.getByText("600519")).toBeTruthy();
  });

  it("markdown 块渲染文本", () => {
    const block: RenderBlock = { ...base, kind: "markdown", text: "这是一段说明" };
    render(<BlockRenderer block={block} />);
    expect(screen.getByText("这是一段说明")).toBeTruthy();
  });

  it("chart + renderer=lwc + 单条 series → 用 PriceChart（line 模式）", () => {
    const block: RenderBlock = {
      ...base,
      kind: "chart",
      renderer: "lwc",
      lwc: {
        series: [{ name: "滚动 Sharpe", points: [{ time: "2026-01-01", value: 1.2 }] }],
      } as never,
    };
    render(<BlockRenderer block={block} />);
    expect(screen.getByTestId("lwc-price")).toBeTruthy();
    expect(screen.queryByTestId("echarts")).toBeNull();
  });

  it("chart + renderer=lwc + 多条 series 但**无** drawdown 载荷 → 不该误用 EquityChart", () => {
    // 回归测试（真 bug，截图发现）：`backtest.equity` 本身就是 2 条 series
    // （策略 vs 买入持有）。曾经按「series > 1」分派，结果净值图被当成净值+回撤，
    // EquityChart 自动加了一个空回撤 pane，而后面那个 `backtest.drawdown` 块
    // 又画了一遍回撤 —— 同一屏两份回撤，且第一份是空线。
    //
    // ROUND3 D5 起：无 drawdown 的多条 series 走 MultiLineChart（多线同 pane），
    // 仍然**不是** EquityChart —— 上面这条判定的核心断言（不误用 EquityChart）不变。
    const block: RenderBlock = {
      ...base,
      kind: "chart",
      renderer: "lwc",
      lwc: {
        series: [
          { name: "策略", points: [{ time: "2026-01-01", value: 1.1 }] },
          { name: "买入持有", points: [{ time: "2026-01-01", value: 1.0 }] },
        ],
      } as never,
    };
    render(<BlockRenderer block={block} />);
    expect(screen.queryByTestId("lwc-equity")).toBeNull();
    expect(screen.getByTestId("lwc-multiline")).toBeTruthy();
  });

  it("chart + renderer=lwc + 有 drawdown 载荷 → 用 EquityChart 单实例多 pane", () => {
    const block: RenderBlock = {
      ...base,
      kind: "chart",
      renderer: "lwc",
      lwc: {
        series: [{ name: "策略", points: [{ time: "2026-01-01", value: 1.1 }] }],
        drawdown: [{ time: "2026-01-01", value: -0.05 }],
      } as never,
    };
    render(<BlockRenderer block={block} />);
    expect(screen.getByTestId("lwc-equity")).toBeTruthy();
  });

  it("chart + renderer=lwc 但**无** lwc 载荷 → 提示而不是白屏", () => {
    // 这是真实会发生的：老 spec / 后端未返 lwc 载荷。白屏会让用户以为坏了。
    const block: RenderBlock = { ...base, kind: "chart", renderer: "lwc" };
    render(<BlockRenderer block={block} />);
    expect(screen.getByText(/无数据|暂不可用/)).toBeTruthy();
  });

  it("chart + renderer=echarts → 用 EChart，且剥掉 option 里的 title", () => {
    // 标题由外层 panel 的 h3 显示；ECharts 再画一遍就是同一句话出现两次。
    const block: RenderBlock = {
      ...base,
      kind: "chart",
      renderer: "echarts",
      option: { title: { text: "重复标题" }, series: [] },
    };
    render(<BlockRenderer block={block} />);
    const el = screen.getByTestId("echarts");
    expect(el.getAttribute("data-has-option")).toBe("1");
  });

  it("chart + renderer=echarts 但无 option → 提示而不是白屏", () => {
    const block: RenderBlock = { ...base, kind: "chart", renderer: "echarts" };
    render(<BlockRenderer block={block} />);
    expect(screen.getByText(/无数据|暂不可用/)).toBeTruthy();
  });

  it("chart 缺 renderer（老数据）→ 不猜，给提示", () => {
    // 猜默认值会「同一图形两套实现」（ADR-0014 图表分工反对的正是这个）。
    const block: RenderBlock = { ...base, kind: "chart", option: { series: [] } };
    render(<BlockRenderer block={block} />);
    expect(screen.getByText(/无数据|暂不可用|未知/)).toBeTruthy();
    expect(screen.queryByTestId("echarts")).toBeNull();
  });

  it("标题存在时显示出来（block.title 由后端给）", () => {
    const block: RenderBlock = {
      ...base,
      kind: "chart",
      title: "滚动 Sharpe",
      renderer: "echarts",
      option: { series: [] },
    };
    render(<BlockRenderer block={block} />);
    expect(screen.getByText("滚动 Sharpe")).toBeTruthy();
  });
});
