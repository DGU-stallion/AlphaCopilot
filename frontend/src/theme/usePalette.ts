import { useSyncExternalStore } from "react";
import { DARK, LIGHT, type Palette } from "@/theme/tokens";

/**
 * 当前主题的 palette（ADR-0014：颜色唯一真源 tokens.ts）。
 *
 * 主题机制：hooks/useDarkMode 给 <html> 切 .light / .dark 类。
 * 用 useSyncExternalStore + MutationObserver 订阅类名变化：
 * 任何组件（不止 Layout）都能拿到会随主题变化的 palette，
 * 调用点不用自己传（<Num> 内部就用它，不要每个调用点传 palette）。
 */

function subscribe(cb: () => void) {
  const mo = new MutationObserver(cb);
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  return () => mo.disconnect();
}

function currentPalette(): Palette {
  // useDarkMode：亮色加 .light，暗色加 .dark；初始 effect 未跑时默认亮色。
  return document.documentElement.classList.contains("dark") ? DARK : LIGHT;
}

export function usePalette(): Palette {
  return useSyncExternalStore(subscribe, currentPalette, () => LIGHT);
}
