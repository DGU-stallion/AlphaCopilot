# UI 设计调研（2026-10-21）

> 触发：用户对 ADR-0013 的终端风原型两版都不满意（「UI、排版、字体、线条、颜色都不喜欢」，
> 且「心中也没有对标」）。本文件是**先调研再动手**的产物，不是事后辩护。
> 结论落在 ADR-0014，本文只记证据。

## 一、TradingView 重设计的官方案例（Rondesignlab）

来源：<https://rondesignlab.com/cases/tradingview-platform-for-traders>
（TradingView 联合创始人 Liam Mercer 具名背书的案例研究，含具体数字）

三条可直接照搬的结论：

### 1. 字体分工不是审美，是防误读

> IBM Plex Mono, chosen for superior number differentiation... it prevents misreading,
> say, $1,234.56 as $12,34.56.
> Secondary Typeface, Inter Variable, handles all UI labels, buttons and narrative text.

- **数字用等宽**（Plex Mono / JetBrains Mono）：防止 `1,234.56` 读成 `12,34.56`
- **UI 文本用 Inter Variable**：变量字体，300–700 字重单文件，比静态字族省 180KB

我们原来的 `index.css` 只写了 `font-family: Inter, system-ui`，**数字没有等宽** ——
这是「表格里价格看着不齐」的根因，与配色无关。

### 2. 涨跌色要降饱和，不是纯红纯绿

> Traditional bright green (#00ff00) and red (#ff0000) create eye strain during long
> trading sessions. That is why we reduced color saturation by 18%...
> User testing showed **23% longer viewing time** with the changed palette.

- 纯 `#00FF00`/`#FF0000` 长时间看会疲劳
- 降饱和 18% → 观看时长 +23%

我第一版原型用了 `#F04438`/`#12B76A`（Tailwind 语义色），实际偏艳；应当再暗一档。

### 3. 深色主题的「层次」靠灰阶，不靠阴影

> Our redesigned panel involves a color scheme ranging from darker to more lighter grays,
> which all stay within the frame of a dark theme, but portray depth...

- 全站在同一个深色色相内，用**灰阶差**表示层级
- 不用阴影、不用发光、不用渐变

这条与 ADR-0013 的判断一致，但 ADR-0013 只说了「不用」，没说「用什么替代」。
答案是：**同一色相的 4–5 级明度**。

## 二、组件库选型

### 结论：用 Ant Design v6，不手写

| 库 | 判断 |
|---|---|
| **Ant Design 6.6.7** | ✅ 选它。阿里为金融/后台场景造的，60+ 组件，Table 是最强项（排序/筛选/虚拟滚动/服务端分页全内置，CRUD 表 80 行 vs shadcn 2000 行）。中文语境默认对齐 |
| shadcn/ui | ❌ 代码拷进仓库、要自己维护；我们是单人项目，维护成本不划算。适合「设计语言要独特」的产品 |
| Tremor | ❌ 专为 dashboard 造，但图表走 Recharts；我们图表已经定了 LWC + ECharts，引入 Recharts 是第三套图表栈 |
| MUI | ❌ Material 审美偏消费级，且包体 300KB+ |

关键理由：**用户明确说「使用 react、ant 这些好看的库，而不是纯原生手写」**。
更重要的是，我前两版手写原型的结果证明了单靠自己调 CSS 出不了一致的观感
——间距、字重、边框可见度这些没有系统约束就会每处不一样。

antd 的 token 系统（Seed → Map → Alias）正好解决这个问题：
改 `colorPrimary` / `borderRadius` / `fontSize` 几个 seed，全套组件跟着变，
不需要逐组件覆盖。

### antd 已知代价

- 包体约 500KB → 用 `manualChunks` 拆出去，首屏不阻塞
- 默认观感是「阿里后台」→ 必须改 token，否则一眼就是 antd demo
- v6 比 v5 新，生态文章少 → 以官方文档为准

## 三、我们的风格关键词 → 具体设计决策

用户给的关键词：**金融、科技、简约、实用**。

| 关键词 | 误读（前两版犯的） | 正确做法 |
|---|---|---|
| 金融 | 深色 + 红绿闪烁 = 金融感 | **数字可信、对齐精确、留白克制**。金融感来自信息组织，不来自颜色 |
| 科技 | 渐变、发光、玻璃 | **锐利的 1px 线、等宽数字、低饱和**。科技感来自精度 |
| 简约 | 东西少 | **每个像素都有信息**。简约 ≠ 空，而是没有装饰性元素 |
| 实用 | 功能全堆上去 | **常用路径 1 次点击**。层级靠版式，不靠折叠面板 |

## 四、色彩：定案

不用纯黑（`#000` 对比过强、显廉价），用**带蓝的深灰**，三层明度：

```
深色（默认）
  bg      #0B0E14   页面底
  panel   #12161F   面板/卡片
  raised  #1A1F2B   悬浮/选中/hover
  border  #232936   1px 分隔线
  border2 #2E3546   强分隔（表头下沿）

文字（同一色相，4 级）
  primary   #E6E9EF
  secondary #9BA3B4
  tertiary  #6B7385
  disabled  #4A5162

强调（唯一）
  accent    #3B82F6   只给交互：选中/链接/聚焦环

涨跌（降饱和 18%，对齐 TradingView 案例）
  up        #D9534F   A 股红涨（不是 #FF0000）
  down      #3FAE7A   绿跌（不是 #00FF00）
```

浅色主题同结构，明度反转，accent 加深保证对比。

## 五、字体：定案

| 用途 | 字体 | 理由 |
|---|---|---|
| UI 文本 | Inter Variable | TradingView 案例的选择，变量字重省体积 |
| **所有数字** | JetBrains Mono | 防误读；`font-variant-numeric: tabular-nums` 双保险 |
| 中文 | 系统栈（PingFang SC / Microsoft YaHei） | 不引中文字体包（动辄 10MB+） |

数字字体必须**在组件层强制**，不能靠开发者记得加 class。

## 六、间距与尺寸

8px 基准，但数据密集区用 4px：

```
间距  4 / 8 / 12 / 16 / 24 / 32
行高  表格 28px（紧凑）/ 32px（常规）
圆角  2（标签）/ 4（输入、按钮）/ 6（卡片）
字号  11（表头、辅助）/ 12（正文）/ 13（强调）/ 16（页面标题）/ 20（大数字）
```

## 七、待验证

- [ ] antd v6 token 是否真的能改到「不像 antd」——原型要证明这一点
- [ ] LWC 与 antd 深色主题色是否一致（两边各自读 token）
- [ ] 中文字体在 JetBrains Mono 旁边是否协调（中文走系统栈，字重需匹配）
