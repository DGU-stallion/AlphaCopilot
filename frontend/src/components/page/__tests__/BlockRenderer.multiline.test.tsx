/**
 * BlockRenderer 的 lwc 分派：**单条 / 多条**（ROUND3 D5）。
 *
 * 背景（真 bug，截图发现）：曾经按「series 条数 > 1」直接上 EquityChart，
 * 于是 `backtest.equity`（策略 + 买入持有 = 2 条）被当成「净值 + 回撤」，
 * EquityChart 自动补了一个空回撤 pane，后面的 `backtest.drawdown` 块又画一遍 ——
 * 同一屏两份回撤。**真正的判别符是 `payload.drawdown` 有没有值。**
 *
 * D5 只在那条判定的**下游**细分：没有 drawdown 时，
 *   1 条 → PriceChart（现状，单线折线）
 *   >1 条 → MultiLineChart（相关性叠加走势，N 条线同 pane）
 * 有 drawdown 时仍然一律 EquityChart，一行判定都不动。
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { RenderBlock } from "@/lib/research";

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
vi.mock("@/components/charts/MultiLineChart", () => ({
  MultiLineChart: ({ payload }: { payload: { series?: unknown[] } }) => (
    <div data-testid="lwc-multiline" data-series={payload?.series?.length ?? 0} />
  ),
}));
vi.mock("@/components/ui/EChart", () => ({
  EChart: () => <div data-testid="echarts" />,
}));

import { BlockRenderer } from "../BlockRenderer";

const point = { time: "2025-01-02", value: 100 };

const chartBlock = (lwc: unknown): RenderBlock => ({
  kind: "chart",
  span: 2,
  renderer: "lwc",
  lwc: lwc as never,
});

describe("BlockRenderer：lwc 载荷的单条 / 多条分派", () => {
  it("无 drawdown + 多条 series（相关性叠加走势）→ MultiLineChart", () => {
    render(
      <BlockRenderer
        block={chartBlock({
          series: [
            { name: "贵州茅台", points: [point, { time: "2025-01-03", value: 101 }] },
            { name: "五粮液", points: [point, { time: "2025-01-03", value: 99 }] },
          ],
          drawdown: [],
        })}
      />,
    );
    const el = screen.getByTestId("lwc-multiline");
    expect(el.getAttribute("data-series")).toBe("2");
    expect(screen.queryByTestId("lwc-price")).toBeNull();
    expect(screen.queryByTestId("lwc-equity")).toBeNull();
  });

  it("无 drawdown + 单条 series（滚动相关）→ 仍走 PriceChart", () => {
    render(
      <BlockRenderer
        block={chartBlock({
          series: [{ name: "滚动20日相关", points: [point, { time: "2025-01-03", value: 0.5 }] }],
          drawdown: [],
        })}
      />,
    );
    expect(screen.getByTestId("lwc-price")).toBeTruthy();
    expect(screen.queryByTestId("lwc-multiline")).toBeNull();
  });

  it("有 drawdown + 多条 series → 仍走 EquityChart（drawdown 判别优先，不被条数改写）", () => {
    render(
      <BlockRenderer
        block={chartBlock({
          series: [
            { name: "策略", points: [point] },
            { name: "买入持有", points: [point] },
          ],
          drawdown: [{ time: "2025-01-02", value: -0.02 }],
        })}
      />,
    );
    expect(screen.getByTestId("lwc-equity")).toBeTruthy();
    expect(screen.queryByTestId("lwc-multiline")).toBeNull();
  });

  it("有 drawdown + 单条 series → EquityChart（回撤是同实例第二个 pane）", () => {
    render(
      <BlockRenderer
        block={chartBlock({
          series: [{ name: "净值", points: [point] }],
          drawdown: [{ time: "2025-01-02", value: 0 }],
        })}
      />,
    );
    expect(screen.getByTestId("lwc-equity")).toBeTruthy();
    expect(screen.queryByTestId("lwc-price")).toBeNull();
  });
});
