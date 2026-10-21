/**
 * 全站数据时点（M5-4）。
 *
 * 测的核心是一件事：**「未知」不能被显示成「今天」**。
 * 假的时间戳比没有时间戳更危险 —— 它让人相信它。
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  DataAsOfProvider, useDataAsOf, useDataAsOfAuto, useDataAsOfValue, formatAsOf,
  type DataAsOf,
} from "@/lib/data-asof";

function Probe({ info }: { info: DataAsOf | null }) {
  useDataAsOf(info);
  const v = useDataAsOfValue();
  return <span data-testid="out">{v ? `${v.dataAsOf}|${v.label ?? ""}` : "none"}</span>;
}

describe("页面报告时点 → 底栏可读", () => {
  it("页面报告的 as-of 能被消费方读到", () => {
    render(
      <DataAsOfProvider>
        <Probe info={{ dataAsOf: "2026-10-21", fetchedAt: Date.now(), label: "打板情绪" }} />
      </DataAsOfProvider>,
    );
    expect(screen.getByTestId("out").textContent).toBe("2026-10-21|打板情绪");
  });

  it("传 null 表示「本页无数据」，与「有数据但时点未知」区分", () => {
    const { unmount } = render(
      <DataAsOfProvider>
        <Probe info={{ dataAsOf: "2026-10-21", fetchedAt: Date.now() }} />
      </DataAsOfProvider>,
    );
    expect(screen.getByTestId("out").textContent).toContain("2026-10-21");
    unmount();

    render(
      <DataAsOfProvider>
        <Probe info={null} />
      </DataAsOfProvider>,
    );
    expect(screen.getByTestId("out").textContent).toBe("none");
  });

  it("页面卸载后清空（旧页的时点不能留在新页上）", () => {
    const { rerender } = render(
      <DataAsOfProvider>
        <Probe info={{ dataAsOf: "2026-10-20", fetchedAt: Date.now() }} />
      </DataAsOfProvider>,
    );
    expect(screen.getByTestId("out").textContent).toContain("2026-10-20");
    rerender(
      <DataAsOfProvider>
        <Probe info={null} />
      </DataAsOfProvider>,
    );
    expect(screen.getByTestId("out").textContent).toBe("none");
  });
});

describe("依赖稳定性（无限重渲染的守门）", () => {
  it("页面每次渲染都传新对象、但字段不变时，不该反复 setState", async () => {
    // 抓的是实测遇到的坑：调用方写 `fetchedAt: Date.now()` 在渲染体里，
    // 每次渲染都是新值 → effect 每次都跑 → setState → 再渲染 → 无限循环。
    // 所以 useDataAsOf 的依赖必须是**具体字段**，不是对象本身。
    const { render } = await import("@testing-library/react");
    let renders = 0;
    function Unstable() {
      renders += 1;
      useDataAsOf({ dataAsOf: "2026-10-21", fetchedAt: 1000, label: "x" });  // 每次新对象
      return null;
    }
    render(
      <DataAsOfProvider>
        <Unstable />
      </DataAsOfProvider>,
    );
    // 如果没有无限循环，这里能正常返回且渲染次数是有限的小数字。
    // React 会在无限 setState 时抛 "Maximum update depth exceeded"，测试会失败。
    expect(renders).toBeLessThan(10);
  });
});

describe("useDataAsOfAuto（防无限重渲染的安全变体）", () => {
  it("字段不变时反复渲染，不会无限 setState", async () => {
    // 这条守的是实测崩过的场景：页面写 `fetchedAt: Date.now()` 在渲染体里
    // → 每次渲染新值 → effect 反复触发 → React 抛
    // "Maximum update depth exceeded"。整页崩，但单测页面组件时看不出来。
    const { render } = await import("@testing-library/react");
    let renders = 0;
    function Page() {
      renders += 1;
      useDataAsOfAuto({ dataAsOf: "2026-10-21", label: "x" });
      return null;
    }
    render(
      <DataAsOfProvider>
        <Page />
      </DataAsOfProvider>,
    );
    expect(renders).toBeLessThan(10);
  });

  it("as-of 变化时会更新，且 fetchedAt 不倒退", async () => {
    const { renderHook } = await import("@testing-library/react");
    const { wrapper } = await import("@testing-library/react").then((m) => ({
      wrapper: ({ children }: { children: React.ReactNode }) =>
        <DataAsOfProvider>{children}</DataAsOfProvider>,
    }));
    const { result, rerender } = renderHook(
      ({ v }: { v: string }) => {
        useDataAsOfAuto({ dataAsOf: v, label: "y" });
        return useDataAsOfValue();
      },
      { initialProps: { v: "2026-10-20" }, wrapper },
    );
    expect(result.current?.dataAsOf).toBe("2026-10-20");
    const t1 = result.current?.fetchedAt ?? 0;
    rerender({ v: "2026-10-21" });
    expect(result.current?.dataAsOf).toBe("2026-10-21");
    expect(result.current!.fetchedAt).toBeGreaterThanOrEqual(t1);
  });
});

describe("formatAsOf 的文案", () => {
  it("无数据 → 无数据", () => {
    expect(formatAsOf(null)).toEqual({ text: "无数据", stale: false });
  });

  it("有数据但时点未知 → 明确说未知，且标为可疑", () => {
    // 这是最重要的一条：不能因为不知道就显示成今天的日期
    const r = formatAsOf({ dataAsOf: "", fetchedAt: 0 });
    expect(r.text).toBe("时点未知");
    expect(r.stale).toBe(true);
  });

  it("今天的数据显示日期 + 时分", () => {
    const now = new Date();
    const r = formatAsOf({ dataAsOf: localDay(now), fetchedAt: now.getTime() });
    expect(r.text).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
    expect(r.stale).toBe(false);
  });

  it("非今日数据要标「非今日」（否则用户会以为是今天的）", () => {
    const yesterday = new Date(Date.now() - 86400_000);
    const r = formatAsOf({ dataAsOf: localDay(yesterday), fetchedAt: yesterday.getTime() });
    expect(r.text).toContain("非今日");
    expect(r.stale).toBe(true);
  });

  it("dataAsOf 是今天但取数是昨天：按取数时间判为过期", () => {
    // 极端但真实的场景：周末取的「今天」数据被缓存到周一
    const yesterday = new Date(Date.now() - 86400_000);
    const r = formatAsOf({ dataAsOf: localDay(new Date()), fetchedAt: yesterday.getTime() });
    expect(r.stale).toBe(true);
  });
});

function localDay(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
