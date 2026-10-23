/**
 * 图表主题：从 `theme/tokens.ts` 读，不再自己定义颜色。
 *
 * ADR-0014 §2：颜色只有 tokens.ts 一个真源。本文件原来自己算 HSL→hex、
 * 自己判断 zh/en 决定红绿方向，导致图表与 UI 会各走一套（同一屏里两种蓝）。
 * 现在改成纯映射：取 palette，输出图表库需要的字段形状。
 *
 * 注意涨跌方向**不由语言决定**，由用户的「涨跌口径」决定（ADR-0014 §3）：
 * A 股红涨绿跌是默认，国际口径可切。方向由 palette 的 up/down 承载，
 * 本文件不判断 locale。
 */
import { DARK, LIGHT, type Palette } from "@/theme/tokens";

export interface ChartTheme {
  gridColor: string;
  textColor: string;
  axisColor: string;
  upColor: string;
  downColor: string;
  maColors: string[];
  bollColor: string;
  volumeUp: string;
  volumeDown: string;
  infoColor: string;
  warningColor: string;
  accentColor: string;
  seriesColors: string[];
  tooltipBg: string;
  tooltipBorder: string;
  tooltipText: string;
}

/** 判断当前是否深色。DOM class 为准（与 useDarkMode 同一判定源）。 */
function isDarkNow(): boolean {
  return document.documentElement.classList.contains("dark");
}

/** 当前 palette。口径切换（红涨绿跌 ↔ 绿涨红跌）通过换 palette 的 up/down 实现。 */
export function currentPalette(): Palette {
  return isDarkNow() ? DARK : LIGHT;
}

function toChartTheme(p: Palette): ChartTheme {
  return {
    gridColor: p.border,
    textColor: p.textTertiary,
    axisColor: p.borderStrong,
    upColor: p.up,
    downColor: p.down,
    maColors: [p.warning, p.accent, p.info],
    bollColor: `${p.accent}80`,
    volumeUp: `${p.up}66`,
    volumeDown: `${p.down}66`,
    infoColor: p.info,
    warningColor: p.warning,
    accentColor: p.accent,
    // 分类系列色：语义色 + tokens 的补位色，多系列图按此顺序循环取色
    seriesColors: [p.warning, p.catViolet, p.info, p.up, p.down, p.catTeal],
    // tooltip 用 raised 而不是半透明黑：与面板同色，视觉上是「浮起的一层」
    tooltipBg: p.raised,
    tooltipBorder: p.border,
    tooltipText: p.text,
  };
}

let _cache: ChartTheme | null = null;
let _cacheKey = "";

/**
 * 取当前图表主题。
 *
 * 缓存键包含 class 与 palette 的涨跌色 —— 只含 class 的话，
 * 用户在浅色主题下切换涨跌口径时图表不会更新（class 没变）。
 */
export function getChartTheme(): ChartTheme {
  const p = currentPalette();
  const key = `${document.documentElement.className}|${p.up}|${p.down}`;
  if (_cache && _cacheKey === key) return _cache;
  _cache = toChartTheme(p);
  _cacheKey = key;
  return _cache;
}

/** 供测试用：清缓存。 */
export function _resetChartThemeCache(): void {
  _cache = null;
  _cacheKey = "";
}
