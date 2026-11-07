/**
 * 默认主题必须是深色（ADR-0014 §3）。
 *
 * 这条看着琐碎，但它是个**产品决策的守门**：
 * 投研工具是长时间盯盘的场景，报价、K 线、表格都是大面积高对比数字。
 * 默认浅色会让新用户第一眼就被刺到，而「默认值」几乎决定了用户会不会去改。
 *
 * 之前代码默认浅色、ADR 写默认深色 —— 文档与实现不一致本身就是 bug。
 * 所以这里钉住它，改回浅色必须是有意识的（改 ADR + 改测试）。
 */
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useDarkMode } from "@/hooks/useDarkMode";

describe("默认主题", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.className = "";
  });

  it("没有存过选择时，默认深色", () => {
    const { result } = renderHook(() => useDarkMode());
    expect(result.current.dark).toBe(true);
  });

  it("默认深色时，<html> 上有 .dark 且没有 .light", () => {
    renderHook(() => useDarkMode());
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.documentElement.classList.contains("light")).toBe(false);
  });

  it("用户显式选过浅色，就必须尊重（不能被默认值覆盖）", () => {
    localStorage.setItem("vr-theme", "light");
    const { result } = renderHook(() => useDarkMode());
    expect(result.current.dark).toBe(false);
  });

  it("切换后再挂载，记得上次的选择", () => {
    const first = renderHook(() => useDarkMode());
    act(() => first.result.current.toggle());
    expect(first.result.current.dark).toBe(false);

    // 模拟重新打开应用
    const second = renderHook(() => useDarkMode());
    expect(second.result.current.dark).toBe(false);
  });

  it("两个主题类都显式设置，不靠「没有类名」表示默认", () => {
    // 这条是为了让 usePalette / chart-theme 只需读 classList，
    // 不必猜「没类名时算什么」。猜的话两边很容易猜得不一样。
    const { result } = renderHook(() => useDarkMode());

    expect(document.documentElement.classList.contains("dark")).toBe(true);

    act(() => result.current.toggle());
    expect(document.documentElement.classList.contains("light")).toBe(true);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });
});
