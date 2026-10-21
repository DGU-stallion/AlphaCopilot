/**
 * 设计 token 单一真源（ADR-0014）。
 *
 * 为什么要有这个文件：AGENTS 硬规则 7 说「颜色只写在 index.css 与 chart-theme.ts 两处」。
 * 引入 antd 后这句话要改 —— antd 不吃 CSS 变量做主题，它要 JS 对象。所以：
 *
 *   tokens.ts  ← 唯一真源（这个文件）
 *      ├→ antd 主题（ConfigProvider theme）
 *      ├→ CSS 变量（index.css 由它生成，见 gen-css-vars）
 *      └→ LWC / ECharts（chart-theme.ts 从它读）
 *
 * 这样「改一个颜色」只改一处，图表和 UI 不会漂移。
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
export const SPACE = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;

// 字号：11 表头 / 12 正文 / 13 强调 / 16 页标 / 20 大数字
export const SIZE = { xs: 11, sm: 12, md: 13, lg: 16, xl: 20, xxl: 28 } as const;

// 行高：表格紧凑 28，常规 32
export const ROW = { compact: 28, regular: 32 } as const;

// 圆角：标签 2 / 输入按钮 4 / 卡片 6
export const RADIUS = { sm: 2, md: 4, lg: 6 } as const;

/** 生成 antd 的 theme 配置。algorithm 由调用方给（dark/default/compact）。 */
export function antdTheme(p: Palette) {
  return {
    token: {
      colorPrimary: p.accent,
      colorInfo: p.info,
      // 注意用 danger/success 而**不是** up/down：
      // antd 的这两个槽位是「操作成功/失败」的界面反馈，
      // 国际口径下把 up/down 换过来后，保存成功的提示不该变成红色。
      colorSuccess: p.success,
      colorError: p.danger,
      colorWarning: p.warning,

      colorBgBase: p.bg,
      colorBgLayout: p.bg,
      colorBgContainer: p.panel,
      colorBgElevated: p.raised,

      colorText: p.text,
      colorTextSecondary: p.textSecondary,
      colorTextTertiary: p.textTertiary,
      colorTextQuaternary: p.textDisabled,
      colorBorder: p.border,
      colorBorderSecondary: p.border,

      borderRadius: RADIUS.md,
      borderRadiusLG: RADIUS.lg,
      borderRadiusSM: RADIUS.sm,

      fontFamily: FONT.ui,
      fontFamilyCode: FONT.mono,
      fontSize: SIZE.sm,
      fontSizeSM: SIZE.xs,
      fontSizeLG: SIZE.md,
      fontSizeHeading5: SIZE.lg,
      fontSizeHeading4: SIZE.lg,
      fontSizeHeading3: SIZE.xl,

      controlHeight: 28,
      controlHeightSM: 24,
      controlHeightLG: 32,
      lineWidth: 1,
      wireframe: false,
    },
    components: {
      // 表格是主战场：压行高、去掉斑马纹、分隔线只留横向且要淡
      Table: {
        headerBg: p.panel,
        headerColor: p.textTertiary,
        headerSplitColor: "transparent",
        rowHoverBg: p.raised,
        cellPaddingBlock: 6,
        cellPaddingInline: 12,
        borderColor: p.border,
        fontSize: SIZE.sm,
      },
      // Menu 深色下不要 antd 默认的选中块，只留一条左侧竖线 + 文字变色
      Menu: {
        itemBg: "transparent",
        itemSelectedBg: p.raised,
        itemSelectedColor: p.text,
        itemColor: p.textSecondary,
        itemHoverBg: p.raised,
        itemHoverColor: p.text,
        itemHeight: 32,
        iconSize: 14,
      },
      Card: {
        colorBgContainer: p.panel,
        paddingLG: SPACE.md,
        headerBg: "transparent",
        headerFontSize: SIZE.sm,
        headerHeight: 36,
      },
      Tabs: {
        itemColor: p.textSecondary,
        itemSelectedColor: p.text,
        itemHoverColor: p.text,
        inkBarColor: p.accent,
        horizontalItemPadding: "6px 0",
        horizontalItemGutter: 20,
        titleFontSize: SIZE.sm,
      },
      Segmented: {
        itemSelectedBg: p.raised,
        itemSelectedColor: p.text,
        itemColor: p.textSecondary,
        trackBg: p.bg,
      },
      Statistic: {
        contentFontSize: SIZE.xl,
        titleFontSize: SIZE.xs,
      },
      Descriptions: {
        labelBg: "transparent",
        titleColor: p.textTertiary,
        labelColor: p.textTertiary,
        contentColor: p.text,
      },
      Divider: { colorSplit: p.border },
      Layout: {
        bodyBg: p.bg,
        headerBg: p.panel,
        siderBg: p.panel,
      },
    },
  } satisfies import("antd").ThemeConfig;
}
