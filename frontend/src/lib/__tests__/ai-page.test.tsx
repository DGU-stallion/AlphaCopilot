import { render, renderHook, act } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createElement, type ReactNode } from "react";
import { AiPageProvider, useAiPage, useCurrentAiPage } from "@/lib/ai-page";

// ai-page 是 8 个页面共用的登记处：页面 `set`，浮标 `read`。
// 它自己的行为错一次，所有页面的 AI 上下文就一起错，所以单独测。
//
// 这里测的是**约定**，不是实现：页面登记后浮标能读到；卸载后自动清空；
// 同一个 key 重复登记不抖动；suggestions 内容变化能被识别（它被压成
// 一个 sig 字符串来比较，这是最容易写错的一处）。

function wrapper({ children }: { children: ReactNode }) {
  return createElement(AiPageProvider, null, children);
}

const page = (over: Partial<Parameters<typeof useAiPage>[0]> = {}) => ({
  key: "k1",
  title: "测试页",
  context: "600519 现价 1500",
  suggestions: ["a", "b"],
  ...over,
});

describe("ai-page 登记处", () => {
  it("页面登记后，浮标侧能读到同一份快照", () => {
    const { result } = renderHook(
      () => {
        useAiPage(page());
        return useCurrentAiPage();
      },
      { wrapper },
    );

    expect(result.current?.key).toBe("k1");
    expect(result.current?.title).toBe("测试页");
    expect(result.current?.context).toContain("600519");
    expect(result.current?.suggestions).toEqual(["a", "b"]);
  });

  it("页面卸载后自动清空，不会把上一页的上下文留给下一页", () => {
    // 这条防的是「换页后浮标还显示上一页数据」——用户看到会以为
    // AI 在拿旧数据回答新问题。
    const { result, rerender } = renderHook(
      ({ mount }: { mount: boolean }) => {
        // 始终调用、参数给 null —— 不能在两次渲染之间改变 hook 数量
        useAiPage(mount ? page() : null);
        return useCurrentAiPage();
      },
      { wrapper, initialProps: { mount: true } },
    );

    expect(result.current?.key).toBe("k1");

    act(() => rerender({ mount: false }));
    expect(result.current).toBeNull();
  });

  it("最后一个页面卸载后登记应清空（浮标不该继续显示已离开的页）", () => {
    // 与「切页顺序」那条互为边界：那条测「旧页卸载不能连累新页」，
    // 这条测「该清的时候要清」。缺少后者，cleanup 写成空操作也能全绿 ——
    // 表现是离开某页后浮标仍显示那一页的数据，问 AI 会基于旧数据回答。
    const PageA = () => {
      useAiPage(page({ key: "a" }));
      return null;
    };
    const Probe = () => {
      const cur = useCurrentAiPage();
      return createElement("span", { "data-testid": "k" }, cur?.key ?? "-");
    };
    const Tree = ({ show }: { show: boolean }) =>
      createElement("div", null, show ? createElement(PageA) : null, createElement(Probe));

    const { container, rerender } = render(
      createElement(AiPageProvider, null, createElement(Tree, { show: true })),
    );
    const keyOf = () => container.querySelector('[data-testid="k"]')?.textContent;

    expect(keyOf()).toBe("a");

    rerender(createElement(AiPageProvider, null, createElement(Tree, { show: false })));
    expect(keyOf()).toBe("-");
  });

  it("切页顺序：旧页卸载晚于新页挂载时，不能把新页的登记抹掉", () => {
    // 这是 cleanup 最容易写错的地方，也是它真正的存在理由。
    // 若 cleanup 写成「无条件 set(null)」，在 A 卸载、B 已挂载的顺序里
    // 会把 B 刚登记的快照清掉，表现是换页后浮标说「这页没有数据」。
    //
    // 必须真的把组件挂到树上（renderHook 的 children 不会渲染），
    // 所以这里用 render + 一个读快照的探针。
    const PageA = () => {
      useAiPage(page({ key: "a" }));
      return null;
    };
    const PageB = () => {
      useAiPage(page({ key: "b" }));
      return null;
    };
    const Probe = () => {
      const cur = useCurrentAiPage();
      return createElement("span", { "data-testid": "k" }, cur?.key ?? "-");
    };
    const Tree = ({ showA }: { showA: boolean }) =>
      createElement(
        "div",
        null,
        showA ? createElement(PageA) : null,
        createElement(PageB),
        createElement(Probe),
      );

    const { container, rerender } = render(
      createElement(AiPageProvider, null, createElement(Tree, { showA: true })),
    );
    const keyOf = () =>
      container.querySelector('[data-testid="k"]')?.textContent;

    // B 后挂载，所以当前是 b
    expect(keyOf()).toBe("b");

    // A 卸载：若 cleanup 无条件清空，这里会变成 '-'
    rerender(
      createElement(AiPageProvider, null, createElement(Tree, { showA: false })),
    );
    expect(keyOf()).toBe("b");
  });

  it("suggestions 内容变化会被识别（它们被压成 sig 比较）", () => {
    // 这是最容易写错的一处：数组每次都是新引用，若直接放进依赖会让
    // effect 无限重跑；若完全不比较则建议列表永远停在第一次的值。
    const { result, rerender } = renderHook(
      ({ sugg }: { sugg: string[] }) => {
        useAiPage(page({ suggestions: sugg }));
        return useCurrentAiPage();
      },
      { wrapper, initialProps: { sugg: ["a"] } },
    );

    expect(result.current?.suggestions).toEqual(["a"]);

    act(() => rerender({ sugg: ["a", "b"] }));
    expect(result.current?.suggestions).toEqual(["a", "b"]);
  });

  it("同样的 suggestions 每次新数组，不应把快照清掉", () => {
    // 页面每次渲染都会传新数组字面量。若实现把引用相等当判据，
    // 会产生「登记→清空→登记」的抖动，浮标闪烁。
    const { result, rerender } = renderHook(
      ({ n }: { n: number }) => {
        useAiPage(page({ suggestions: ["a", "b"], context: `v${n}` }));
        return useCurrentAiPage();
      },
      { wrapper, initialProps: { n: 1 } },
    );

    act(() => rerender({ n: 2 }));

    expect(result.current?.suggestions).toEqual(["a", "b"]);
    expect(result.current?.context).toBe("v2");
  });

  it("没有 Provider 时不抛错（页面可单独渲染 / 单测里没有壳）", () => {
    expect(() =>
      renderHook(() => useAiPage(page())),
    ).not.toThrow();
  });
});
