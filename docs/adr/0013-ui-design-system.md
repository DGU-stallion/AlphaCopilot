# ADR-0013 — UI 设计系统 v1：交易终端风 + 双主题 + Lightweight Charts

**状态**：已决定
**日期**：2026-10-20
**取代**：S1 时期的玻璃拟态设计（glass / glow / 渐变 / 大圆角）
**继承**：AGENTS 硬规则 7（颜色只写在 `index.css` 与 `chart-theme.ts` 两处）

## 背景

用户反馈：「前端 UI 风格我要换，现在的不太好看，我喜欢简单一点的，类似于 TradingView」，
并选择**双主题**（深色 + 浅色）。

现状问题（具体到 token）：

- `glass`（背景模糊）+ `shadow-glow`（橙色发光）+ 渐变背景 → **视觉噪音 > 信息密度**
- `rounded-2xl`（16px）用于数据卡片 → 交易类界面应当锐利
- 主色是暖橙，且用作品牌装饰而非交互色 → 到处都是强调 = 没有强调
- 数字没有 `tabular-nums` → 表格里价格不右对齐时跳动

## 决定

### 1. 视觉语言：平面、密集、等宽数字

| 项 | 值 |
|---|---|
| 背景 / 面板 / 悬浮 | `--bg` / `--panel` / `--surface` |
| 边框 | `1px solid var(--border)`，**不用阴影** |
| 圆角 | 卡片 4px / 按钮与输入 2px / 标签 2px |
| 字号 | 11 / 12 / 13，正文 12；标题 14–16 |
| 行高 | 表格 28–32px |
| 数字 | `font-variant-numeric: tabular-nums`，全站强制 |
| 强调色 | **单一** `--accent`，只用于交互（选中、链接、聚焦），不用于装饰 |

### 2. 双主题 token

```css
/* 深色（默认） */
--bg: #0E1117;  --panel: #161A25;  --surface: #1C2230;
--border: #252A37;
--text: #D6DAE3;  --text-muted: #8A90A0;  --text-faint: #5A6072;
--accent: #4C8DFF;

/* 浅色 */
--bg: #FFFFFF;  --panel: #F7F8FA;  --surface: #FFFFFF;
--border: #E3E6EB;
--text: #1A1D23;  --text-muted: #6B7280;  --text-faint: #9CA3AF;
--accent: #2563EB;
```

**涨跌双口径**（用户可切换，持久化到 localStorage）：

```css
/* 口径 A：A 股（红涨绿跌）—— 默认 */
--up: #F04438;  --down: #12B76A;
/* 口径 B：国际（绿涨红跌） */
--up: #12B76A;  --down: #F04438;
```

**禁止项**：`backdrop-blur`、`box-shadow`（除 focus ring）、渐变背景、
`rounded-2xl` 及以上、发光效果、emoji 作为图标。

### 3. 图表分工

| 图形 | 库 | 理由 |
|---|---|---|
| K 线 / 成交量 / 净值 / 回撤 / 买卖点 / 信号标记 | **Lightweight Charts 5.x** | TradingView 官方、35KB、Apache 2.0、多 pane、markers、price lines |
| 相关性热力图 / 因子分层收益 / 散点 / 归因柱 / 饼图 | **ECharts 6** | 复杂图形表达力强、已有封装 |

**Lightweight Charts 的两个必做项**：

1. **署名**：Apache 2.0 + NOTICE 要求，用 `attributionLogo: true` 一行满足。
2. **颜色**：通过 `chart-theme.ts` 统一注入，与 `--up/--down` 同源，
   **不硬编码**（TradingView 默认绿涨红跌，与 A 股相反）。

**装官方 Agent Skills**（服务 AI native 路线）：

```bash
npx skills add tradingview/lightweight-charts
```

理由：agent 写图表代码时会拿到正确的 v5 API 知识，而不是训练数据里的 v4 片段。

### 4. 布局：命令栏 + 主画布 + Agent 面板

```
┌────────────────────────────────────────────────────────────┐
│ 顶栏  [标的] [区间] [口径▾]   ⌘K 命令栏        ● as-of 时间 │
├──────┬─────────────────────────────────────┬───────────────┤
│ 左导航│  主画布（Page = View 网格，可拖拽） │  Agent 面板   │
│      │  ┌────────────┬────────────┐        │  （可折叠）   │
│ 市场 │  │ K线+信号    │ KPI 卡     │        │               │
│ 研究 │  ├────────────┼────────────┤        │  对话流       │
│ 量化 │  │ 净值/回撤   │ 归因       │        │  + Pin 按钮   │
│ 系统 │  └────────────┴────────────┘        │               │
├──────┴─────────────────────────────────────┴───────────────┤
│ 底栏  数据源 · as-of · 口径说明 · run id（AI 产出时显示）    │
└────────────────────────────────────────────────────────────┘
```

**Agent 面板从「右下角浮标」改为「右侧常驻可折叠栏」**：因为 AI native 之后对话
不再是偶发功能，而是主要交互之一；浮标模式让对话与页面内容割裂。

### 5. 必须清理的视觉/功能残留

| 项 | 位置 | 动作 |
|---|---|---|
| 玻璃拟态（`glass` / `shadow-glow` / 渐变） | `index.css`、多个组件 | 删 |
| `AskAiButton`（点击弹「即将上线」） | 6 个页面 | **删组件** |
| `DeepDive` / `RunAllButton`（同上） | 复盘看板 | **删组件** |
| `Placeholder`（未被引用） | `pages/Placeholder.tsx` | 删 |
| 「vibe-astock / Vibe-Research / vibe-trading」注释与文案 | 76 处 | 全部删除或改写为中性表述 |
| `SaveNoteButton` + `lib/notes.ts`（localStorage） | 未接入 | 删（后续用正式 Note 对象替代） |

## 权衡

| 备选 | 否决原因 |
|---|---|
| Advanced Charts（670KB，需申请签协议） | 110+ 画图工具对投研工作是负担；协议要求自建 datafeed 且不能做竞品图表库；审核周期 |
| TradingView Widgets（iframe） | 用 TradingView 的数据，不能叠加自己的回测；且不能改样式 |
| 只保留 ECharts | K 线的交互（十字光标、缩放、pane 联动）要自己实现，不如直接用 |
| 只做深色 | 用户明确要双主题 |

## 影响

- `frontend/src/index.css` 全量重写 token；`lib/chart-theme.ts` 重写。
- 新增依赖：`lightweight-charts`（35KB，gzip 后约 12KB）。
- `EChart.tsx` 保留但收窄职责（只服务热力图/散点/柱状类）。
- 8 个页面组件需要重排布局（工作量约 5–7 天，在 M2）。
