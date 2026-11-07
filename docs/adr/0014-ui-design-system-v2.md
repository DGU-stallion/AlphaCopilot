# ADR-0014 — UI 设计系统 v2：antd token + 自托管字体 + 单 chart 多 pane

**状态**：已决定（2026-10-21）
**取代**：ADR-0013 的 §1/§2/§3（视觉语言、颜色 token、图表分工实现方式）
**继承**：ADR-0013 的 §4（三区布局）与 §5（清理清单）；AGENTS 硬规则 7、8
**依据**：[`docs/research/ui-design-2026-10.md`](../research/ui-design-2026-10.md)

## 背景

ADR-0013 定下「交易终端风」，但只写了一句话级别的约束（平面、密集、等宽数字），
没有可执行的 token，也没有说用什么组件库实现。实际做了三版原型才收敛：

| 版本 | 做法 | 结果 |
|---|---|---|
| v1 | 平面深色表格塞进旧的玻璃侧栏 | ❌ 用户：「都太丑了」——旧外壳污染判断 |
| v2 | 手写 div 全屏 + 真 K 线 | ❌ 手写 CSS 出不一致的观感 |
| v3 | antd + token 单一真源 | ✅ 结构成立，但圆表占满纵向空间、图表留白 |
| v4 | 去掉自选表、Agent 栏可折叠、图表填满 | ✅ 用户：「感官不错」 |

**结论：ADR-0013 的方向对，缺的是实现手段。** 本 ADR 补的就是手段。

## 决定

### 1. 组件库：Ant Design v6（不再手写）

| 库 | 判断 |
|---|---|
| **antd 6.6.7** | ✅ 阿里为金融后台设计，60+ 组件，Table 最强项。Seed→Map→Alias token 系统 |
| shadcn/ui | ❌ 代码拷进仓库要自己维护；设计语言要独特才值得 |
| Tremor | ❌ 图表走 Recharts，我们已有 LWC + ECharts，不引第三套 |
| MUI | ❌ Material 偏消费级，包体 300KB+ |

**理由**：两版手写原型的失败证明「自己调 CSS 出不一一致的观感」——间距、字重、
边框可见度没有系统约束就会每处不一样。antd 的 token 系统让「改一个 seed，全套跟着变」。

**代价**：包体约 500KB → `manualChunks` 拆出去；默认观感是「阿里后台」→ 必须改 token。

### 2. Token 单一真源：`frontend/src/theme/tokens.ts`

AGENTS 硬规则 7 原文是「颜色只写在 `index.css` 与 `chart-theme.ts` 两处」。
引入 antd 后这句话**不再成立**——antd 不吃 CSS 变量做主题，它要 JS 对象。改为：

```
theme/tokens.ts          ← 唯一真源
  ├→ antd ConfigProvider theme
  ├→ Lightweight Charts applyOptions
  └→ ECharts chart-theme.ts（从它读，不再自己定义）
```

`index.css` 保留给极少数 antd 覆盖不到的地方（滚动条、选中态），**不再定义颜色**。

**新增禁令**：任何组件里出现 `#` 开头的颜色字面量，视为违规。颜色只能从
`usePalette()`（或 props 传入的 palette）取。

### 3. 颜色定案（替换 ADR-0013 §2）

不用纯黑（对比过强显廉价），用带蓝的深灰；层次靠**同色相灰阶**，不靠阴影。

```
深色（默认）
  bg      #0B0E14   页面底
  panel   #12161F   面板 / 侧栏 / 顶栏
  raised  #1A1F2B   悬浮 / 选中 / hover
  border  #232936   1px 分隔线
  borderStrong #2E3546  强分隔（表头下沿）

文字（同色相 4 级）
  text          #E6E9EF
  textSecondary #9BA3B4
  textTertiary  #6B7385
  textDisabled  #4A5162

强调（全站唯一，只给交互）
  accent      #3B82F6
  accentHover #60A5FA

涨跌（**降饱和**，见研究文档「+23% 观看时长」）
  up   #D9534F    A 股红涨（不是 #FF0000）
  down #3FAE7A    绿跌（不是 #00FF00）

警告 / 信息
  warning #D99A4E   info #5B8DEF
```

浅色主题同结构、明度反转（`LIGHT` 常量），accent 加深到 `#2563EB` 保对比。

**涨跌双口径**（A 股红涨绿跌 / 国际绿涨红跌）：用户可切，持久化到 localStorage。
实现上交换 `up`/`down` 两个值的来源，不在各处判断口径。

### 4. 字体：数字必须等宽（功能性要求，非审美）

| 用途 | 字体 | 理由 |
|---|---|---|
| UI 文本 | **Inter Variable**（自托管） | 变量字重单文件，比静态字族省约 180KB |
| **所有数字** | **JetBrains Mono**（自托管） | 防 `1,234.56` 读成 `12,34.56` |
| 中文 | 系统栈 | 不引中文字体包（10MB+） |

**自托管，不走 CDN**（`@fontsource-variable/inter`、`@fontsource/jetbrains-mono`）：
离线可用、无第三方请求。

**强制手段**：数字不靠开发者记得加 class，而是走统一组件：

```tsx
<Num v={1309.69} />              // 等宽 + tabular-nums + 涨跌色
<Num v={-1.67} pct />            // 自动带 %、自动上色
```

任何直接写数字的地方视为违规（`<Num>` 之外不得出现 `.toFixed(` 的渲染结果）。

### 5. 尺寸定案

```
间距 4 / 8 / 12 / 16 / 24 / 32（8 基准，数据密集区用 4）
字号 11 表头 / 12 正文 / 13 强调 / 16 页标 / 20 大数字 / 28 报价
行高 表格紧凑 28 / 常规 32
圆角 2 标签 / 4 输入按钮 / 6 卡片
控件高度 24 / 28(默认) / 32
```

### 6. 图表实现：单 chart 多 pane，不拼两个实例

**这是 v4 踩过的坑，必须写进 ADR。**

错误做法：K 线一个 chart、成交量另一个 chart，上下堆叠。

实测后果（有截图对比）：
- 左右边缘**对不齐**（两个实例各自计算价格轴宽度，差约 5px）
- 缩放/十字光标**不联动**（各管各的 `timeScale`）
- 多一份 canvas 开销

正确做法：**同一个 `createChart` 实例，用 pane 分区**：

```ts
c.addSeries(CandlestickSeries, opts, 0);   // pane 0
c.addSeries(HistogramSeries, opts, 1);      // pane 1
c.panes()[1].setHeight(h * 0.24);           // 成交量占 1/4
```

时间轴天然共享，缩放自动同步，LWC 署名只需一处。

**与 ADR-0013 §3「图表分工」的关系**：分工不变（K线/净值/回撤/买卖点 → LWC；
热力图/散点/归因 → ECharts），但 **LWC 内部的多图一律用 pane，不叠加实例**。
净值 + 回撤同理（pane 0 净值、pane 1 回撤）。

### 7. 图表生命周期三条纪律（都踩过）

```tsx
// ① 建实例的 effect **不能依赖 palette**
//    依赖了切主题会销毁重建，series 的 cleanup 随后 removeSeries
//    打到已销毁实例上 → 内部 ensureDefined 抛错 → 整页白屏
useEffect(() => { /* createChart(...) */ }, []);

// ② 主题变化只 applyOptions，不重建
useEffect(() => { chart.applyOptions({ /* colors */ }); }, [palette]);

// ③ 数据变化只 setData，不重建 series
//    重建会丢掉缩放位置与十字光标状态
useEffect(() => { series.setData(pts); }, [bars]);
```

另：`rightPriceScale.entireTextOnly: true` —— 边缘刻度宁可不显示，
也不要露出半截数字（canvas 会裁掉）。

### 8. 布局（继承 ADR-0013 §4，细化尺寸）

```
┌──────────────────────────────────────────────────────────┐
│ 顶栏 48  [标的▾] [视图] [搜索 ⌘K]        [as-of] [主题]   │
├────────┬─────────────────────────────────┬───────────────┤
│ 左导航 │  主画布                          │ Agent 栏      │
│ 176 /  │  ├ 标的头（大字报价 + OHLC）     │ 展开 360      │
│ 52 折叠│  ├ 视图切换条                    │ 折叠 44       │
│        │  └ 图表（flex:1 吃满）           │ 可折叠        │
├────────┴─────────────────────────────────┴───────────────┤
│ 底栏 28  数据源 · 口径 · as-of · run id                   │
└──────────────────────────────────────────────────────────┘
```

- **左导航可折叠**（176 → 52），点击 logo 切换
- **Agent 栏可折叠**（360 → 44 竖条），折叠时主画布自动变宽，带 160ms 过渡
- **主画布内部 `minHeight: 0`** —— 否则 flex 子项不会真正压缩，图表会溢出

## 权衡

| 备选 | 否决原因 |
|---|---|
| 继续手写组件 | 两版原型已证明出不一致观感 |
| shadcn/ui | 单人项目维护成本 > 收益 |
| 两个独立 chart 拼多图 | 对齐/联动/开销三项皆输（实测） |
| 纯 CSS 变量做主题（不引 antd） | antd 不吃 CSS 变量，二者只能选一 |
| CDN 字体 | 离线不可用，且有第三方请求 |

## 影响

- **AGENTS 硬规则 7 需修订**：颜色真源从 `index.css` + `chart-theme.ts`
  改为 `theme/tokens.ts` 单一文件
- ADR-0013 §1/§2/§3 被本 ADR 取代；§4/§5 继续有效
- M2 任务表需按本 ADR 重写（见 REFACTOR-PLAN）

## 待办

- [ ] `index.css` 里的旧 token 全部迁到 `tokens.ts`，删 `glass`/`glow`
- [ ] `chart-theme.ts` 改为从 `tokens.ts` 读，不再自己定义颜色
- [ ] 现有 10 个页面按新 token 重排
- [ ] 涨跌双口径的持久化与切换入口
