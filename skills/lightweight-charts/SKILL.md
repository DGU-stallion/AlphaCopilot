---
name: lightweight-charts
description: Use when writing or reviewing any lightweight-charts (TradingView) chart code — createChart, series creation, panes, time/price scales, data updates, React lifecycle cleanup. Covers the v5 API difference (addSeries instead of addCandlestickSeries), the three lifecycle disciplines that cause blank charts when violated, and how to verify every API name against the locally installed typings.
category: reference
source: TradingView/lightweight-charts 官方 skills 仓库（Apache-2.0）改编；已逐条核对 frontend/node_modules/lightweight-charts@5.2.1 dist/typings.d.ts 与 ADR-0014 §6/§7
---

# lightweight-charts v5（项目内唯一金融图表库）

## 适用场景

- 用 bash 写图表代码（view/artifact 的 LWC 渲染块）
- 排查「图表为何白屏 / 边缘不齐 / 缩放丢了」
- K 线 + 成交量、净值 + 回撤这类同图多序列

K 线/净值/回撤/买卖点才用 LWC；热力图/散点/归因用 ECharts（ADR-0014 §6 分工不变）。

## 唯一权威：本地 typings，不靠记忆

写代码前先 grep 装好的版本（v5.x，当前 5.2.1）：

```sh
node -p "require('./frontend/node_modules/lightweight-charts/package.json').version"
rg -n "addSeries|CandlestickSeries|setHeight|entireTextOnly" \
  frontend/node_modules/lightweight-charts/dist/typings.d.ts
```

typings 里找不到的 option / 方法就不要写。API 名在 chart / series / scale /
pane 四层之间有同名陷阱（`upColor` 是 series 的，`textColor` 是 layout 的），
层级要确认清楚。

## v5 与 v4 的差别（最常见的翻车点）

v4 每种序列一个方法，v5 统一成 `addSeries` + 显式导入的序列定义
（typings.d.ts:1640）：

```ts
addSeries<T extends SeriesType>(definition: SeriesDefinition<T>, options?, paneIndex?): ISeriesApi<T>
```

```ts
// ✅ v5（verified：typings.d.ts 5027-5034 导出块）
import { createChart, CandlestickSeries, HistogramSeries, LineSeries, AreaSeries } from "lightweight-charts";
const candle = chart.addSeries(CandlestickSeries, { ... }, 0);
const vol    = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" } }, 1);

// ❌ v4（v5 typings 里不存在，仅出现在旧注释里）
chart.addCandlestickSeries();
```

已核对：`addCandlestickSeries` 在 5.2.1 的 typings.d.ts 里只有 2 处、且都在
jsdoc 注释里，**没有任何真实方法声明**。照 v4 写，运行时直接抛
`seriesType is not a function` 之类的错，或图表静默空白。

其余 v4→v5 易踩点（均已对 typings 核对）：

| 旧写法 | v5 写法 | 依据 |
|---|---|---|
| `series.setMarkers(...)` | `createSeriesMarkers(series, markers)` 返回独立插件对象 | typings:294 导出；`setMarkers` 只属于 marker 插件 `ISeriesMarkersPluginApi`（2639），不在 `ISeriesApi` 上 |
| `watermark` chart option | 不再用（本项目也不需要） | — |
| `time: Date.now()` 毫秒 | `UTCTimestamp` 是**秒**，`(Date.now() / 1000) as UTCTimestamp` | typings:4995-5001 明文 |
| 判断不到 v5 就乱抄 | 先 `node -p` 查版本 | — |

## 单 chart 多 pane，不拼两个实例（ADR-0014 §6）

```ts
const c = createChart(container, { autoSize: true });
c.addSeries(CandlestickSeries, opts, 0);   // pane 0：K 线
c.addSeries(HistogramSeries,  opts, 1);    // pane 1：成交量
c.panes()[1].setHeight(h * 0.24);          // 成交量占 1/4
```

- `chart.panes(): IPaneApi[]`（typings:1779）；`IPaneApi.setHeight(height)`（2025）、
  `getHeight()`、`paneIndex()`、`getSeries()` 均已核对。
- 不设 pane 高度时两个 pane 等高，K 线会被压扁；一般用 ResizeObserver 跟随容器
  重算 pane 高度。
- **为什么不能 `createChart` 两次上下拼**：两个实例各自计算价格轴宽度，左右
  边缘差约 5px；缩放/十字光标各管各的 `timeScale` 不联动；多一份 canvas 开销。
  pane API 时间轴天然共享，缩放自动同步。实测对比见 ADR-0014 §6。

## 生命周期三条纪律（ADR-0014 §7，每条都踩过）

```tsx
// ① 建实例的 effect 不依赖 palette / 主题
useEffect(() => { /* createChart + remove cleanup */ }, []);

// ② 主题变化只 applyOptions，不销毁重建
useEffect(() => { chart.applyOptions({ ... }); seriesRef.current?.applyOptions({ ... }); }, [palette]);

// ③ 数据变化只 setData（或增量 update），不重建 series
useEffect(() => { seriesRef.current?.setData(points); }, [bars]);
```

违反后的具体症状：

1. ① 依赖了主题 → 切换主题时销毁重建 chart；cleanup 里对 series 的
   `remove`/`removeSeries` 打到**已销毁实例**上 → 内部 `ensureDefined` 抛错
   （已核对：`ensureDefined` 是 development build 的内部函数
   `lightweight-charts.development.mjs`，非公开 API）→ **整页白屏**。
2. ② 改成重建 → 同上白屏；正确做法只剩换色（applyOptions）。
3. ③ 重建 series → **丢缩放位置与十字光标状态**；且每次重建都要重新算 pane
   高度。仅全量换数据时才 `setData`，逐 tick 增量用 `update()`（typings:2464）。

setup 顺序：cleanup 里先 `paneRO.current?.disconnect()`、清空 refs，最后
`chart.remove()`（IChartApi.remove，typings:1605）。`remove()` 之后不要再对
任何 series 调方法——实例已销毁，轻则 no-op 重则 ensureDefined 抛错。

## 数据约束（会直接抛错）

- **必须严格按 `time` 递增、无重复**。development build 内部断言原文：
  `data must be asc ordered by time, index=..., time=..., prev time=...`。
  违反即抛 `AssertionFailed`，视图空白。
- 同一序列内 `time` 格式不要混用：要么全 `UTCTimestamp`（秒），要么全
  `'YYYY-MM-DD'` 字符串（BusinessDay）。
- 空洞（gap）用只带 `time` 的 whitespace 点，不要写 `value: null`。

## 图表 options（已逐条核对）

```ts
createChart(container, {
  autoSize: true,                 // LayoutOptions，typings:948；需容器可压缩
  layout: { background: { color: "transparent" }, textColor: "..." },
  grid: { vertLines: { color }, horzLines: { color } },
  rightPriceScale: {
    entireTextOnly: true,         // PriceScaleOptions，typings:3772：边缘刻度宁可不显示，也不露半截数字
    scaleMargins: { top: 0.06, bottom: 0.06 },
  },
  timeScale: { borderColor, timeVisible: false },
  crosshair: { mode: 1 },
});
```

- `autoSize: true` 依赖 ResizeObserver；容器在 flex 布局里时给容器
  `minHeight: 0`（flex 子项默认不真正压缩，图表会撑破布局，ADR-0014 §8）。
- K 线序列 options（CandlestickStyleOptions，863-914 各项均核对）：
  `upColor` `downColor` `borderVisible` `borderUpColor` `borderDownColor`
  `wickUpColor` `wickDownColor`。成交量用 `priceFormat: { type: "volume" }`
  （typings:3567，取值 `"price" | "volume" | "percent"`）。
- 序列换色：`series.applyOptions({ ... })`（ISeriesApi.applyOptions，2397；
  chart.applyOptions 1596）。`applyOptions` 里传 `undefined` = 「不指定」，
  不是「重置」。

## 写完自查清单

1. `[ ]` 没有 `addCandlestickSeries` / `addLineSeries` / `series.setMarkers`
2. `[ ]` 序列定义从包里显式 import
3. `[ ]` 里 chart 实例唯一，多序列用 paneIndex
4. `[ ]` 建实例 effect 依赖 `[]`，主题只 applyOptions
5. `[ ]` cleanup：disconnect RO → 清 refs → `chart.remove()`
6. `[ ]` `time` 严格递增无重复、全秒级 timestamp、同序列格式统一
7. `[ ]` `autoSize: true` + 容器 `minHeight: 0`
8. `[ ]` `rightPriceScale.entireTextOnly: true`
