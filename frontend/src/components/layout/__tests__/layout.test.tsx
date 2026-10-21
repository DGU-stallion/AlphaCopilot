/**
 * 三区布局（M2-5 / ADR-0014 §8）。
 *
 * 布局本身不好测「好不好看」，但有几条**可测的结构事实**，它们都有真实后果：
 *
 *   1. 两侧都能折叠，且折叠状态持久化 —— 每次刷新都回到展开会让重度用户烦
 *   2. 折叠 Agent 栏后主画布必须变宽 —— 否则折叠毫无意义
 *   3. 左导航 176/52、Agent 栏 360/44 —— 尺寸写错会让日期轴刻度挤成两行
 *   4. 主画布 minHeight:0 —— 缺了它 flex 子项不压缩，图表溢出
 *
 * 这里测结构，不测像素。像素靠截图人工验收。
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("react-router-dom", () => ({
  useLocation: () => ({ pathname: "/daily-review" }),
  Link: ({ children, ...rest }: { children: React.ReactNode }) => <a {...rest}>{children}</a>,
  Outlet: () => <div data-testid="outlet" />,
}));

vi.mock("@/components/ai/AiConsole", () => ({ AiConsole: () => null }));

import { Layout } from "@/components/layout/Layout";

function navAside() {
  return document.querySelector('[data-region="nav"]') as HTMLElement;
}
function agentRail() {
  return document.querySelector('[data-region="agent"]') as HTMLElement;
}
function canvas() {
  return document.querySelector('[data-region="canvas"]') as HTMLElement;
}

describe("三区布局结构", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.className = "dark";
  });

  it("有四个区域：nav / canvas / agent / bottom", () => {
    render(<Layout />);
    for (const r of ["nav", "canvas", "agent", "bottom"]) {
      expect(document.querySelector(`[data-region="${r}"]`), `缺 ${r}`).toBeTruthy();
    }
  });

  it("左导航展开 176、折叠 52", async () => {
    render(<Layout />);
    expect(navAside().style.width).toBe("176px");
    fireEvent.click(screen.getByTitle("收起导航"));
    await waitFor(() => expect(navAside().style.width).toBe("52px"));
  });

  it("Agent 栏展开 360、折叠 44", async () => {
    render(<Layout />);
    expect(agentRail().style.width).toBe("360px");
    fireEvent.click(screen.getByTitle("收起助手"));
    await waitFor(() => expect(agentRail().style.width).toBe("44px"));
  });

  it("折叠 Agent 栏后主画布吸收腾出的宽度（flex:1 + minWidth:0）", async () => {
    render(<Layout />);
    // jsdom 不做真实布局，量不到像素宽度。所以测「画布会不会吸收腾出的空间」这个
    // 因果链的两个必要条件：① Agent 栏确实变窄 ② 画布是 flex:1 且可压缩。
    // 缺 ② 的话折叠只会留下一条空白。
    fireEvent.click(screen.getByTitle("收起助手"));
    await waitFor(() => expect(agentRail().style.width).toBe("44px"));
    expect(canvas().className).toContain("flex-1");
    expect(canvas().style.minWidth).toBe("0");
  });

  it("主画布 minHeight:0（否则图表不压缩会溢出）", () => {
    // ADR-0014 §8 点名的坑：flex 子项默认 min-height:auto，图表会撑破父容器。
    render(<Layout />);
    // jsdom 把 0 归一化成 "0"（不是 "0px"），所以按值比较而不是按字符串
    expect(parseFloat(canvas().style.minHeight || "1")).toBe(0);
  });

  it("导航折叠状态会持久化，刷新后还在", async () => {
    const { unmount } = render(<Layout />);
    fireEvent.click(screen.getByTitle("收起导航"));
    await waitFor(() => expect(navAside().style.width).toBe("52px"));
    unmount();

    render(<Layout />);
    expect(navAside().style.width).toBe("52px");
  });

  it("Agent 栏折叠状态同样持久化（且与导航互不影响）", async () => {
    const { unmount } = render(<Layout />);
    fireEvent.click(screen.getByTitle("收起助手"));
    await waitFor(() => expect(agentRail().style.width).toBe("44px"));
    unmount();

    render(<Layout />);
    expect(agentRail().style.width).toBe("44px");
    expect(navAside().style.width).toBe("176px");   // 没被连带折叠
  });
});

describe("底栏的信息与开关", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.className = "dark";
  });

  it("底栏有涨跌口径切换入口", () => {
    render(<Layout />);
    expect(screen.getByRole("button", { name: /口径/ })).toBeTruthy();
  });

  it("点口径按钮切换 <html> 的 caliber-intl 类并落 localStorage", async () => {
    render(<Layout />);
    fireEvent.click(screen.getByRole("button", { name: /口径/ }));
    await waitFor(() => {
      expect(document.documentElement.classList.contains("caliber-intl")).toBe(true);
    });
    expect(localStorage.getItem("ac-caliber")).toBe("intl");
  });
});
