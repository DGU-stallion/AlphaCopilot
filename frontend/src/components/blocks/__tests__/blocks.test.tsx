import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { TableBlock } from "@/components/blocks/TableBlock";
import { MarkdownBlock } from "@/components/blocks/MarkdownBlock";

describe("TableBlock", () => {
  it("渲染表头与行", () => {
    render(
      <TableBlock
        payload={{ columns: ["标的", "相关性"], rows: [["茅台", 0.82], ["五粮液", 0.75]] }}
        title="相关性表"
      />,
    );
    expect(screen.getByText("相关性表")).toBeTruthy();
    expect(screen.getByText("标的")).toBeTruthy();
    expect(screen.getByText("茅台")).toBeTruthy();
    expect(screen.getByText("0.82")).toBeTruthy();
    // 2 行数据
    const table = screen.getByTestId("table-block");
    expect(table.querySelectorAll("tbody tr").length).toBe(2);
  });
});

describe("MarkdownBlock", () => {
  it("渲染 markdown（含 gfm 表格）", () => {
    render(<MarkdownBlock payload={{ text: "## 结论\n\n白酒板块**高相关**。" }} title="报告" />);
    expect(screen.getByText("报告")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "结论" })).toBeTruthy();
    expect(screen.getByText("高相关")).toBeTruthy();
  });

  it("接受字符串 payload", () => {
    render(<MarkdownBlock payload={"纯文本结论"} />);
    expect(screen.getByText("纯文本结论")).toBeTruthy();
  });
});

// ChartBlock: mock echarts.init to assert setOption called with the option.
const setOptionSpy = vi.fn();
vi.mock("@/lib/echarts", () => ({
  echarts: {
    init: () => ({ setOption: setOptionSpy, resize: () => {}, dispose: () => {} }),
  },
}));
vi.mock("@/lib/chart-theme", () => ({
  getChartTheme: () => ({
    textColor: "#fff", tooltipBg: "#000", tooltipBorder: "#111", tooltipText: "#fff",
  }),
}));

// ResizeObserver 在 jsdom 不存在，补一个。
class RO {
  observe() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = RO;

describe("ChartBlock", () => {
  it("用 artifact.payload 调 setOption", async () => {
    setOptionSpy.mockClear();
    const { ChartBlock } = await import("@/components/blocks/ChartBlock");
    const { ThemeProvider } = await import("@/theme");
    const option = { series: [{ type: "heatmap", data: [[0, 0, 1]] }] };
    render(
      <ThemeProvider>
        <ChartBlock option={option} title="热力图" />
      </ThemeProvider>,
    );
    expect(screen.getByText("热力图")).toBeTruthy();
    expect(setOptionSpy).toHaveBeenCalled();
    const passed = setOptionSpy.mock.calls[0][0];
    expect(passed.series).toEqual(option.series);
  });
});
