/**
 * 宏观看板的内容（ROUND3 D4）。
 *
 * 用户反馈原文是「**内容不足**」不是密度不够，所以这里测的是：
 * 序列真的被画出来了？取不到的时候是不是**如实说明**（而不是画空轴 / 补 0）？
 */
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/ui/EChart", () => ({
  EChart: ({ option }: { option: Record<string, unknown> }) => (
    <div
      data-testid="chart"
      data-series={JSON.stringify((option as { series?: { name?: string }[] })?.series?.map((s) => s.name) ?? [])}
    />
  ),
}));
vi.mock("@/lib/ai-page", () => ({ useAiPage: () => {} }));

// vi.mock 的工厂会被提升到文件顶部，所以这里的数据必须用 vi.hoisted 定义，
// 否则会落到「Cannot access before initialization」。
const { series, unavailable, unavailableSeries } = vi.hoisted(() => ({
  series: (vals: number[], unit = "%") => ({
    available: true, reason: "", unit,
    points: vals.map((v, i) => ({ period: `2026-01-${String(i + 1).padStart(2, "0")}`, value: v })),
  }),
  unavailableSeries: () => ({ available: false, reason: "", unit: "", points: [] }),
  unavailable: (reason: string) => ({ available: false, reason, unit: "", points: [] }),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  const table: Record<string, () => Promise<unknown>> = {
    indices: async () => [],
    overseas: async () => ({ available: false }),
    macroCommodities: async () => ({ available: false }),
    macroForex: async () => ({ available: false }),
    macroRates: async () => ({ available: false }),
    macroCrypto: async () => ({ available: false }),
    socialFinancing: async () => series([100, 200, 300], "亿元"),
    pmi: async () => series([50.2, 49.8]),
    cnYields: async () => ({
      available: true, reason: "", unit: "%", date: "2026-10-22",
      points: [{ tenor: "1y", value: 1.15 }, { tenor: "10y", value: 1.64 }],
    }),
    lpr: async () => series([3.0, 2.95]),
    repo: async () => series([1.4, 1.5]),
    northbound: async () => unavailable("vendor 仅提供盘中分钟流向（历史自缓存 CSV 为空）"),
    margin: async () => unavailableSeries(),
  };
  const pick = (k: string) => table[k] ?? (async () => ({ available: false, reason: "", points: [] }));
  return {
    ...actual,
    api: new Proxy({} as Record<string, unknown>, { get: (_t, k: string) => pick(k) }),
    macroApi: new Proxy({} as Record<string, unknown>, { get: (_t, k: string) => pick(k) }),
  };
});

import { MacroDashboard } from "@/pages/MacroDashboard";

describe("宏观看板的内容", () => {
  it("出图而不是只有孤立数字", async () => {
    render(<MacroDashboard />);
    await waitFor(() => expect(screen.getAllByTestId("chart").length).toBeGreaterThanOrEqual(5));
  });

  it("每块都有标题（能看出在讲什么）", async () => {
    render(<MacroDashboard />);
    await waitFor(() => expect(screen.getByText(/社会融资规模增量/)).toBeTruthy());
    expect(screen.getByText(/制造业 PMI/)).toBeTruthy();
    expect(screen.getByText(/国债收益率曲线/)).toBeTruthy();
    expect(screen.getByText(/银行间回购定盘利率/)).toBeTruthy();
  });

  it("取不到的项**如实说明原因**，不画空轴", async () => {
    render(<MacroDashboard />);
    await waitFor(() =>
      expect(screen.getByText(/vendor 仅提供盘中分钟流向/)).toBeTruthy());
    // 两融 unavailable 且无 reason → 也必须有一句兜底说明，不能白着
    expect(screen.getAllByText(/暂不可用/).length).toBeGreaterThanOrEqual(1);
  });

  it("曲线图显示 10Y 读数（形状之外还要给一个可比的数）", async () => {
    render(<MacroDashboard />);
    await waitFor(() => expect(screen.getByText(/1\.64/)).toBeTruthy());
  });
});
