/**
 * K 线数据整形（M2-6）：后端 /api/kline → Lightweight Charts 的输入。
 *
 * 单独抽成纯函数的原因：图表组件是 imperative + canvas（难测），
 * 而这里正是踩过坑的地方 —— 排序、去重、空格丢弃。每条规则都有对应测试。
 */
import type { Palette } from "@/theme/tokens";

/** 后端 /api/kline 返回的单根 K 线（字段名与 research.astock 一致）。 */
export interface RawBar {
  datetime: string;
  open: number;
  close: number;
  high: number;
  low: number;
  vol: number;
}

export interface Candle {
  time: string;
  open: number;
  close: number;
  high: number;
  low: number;
}

export interface VolumeBar {
  time: string;
  value: number;
  color?: string;
}

const finite = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);

/**
 * 保留**最后一条**同一天记录。
 *
 * 为什么最后一条而不是第一条：后端的重复通常来自「先返回了盘中快照、后返回收盘定稿」，
 * 后到的更接近定稿。原样喂给 LWC 会触发 `data must be asc ordered` 断言 → 整页白屏。
 */
function dedupeByLast(bars: RawBar[]): RawBar[] {
  const map = new Map<string, RawBar>();
  for (const b of bars) map.set(b.datetime, b);
  return [...map.values()];
}

/** 排序 + 去重 + 丢弃坏行。返回严格 time 递增的数组。 */
function normalized(bars: RawBar[]): RawBar[] {
  return dedupeByLast(
    bars.filter((b) => (
      typeof b?.datetime === "string" && b.datetime.length > 0
      && finite(b.open) && finite(b.close) && finite(b.high) && finite(b.low)
    )),
  ).sort((a, b) => (a.datetime < b.datetime ? -1 : a.datetime > b.datetime ? 1 : 0));
}

export function toCandleData(bars: RawBar[]): Candle[] {
  return normalized(bars).map((b) => ({
    time: b.datetime, open: b.open, close: b.close, high: b.high, low: b.low,
  }));
}

/**
 * 成交量柱。颜色跟**当根 K 线自身**的方向（收 >= 开 用涨色），
 * 不是跟"今天涨跌"走 —— 否则一根阴线（高开低走但仍高于昨收）的量柱会是红的。
 */
export function toVolumeData(bars: RawBar[], p: Palette): VolumeBar[] {
  return normalized(bars).map((b) => ({
    time: b.datetime,
    value: finite(b.vol) ? b.vol : 0,
    color: `${b.close >= b.open ? p.up : p.down}66`,
  }));
}

/**
 * 成交量 pane 的高度。
 *
 * - 24%：视觉上「量能是辅助」，但也足够读出放量/缩量
 * - 48px 下限：容器很矮或还没测量（0）时，保证 pane 不被压成 0 高
 *   （0 高的 pane 在 LWC 里会让坐标轴刻度重叠）
 */
export function paneHeight(total: number): number {
  if (!Number.isFinite(total) || total <= 0) return 48;
  return Math.max(48, Math.round(total * 0.24));
}
