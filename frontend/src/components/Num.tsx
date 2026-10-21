import { type CSSProperties } from "react";
import { FONT, SIZE } from "@/theme/tokens";
import { usePalette } from "@/theme/usePalette";
import { cn } from "@/lib/utils";

/**
 * 数字渲染唯一路径（ADR-0014 §4）：等宽 + tabular-nums + 涨跌色。
 *
 * 颜色不写字面量，从 theme/tokens.ts 的 palette 取（硬规则 7）；
 * palette 变化由 usePalette 订阅，调用点不需要传主题。
 *
 * 格式：千分位分组（1,234.56）—— TradingView 案例防误读的本意；
 * 小数位由 digits 固定（默认 2），与 .toFixed 的舍入行为一致。
 * null / undefined / NaN / ±Infinity 一律渲染 — （不是 0，也不是 NaN）。
 */

type SizeKey = keyof typeof SIZE;

export interface NumProps {
  v?: number | null;
  /** 小数位；默认 2，rate 模式默认 0 */
  digits?: number;
  /** 自动带 % 与正数 + 号，并按 A 股口径上涨跌色（正红 / 负绿 / 平灰） */
  pct?: boolean;
  /**
   * 0~1 比率：内部 ×100 再显示（0.625 → 62.5%）。
   * 小数位默认 0，要小数显式给 digits={1}。
   */
  rate?: boolean;
  /** 正数加 + 号（不带 pct 时手动开，如现金流净额） */
  signed?: boolean;
  /** 按正负上涨跌色；pct / rate 自带涨跌色，这个给「不加 % 但想上色」的地方 */
  colorBySign?: boolean;
  /** 数值后缀单位（如「亿」）；v 为 null 时整体是 —，不带单位 */
  unit?: string;
  /** 数字前缀文本；内部 + 号在 prefix 之前 */
  prefix?: string;
  /** 额外后缀文本（位于 % / unit 之后） */
  suffix?: string;
  /** 字号，读 tokens.ts 的 SIZE 体系（xs/sm/md/lg/xl/xxl） */
  size?: SizeKey;
  /** 不设内联颜色，跟随父元素的语义色（如容器已用 text-primary / text-danger） */
  inheritColor?: boolean;
  className?: string;
  style?: CSSProperties;
}

export function Num({
  v, digits, pct = false, rate = false, signed, colorBySign,
  unit, prefix, suffix, size, inheritColor = false, className, style,
}: NumProps) {
  const palette = usePalette();
  const d = digits ?? (rate ? 0 : 2);

  const styleAll: CSSProperties = {
    fontFamily: FONT.mono,
    fontVariantNumeric: "tabular-nums",
    ...(size ? { fontSize: SIZE[size] } : {}),
    ...style,
  };

  if (v == null || Number.isNaN(v) || !Number.isFinite(v)) {
    if (!inheritColor) styleAll.color = palette.textTertiary;
    return <span className={cn(className)} style={styleAll}>—</span>;
  }

  // rate：0~1 比率 → ×100 显示
  const shown = rate ? v * 100 : v;
  // 用舍入后的值判符号：+0.004% 显示成 0.00，就不再带涨跌色
  const rounded = Number(shown.toFixed(d));
  const plus = (pct || signed) && rounded > 0 ? "+" : "";
  const useSignColor = colorBySign || pct || rate;
  if (!inheritColor) {
    styleAll.color = useSignColor
      ? (rounded > 0 ? palette.up : rounded < 0 ? palette.down : palette.textSecondary)
      : palette.text;
  }

  const body = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  }).format(Math.abs(rounded));

  return (
    <span className={cn(className)} style={styleAll}>
      {plus}
      {prefix}
      {body}
      {pct || rate ? "%" : ""}
      {unit}
      {suffix}
    </span>
  );
}
