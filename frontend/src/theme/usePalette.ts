import { useSyncExternalStore } from "react";
import { DARK, LIGHT, withCaliber, type Caliber, type Palette } from "@/theme/tokens";

/**
 * 当前主题 + 当前口径的 palette（ADR-0014：颜色唯一真源 tokens.ts）。
 *
 * 两个维度：
 *   - 主题：<html> 上的 .light / .dark 类（hooks/useDarkMode 维护）
 *   - 口径：<html> 上的 .caliber-intl 类（本文件的 setCaliber 维护）
 *
 * 用 useSyncExternalStore + MutationObserver 订阅类名变化，
 * 任一组变化都会让所有订阅组件重渲染。调用点不需要自己传 palette。
 */

export const CALIBER_KEY = "ac-caliber";

/** 订阅 <html> 的 class 变化（主题与口径都靠它，所以只需一个 observer）。 */
function subscribe(cb: () => void) {
  const mo = new MutationObserver(cb);
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  return () => mo.disconnect();
}

/** 从 DOM 读口径，不读 localStorage —— 保证「唯一判定源」与 CSS 一致。 */
export function currentCaliber(): Caliber {
  return document.documentElement.classList.contains("caliber-intl") ? "intl" : "cn";
}

/**
 * 缓存 palette 对象。
 *
 * ⚠️ 这不是性能优化，是**正确性要求**：useSyncExternalStore 用 Object.is 比较
 * getSnapshot 的返回值，返回新对象会被判定为「变了」→ 触发重渲染 → 再取快照
 * → 又是新对象 → 无限循环（React 会抛 "Maximum update depth exceeded"）。
 * 每次 withCaliber 都 `{...p}`，所以必须在这里按 (主题, 口径) 缓存。
 */
let _cache: { key: string; p: Palette } | null = null;

function currentPalette(): Palette {
  const dark = document.documentElement.classList.contains("dark");
  const caliber = currentCaliber();
  const key = `${dark ? "dark" : "light"}|${caliber}`;
  if (_cache && _cache.key === key) return _cache.p;
  _cache = { key, p: withCaliber(dark ? DARK : LIGHT, caliber) };
  return _cache.p;
}

export function usePalette(): Palette {
  return useSyncExternalStore(subscribe, currentPalette, () => LIGHT);
}

/** 测试用：清缓存（避免跨用例脏快照）。 */
export function _resetPaletteCache(): void {
  _cache = null;
}

/** 口径切换。写 localStorage + 切 <html> 的 class，两者必须同步。 */
export function setCaliber(c: Caliber): void {
  document.documentElement.classList.toggle("caliber-intl", c === "intl");
  localStorage.setItem(CALIBER_KEY, c);
}

/** 首次挂载时把 localStorage 里的口径应用到 DOM（main.tsx 或 App 调一次）。 */
export function initCaliber(): Caliber {
  const saved = localStorage.getItem(CALIBER_KEY);
  const c: Caliber = saved === "intl" ? "intl" : "cn";
  document.documentElement.classList.toggle("caliber-intl", c === "intl");
  return c;
}
