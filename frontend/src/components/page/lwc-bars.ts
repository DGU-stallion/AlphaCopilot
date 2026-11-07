/**
 * LWC 载荷 → PriceChart 的 bar 形状（ADR-0016）。
 *
 * 为什么单独一个文件：`Backtest.tsx` 里原本有一份私有实现（lwcToBars），
 * 抽成通用渲染器后两个调用方都要用。放在组件文件里会造成
 * 「BlockRenderer 引用自己内部的工具函数」的循环依赖风险。
 */
import type { LwcPayload } from "@/components/charts/equity-data";

/** `{time, value}` → `{datetime, open, close, high, low, vol}`（line 模式只用 close）。 */
export function lwcToBars(payload: LwcPayload): {
  datetime: string;
  open: number;
  close: number;
  high: number;
  low: number;
  vol: number;
}[] {
  const pts = payload?.series?.[0]?.points ?? [];
  return pts
    .filter((p) => p && typeof p.value === "number" && Number.isFinite(p.value))
    .map((p) => ({
      datetime: p.time,
      open: p.value,
      close: p.value,
      high: p.value,
      low: p.value,
      vol: 0,
    }));
}
