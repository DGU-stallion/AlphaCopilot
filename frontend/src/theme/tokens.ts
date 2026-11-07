/**
 * 设计 token 单一真源（ADR-0014）。
 *
 * 为什么要有这个文件：AGENTS 硬规则 7 —— 颜色只有一个真源，组件里出现
 * `#` 开头字面量即违规。消费者全部从这里读：
 *
 *   tokens.ts  ← 唯一真源（这个文件）
 *      ├→ CSS 变量（index.css 由它生成，见 gen-css-vars）
 *      └→ LWC / ECharts（chart-theme.ts 从它读）
 *
 * 这样「改一个颜色」只改一处，图表和 UI 不会漂移。
 * （曾有第四个消费者：antd 的 ConfigProvider theme。antd 已不再使用，
 *   `antdTheme()` 于 2026-10-23 删除。）
 *
 * 数值来自 docs/research/ui-design-2026-10.md，那里有出处。
 */

/** 一套调色板的结构。深浅两套共用，所以不能用 typeof DARK（那会把颜色收窄成字面量）。 */
export interface Palette {
  bg: string; panel: string; raised: string; border: string; borderStrong: string;
  text: string; textSecondary: string; textTertiary: string; textDisabled: string;
  accent: string; accentHover: string;
  /** 图表多系列分类补位色：紫 / 青（> 5 系列时与语义色区分用，见 chart-theme.ts） */
  catViolet: string; catTeal: string;
  /**
   * 涨跌色 —— 表达市场事实，**随口径切换反向**（withCaliber）。
   * 只用于价格、涨跌幅、涨跌家数这类「市场方向」。
   */
  up: string; down: string;
  /**
   * UI 语义色 —— 表达「操作出错 / 操作成功」，**不随口径变化**。
   * 用于表单校验、toast、「删除成功」这类界面反馈。
   * 与 up/down 分开的原因见 withCaliber 的注释。
   */
  danger: string; success: string;
  warning: string; info: string;
}

/**
 * 涨跌口径（ADR-0014 §3）。
 * - `cn`   A 股习惯：涨=红、跌=绿（默认）
 * - `intl` 国际习惯：涨=绿、跌=红
 */
export type Caliber = "cn" | "intl";

// ---------------------------------------------------------------- 深色（默认）
export const DARK: Palette = {
  // 底色：带蓝的深灰，不用纯黑（纯黑对比过强显廉价）
  bg: "#0B0E14",
  panel: "#12161F",
  raised: "#1A1F2B",
  border: "#232936",
  borderStrong: "#2E3546",

  // 文字：同色相 4 级
  text: "#E6E9EF",
  textSecondary: "#9BA3B4",
  textTertiary: "#6B7385",
  textDisabled: "#4A5162",

  // 强调：全站唯一，只给交互
  accent: "#3B82F6",
  accentHover: "#60A5FA",

  // 分类补位（原 EChart.tsx 里的裸字面量，迁入本文件作唯一真源）
  catViolet: "#8B5CF6",
  catTeal: "#14B8A6",

  // 涨跌：降饱和 18%（TradingView 案例：观看时长 +23%）
  up: "#D9534F",
  down: "#3FAE7A",

  // UI 语义色（固定，不随口径变）
  danger: "#D9534F",
  success: "#3FAE7A",

  // 语义
  warning: "#D99A4E",
  info: "#5B8DEF",
} as const;

// ---------------------------------------------------------------- 浅色
export const LIGHT: Palette = {
  bg: "#FBFCFD",
  panel: "#FFFFFF",
  raised: "#F1F3F7",
  border: "#E2E6ED",
  borderStrong: "#CFD5E0",

  text: "#14181F",
  textSecondary: "#5A6272",
  textTertiary: "#8A92A3",
  textDisabled: "#B6BDCA",

  accent: "#2563EB",
  accentHover: "#1D4ED8",

  // 分类补位：亮色下降饱和度/加深一档保对比
  catViolet: "#7C3AED",
  catTeal: "#0D9488",

  up: "#C7423E",
  down: "#2E8F63",

  danger: "#C7423E",
  success: "#2E8F63",

  warning: "#B8792E",
  info: "#3B72D9",
};

// ---------------------------------------------------------------- 涨跌口径

/**
 * 按口径置换涨跌色。**纯函数，不改原 palette**。
 *
 * 为什么是「换 up/down」而不是「多一套 palette」：调用方（Num / chart-theme /
 * 图表系列）只需要读 `palette.up` 就是「涨价该用的颜色」，不必到处判断口径。
 * 口径只在一个地方生效，以后加第三种习惯（比如「涨=蓝」）也只改这里。
 *
 * 注意 danger/success **不参与置换** —— 那是 UI 语义，翻转发红色提示会误导用户。
 */
export function withCaliber(p: Palette, caliber: Caliber): Palette {
  if (caliber === "intl") return { ...p, up: p.down, down: p.up };
  return p;
}

// ---------------------------------------------------------------- 排版
// 数字必须等宽：防 1,234.56 读成 12,34.56（TradingView 案例的核心论点）
export const FONT = {
  ui: '"Inter Variable", Inter, system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif',
  mono: '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace',
} as const;

// 间距 8 基准；数据密集区用 4
//
// ROUND2-D1 定案：基准间距从 8 提到 12（D-A 基座放松一档）——
// 面板之间 12px、面板内 12px。`md` 就是它；其它值按比例留着备用。
export const SPACE = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;

/**
 * 字号与行高标度（ROUND2-D1 定案 = D-A 彭博终端放松一档）。
 *
 * 为什么不是原来零散的 10/11/12/13px：没有体系就无法回答「这一级该用哪个」，
 * 结果同一个页面里同时出现 10/11/12/13 四种字号，看着就是不统一。
 *
 * 为什么是 12 而不是 D-A 原型的 11：11px 中文接近可读下限，实测「医疗器械」
 * 这类笔画密的四字词开始粘连。数字仍为 12px 等宽（读盘读数不吃亏）。
 *
 * 基调（用户原话）：
 *   - 信息密集、图表为主体，而不是一堆大号数字
 *   - 不要求一屏塞满，允许上下滚动
 */
export const TYPE = {
  /** 表格/密集区的辅助标签（列头、时间戳） */
  label: 11,
  /** 正文与表格内容 —— 全站默认 */
  body: 12,
  /** 需要一眼抓住的数字与短标题 */
  emphasis: 13,
  /** 页标题 */
  pageTitle: 16,
  /** 关键指标大数字 */
  metric: 20,
} as const;

/** 行高。1.35 是正文；紧凑表格和长文本分开放，不要一个值打天下。 */
export const LINE = {
  tight: 1.2,
  /** 正文默认 */
  body: 1.35,
  /** 长文本（研报正文、归因说明） */
  loose: 1.6,
} as const;

// 字号：与 TYPE 同名映射，保留旧导出名以免大范围改调用方。
// 新代码优先用 TYPE.*（语义清晰）；SIZE.* 留给按 key 取尺寸的地方。
export const SIZE = {
  xs: TYPE.label,
  sm: TYPE.body,
  md: TYPE.emphasis,
  lg: TYPE.pageTitle,
  xl: TYPE.metric,
  xxl: 28,
} as const;

// 行高：表格紧凑 28，常规 32
export const ROW = { compact: 28, regular: 32 } as const;

// 圆角：标签 2 / 输入按钮 4 / 卡片 6
export const RADIUS = { sm: 2, md: 4, lg: 6 } as const;

