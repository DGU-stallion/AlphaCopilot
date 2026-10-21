/**
 * 涨跌口径的切换与持久化（M2-9）。
 *
 * 这里测的是**跨进程/跨刷新的一致性**，因为口径有三个消费者：
 *   1. React 组件（<Num> 通过 usePalette）
 *   2. CSS（text-danger / text-success 通过 <html>.caliber-intl）
 *   3. 图表（chart-theme 通过 currentPalette）
 *
 * 三者必须同时变。只变其中一个的症状是「数字变绿了、K 线还是红的」。
 */
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { DARK, LIGHT } from "@/theme/tokens";
import {
  CALIBER_KEY, initCaliber, setCaliber, usePalette, currentCaliber,
} from "@/theme/usePalette";

function setDark(dark: boolean) {
  document.documentElement.className = dark ? "dark" : "light";
}

describe("口径持久化与三处同步", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.className = "dark";
  });

  it("setCaliber('intl') 同时写 localStorage 与 <html> class", () => {
    act(() => setCaliber("intl"));
    expect(localStorage.getItem(CALIBER_KEY)).toBe("intl");
    expect(document.documentElement.classList.contains("caliber-intl")).toBe(true);
  });

  it("setCaliber('cn') 清掉 class（不是留着 true）", () => {
    act(() => setCaliber("intl"));
    act(() => setCaliber("cn"));
    expect(localStorage.getItem(CALIBER_KEY)).toBe("cn");
    expect(document.documentElement.classList.contains("caliber-intl")).toBe(false);
  });

  it("initCaliber 读回上次的选择", () => {
    localStorage.setItem(CALIBER_KEY, "intl");
    document.documentElement.className = "dark";
    const c = initCaliber();
    expect(c).toBe("intl");
    expect(document.documentElement.classList.contains("caliber-intl")).toBe(true);
  });

  it("initCaliber 在无记录时是 cn（默认 A 股口径）", () => {
    document.documentElement.className = "dark";
    expect(initCaliber()).toBe("cn");
    expect(document.documentElement.classList.contains("caliber-intl")).toBe(false);
  });

  it("usePalette 随口径反向：intl 下 up 取 DARK.down", () => {
    setDark(true);
    act(() => setCaliber("cn"));
    const cn = renderHook(() => usePalette());
    expect(cn.result.current.up).toBe(DARK.up);

    act(() => setCaliber("intl"));
    // MutationObserver 是异步的，等它回调
    return new Promise<void>((resolve) => {
      setTimeout(() => {
        expect(cn.result.current.up).toBe(DARK.down);
        expect(cn.result.current.down).toBe(DARK.up);
        resolve();
      }, 0);
    });
  });

  it("口径与主题互不干扰：intl + 浅色 仍是 LIGHT 的色值", () => {
    setDark(false);
    act(() => setCaliber("intl"));
    const p = renderHook(() => usePalette()).result.current;
    expect(p.up).toBe(LIGHT.down);
    expect(p.bg).toBe(LIGHT.bg);
  });

  it("两次取快照必须是同一个对象引用（否则 useSyncExternalStore 无限重渲染）", () => {
    // 这条抓的是实测踩到的 bug：withCaliber 每次 {...p} 造新对象，
    // useSyncExternalStore 用 Object.is 比较 → 判定「变了」→ 重渲染 →
    // 又取快照 → 又是新对象 → React 抛 "Maximum update depth exceeded"。
    // 当时只在「切换主题」路径上暴露（切到浅色才崩），所以必须单独钉住。
    setDark(true);
    const { result, rerender } = renderHook(() => usePalette());
    const first = result.current;
    rerender();
    expect(result.current).toBe(first);
  });

  it("currentCaliber 直接读 DOM，不读 localStorage", () => {
    // 这样 CSS 与 JS 的判定源唯一。若一个读 DOM 一个读 localStorage，
    // 会出现「CSS 已换色、JS 还按旧口径上色」的错位。
    localStorage.setItem(CALIBER_KEY, "intl");
    document.documentElement.className = "dark";   // DOM 上没有 caliber-intl
    expect(currentCaliber()).toBe("cn");
  });
});
