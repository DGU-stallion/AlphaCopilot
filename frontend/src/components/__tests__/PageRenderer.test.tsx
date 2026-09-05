import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { PageRenderer } from "@/components/PageRenderer";
import { ThemeProvider } from "@/theme";

// ChartBlock 依赖 echarts + ResizeObserver：mock 掉实例、补 ResizeObserver。
vi.mock("@/lib/echarts", () => ({
  echarts: { init: () => ({ setOption: () => {}, resize: () => {}, dispose: () => {} }) },
}));
vi.mock("@/lib/chart-theme", () => ({
  getChartTheme: () => ({
    textColor: "#fff",
    tooltipBg: "#000",
    tooltipBorder: "#111",
    tooltipText: "#fff",
  }),
}));
class RO {
  observe() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = RO;

// 对齐真实后端 GET /api/pages/{slug} 结构：params 在内层 spec 下。
const SPEC = {
  slug: "correlation",
  title: "相关性分析",
  kind: "builtin",
  status: "published",
  spec: {
    slug: "correlation",
    title: "相关性分析",
    kind: "builtin",
    layout: "grid",
    params: [
      { name: "symbols", type: "symbol_list", label: "标的", default: ["600519"] },
      { name: "window", type: "int", label: "窗口", default: 20, min: 5, max: 250 },
      { name: "range", type: "date_range", label: "区间", default: "1y" },
    ],
  },
};

function mockFetch(renderBlocks: unknown[]) {
  return vi.fn(async (url: string, opts?: RequestInit) => {
    if (url === "/api/pages/correlation" && !opts) {
      return new Response(JSON.stringify(SPEC), { status: 200 });
    }
    if (url === "/api/pages/correlation/render" && opts?.method === "POST") {
      return new Response(JSON.stringify({ blocks: renderBlocks }), { status: 200 });
    }
    return new Response("{}", { status: 200 });
  }) as unknown as typeof fetch;
}

function renderPage() {
  return render(
    <ThemeProvider>
      <PageRenderer slug="correlation" />
    </ThemeProvider>,
  );
}

describe("PageRenderer", () => {
  beforeEach(() => {
    global.fetch = mockFetch([]);
  });

  it("据 spec.params 生成三种控件（symbol_list / int / date_range）", async () => {
    renderPage();
    // symbol_list → text input，值为逗号拼接
    const symbols = (await screen.findByLabelText("标的")) as HTMLInputElement;
    expect(symbols.tagName).toBe("INPUT");
    expect(symbols.value).toBe("600519");
    // int → number input，带 min/max
    const window = screen.getByLabelText("窗口") as HTMLInputElement;
    expect(window.type).toBe("number");
    expect(window.min).toBe("5");
    expect(window.max).toBe("250");
    // date_range → select，含 1y/6m/3m
    const range = screen.getByLabelText("区间") as HTMLSelectElement;
    expect(range.tagName).toBe("SELECT");
    expect(range.value).toBe("1y");
    expect(Array.from(range.options).map((o) => o.value)).toEqual(["1y", "6m", "3m"]);
  });

  it("on_open 首次自动 render 一次", async () => {
    renderPage();
    await waitFor(() => {
      const calls = (global.fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls;
      expect(calls.some((c) => c[0] === "/api/pages/correlation/render")).toBe(true);
    });
  });

  it("改参点刷新 → 触发 render POST，body 含新参值", async () => {
    renderPage();
    const window = (await screen.findByLabelText("窗口")) as HTMLInputElement;
    fireEvent.change(window, { target: { value: "60" } });

    fireEvent.click(screen.getByRole("button", { name: "刷新" }));

    await waitFor(() => {
      const calls = (global.fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls;
      const posts = calls.filter(
        (c) => c[0] === "/api/pages/correlation/render" && (c[1] as RequestInit)?.method === "POST",
      );
      expect(posts.length).toBeGreaterThan(0);
      const last = posts[posts.length - 1];
      const body = JSON.parse((last[1] as RequestInit).body as string);
      expect(body.window).toBe(60);
    });
  });

  it("render 返回多 block → 多个容器渲染", async () => {
    global.fetch = mockFetch([
      { kind: "chart", span: 6, option: { series: [] } },
      { kind: "chart", span: 6, option: { series: [] } },
      { kind: "markdown", span: 12, text: "结论" },
    ]);
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByTestId("chart-block").length).toBe(2);
    });
    expect(screen.getByTestId("markdown-block")).toBeTruthy();
  });
});
