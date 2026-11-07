import { useEffect, useState } from "react";

/**
 * 主题：**默认深色**（ADR-0014 §3）。
 *
 * 为什么默认深色而不是跟随系统：这是个长时间盯盘的投研工具，
 * 报价、K 线、表格都是大面积高对比数字；浅色底在长时间使用下更刺眼。
 * TradingView 的案例研究也指出交易场景「massively prefer darker interfaces」。
 *
 * 机制：给 <html> 加 .light / .dark 两个类（两个都加，不靠"没有类"表示默认）。
 * 这样 theme/usePalette.ts 与 chart-theme.ts 都只需读 classList，
 * 不必猜"没类名时算什么"。
 *
 * 存储键保留 `vr-theme`（历史值），不清空用户的已有选择。
 */
const STORAGE_KEY = "vr-theme";

export function useDarkMode() {
  const [dark, setDark] = useState(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "light") return false;
    if (saved === "dark") return true;
    return true; // 默认深色
  });

  useEffect(() => {
    document.documentElement.classList.toggle("light", !dark);
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem(STORAGE_KEY, dark ? "dark" : "light");
  }, [dark]);

  return { dark, toggle: () => setDark((d) => !d) };
}
