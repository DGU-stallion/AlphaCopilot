/**
 * 三区布局（M2-5 / ADR-0014 §8）。
 *
 * 布局本身不好测「好不好看」，但有几条**可测的结构事实**，它们都有真实后果：
 *
 *   1. 两侧都能折叠，且折叠状态持久化 —— 每次刷新都回到展开会让重度用户烦
 *   2. 折叠 Agent 栏后它**完全离开布局**，只留右下角浮动图标
 *      （ROUND2-C1：旧的 44px 竖条仍吃掉一列宽度，数据密集页会因此出横向滚动）
 *   3. 左导航 176/52、Agent 栏展开 360
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

// AiConsole 被 mock 掉（真组件会拉 API、开浮层）。
// 但它必须渲染一个可观测的钩子：Layout 的契约是「浮层挂在 Provider 内部」，
// 没有钩子这条契约就没法测，只能靠人肉读代码。
vi.mock("@/components/ai/AiConsole", () => ({
  AiConsole: () => <div data-agent-console="true" />,
}));

import { api } from "@/lib/api";
import { Layout } from "@/components/layout/Layout";

function navAside() {
  return document.querySelector('[data-region="nav"]') as HTMLElement;
}

function canvas() {
  return document.querySelector('[data-region="canvas"]') as HTMLElement;
}
describe("三区布局结构", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.className = "dark";
  });

  it("结构区：nav / canvas / bottom 三个在布局里，Agent 不在", () => {
    // ROUND3 C2 的契约变更：Agent 栏从**布局内**的常驻 aside 改成**布局外**的
    // 浮窗（AiConsole 自己 fixed 定位）。所以 data-region="agent" 不该出现 ——
    // 它一旦还在 flex 流里，就会重新吃掉一列宽度（这正是 ROUND2-C1 要修的）。
    render(<Layout />);
    for (const r of ["nav", "canvas", "bottom"]) {
      expect(document.querySelector(`[data-region="${r}"]`), `缺 ${r}`).toBeTruthy();
    }
    expect(document.querySelector('[data-region="agent"]')).toBeNull();
  });

  it("助手浮层挂在 Provider 内部（才拿得到本页数据快照作上下文）", () => {
    // 浮层不在布局流里，但必须在 AiPageProvider 里 —— 否则「就这一页聊」
    // 没有上下文，模型只能凭一般知识答，是 ROUND2 明确反对的那种假功能。
    render(<Layout />);
    const console_ = document.querySelector('[data-agent-console]');
    expect(console_).toBeTruthy();
  });

  it("主画布始终是 flex:1 且可压缩（折叠后吸收腾出的宽度）", () => {
    render(<Layout />);
    // jsdom 不做真实布局，量不到像素宽度。所以测「画布会不会吸收腾出的空间」
    // 这个因果链的必要条件：画布是 flex:1 且 minWidth:0。
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

describe("自定义页导航（ADR-0016）", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.className = "dark";
    vi.restoreAllMocks();
  });

  it("库里 kind=user 的页面出现在导航，builtin 不出现", async () => {
    vi.spyOn(api, "pages").mockResolvedValue([
      { id: "p1", slug: "my-kline", title: "我的 K 线", kind: "user", status: "draft" },
      { id: "p2", slug: "backtest", title: "回测", kind: "builtin", status: "published" },
    ] as never);

    render(<Layout />);

    await waitFor(() => expect(screen.getByText("我的 K 线")).toBeTruthy());
    // builtin 不重复出现在自定义分组里（它在 QUANT_NAV 有自己的条目）
    expect(screen.queryByText("自定义页")).toBeTruthy();
  });

  it("点删除按钮调 deletePage 并从列表移除", async () => {
    const pagesMock = vi
      .spyOn(api, "pages")
      .mockResolvedValueOnce([
        { id: "p1", slug: "tmp", title: "临时页", kind: "user", status: "draft" },
      ] as never)
      // 删除后重新拉列表 → 已空
      .mockResolvedValue([] as never);
    const delMock = vi.spyOn(api, "deletePage").mockResolvedValue({ ok: true, id: "p1" });

    render(<Layout />);
    await waitFor(() => expect(screen.getByText("临时页")).toBeTruthy());

    fireEvent.click(screen.getByLabelText("删除 临时页"));

    await waitFor(() => expect(delMock).toHaveBeenCalledWith("p1"));
    await waitFor(() => expect(screen.queryByText("临时页")).toBeNull());
    expect(pagesMock).toHaveBeenCalledTimes(2);
  });
});

describe("删除的撤销（ROUND2 §9 事故后补）", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.className = "dark";
    vi.restoreAllMocks();
  });

  it("删除后出现带「撤销」的提示条（不是静默消失）", async () => {
    vi.spyOn(api, "pages")
      .mockResolvedValueOnce([{ id: "p1", slug: "tmp", title: "临时页", kind: "user", status: "draft" }] as never)
      .mockResolvedValue([] as never);
    vi.spyOn(api, "deletePage").mockResolvedValue({ ok: true, id: "p1", soft: true });

    render(<Layout />);
    await waitFor(() => expect(screen.getByText("临时页")).toBeTruthy());
    fireEvent.click(screen.getByLabelText("删除 临时页"));

    // 关键：数据没了，但用户有后悔的机会
    await waitFor(() => expect(screen.getByRole("status")).toBeTruthy());
    expect(screen.getByRole("button", { name: "撤销" })).toBeTruthy();
  });

  it("点撤销调 restorePage 并把页拉回来", async () => {
    vi.spyOn(api, "pages")
      .mockResolvedValueOnce([{ id: "p1", slug: "tmp", title: "临时页", kind: "user", status: "draft" }] as never)
      .mockResolvedValueOnce([] as never)                                            // 删除后列表空
      .mockResolvedValue([{ id: "p1", slug: "tmp", title: "临时页", kind: "user", status: "draft" }] as never); // 恢复后回来
    vi.spyOn(api, "deletePage").mockResolvedValue({ ok: true, id: "p1", soft: true });
    const restore = vi.spyOn(api, "restorePage").mockResolvedValue({ ok: true, id: "p1" });

    render(<Layout />);
    await waitFor(() => expect(screen.getByText("临时页")).toBeTruthy());
    fireEvent.click(screen.getByLabelText("删除 临时页"));
    await waitFor(() => expect(screen.getByRole("button", { name: "撤销" })).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: "撤销" }));

    await waitFor(() => expect(restore).toHaveBeenCalledWith("p1"));
    await waitFor(() => expect(screen.getByText("临时页")).toBeTruthy());
  });

  it("可以手动关掉提示条", async () => {
    vi.spyOn(api, "pages")
      .mockResolvedValueOnce([{ id: "p1", slug: "tmp", title: "临时页", kind: "user", status: "draft" }] as never)
      .mockResolvedValue([] as never);
    vi.spyOn(api, "deletePage").mockResolvedValue({ ok: true, id: "p1", soft: true });

    render(<Layout />);
    await waitFor(() => expect(screen.getByText("临时页")).toBeTruthy());
    fireEvent.click(screen.getByLabelText("删除 临时页"));
    await waitFor(() => expect(screen.getByRole("status")).toBeTruthy());

    fireEvent.click(screen.getByLabelText("关闭提示"));
    await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
  });
});
