# ADR-0016 — 页面由 spec 组件拼装，agent 产出 spec，服务端裁决

- 状态：已决定 2026-10-22（第二轮迭代 D 阶段期间）
- 相关：ADR-0007（参数化 Page Spec）、ADR-0012（双轨产物）、ADR-0014（UI 设计系统 v2）
- 部分取代：ROUND2-BRIEF 的 B1（删 Build）、A1（不补 published 路由）

## 背景

用户提出：「将这个项目的展示都做成图表型、小组件型的，就像无代码平台一样。
然后这个项目就由 agent 来编写代码，然后将图表固定在页面上。」

这句话有两种可能的读法，必须区分，因为它们对应完全不同的架构：

- **读法 A（拖拽编辑器）**：用户自己在画布上拖 widget、拼页面，像 Retool / Notion。
- **读法 B（agent 产出 spec）**：agent 读自然语言需求，产出一个页面 spec，落库后
  该页面就固定下来；用户不拖，要改就再提需求。

**用户已明确选择 B。** 本 ADR 记录 B 的决定、边界与不做的部分。

## 决定

### 决定 1：页面 = spec（数据），不是手写 TSX

每个页面由 `page` 表的一行 spec 描述，前端用通用渲染器画：

```
page.spec = {
  slug, title, layout: "grid",
  params: [{name, type, label, default}],   // 自动生成参数控件
  blocks: [{kind, span, renderer, analysis_ref: {fn}}]
}
```

`kind ∈ {chart, table, markdown, metric}`，`span ∈ {1,2,3}`（三列栅格），
`renderer ∈ {lwc, echarts}`。**这个契约已经存在**（`backend/api/page_spec.py`，
ADR-0007 定的），不需要新建。

### 决定 2：三块要新建的东西

| 层 | 职责 | 位置 |
|---|---|---|
| `BlockRenderer` | 吃一个 block，按 `kind` + `renderer` 画出来 | `frontend/src/components/page/BlockRenderer.tsx` |
| `PageCanvas` | 按 `span` 摆进三列栅格；按 `spec.params` 生成控件并把值传给 render | `frontend/src/components/page/PageCanvas.tsx` |
| `/p/:slug` | 读 `/api/pages/{slug}` → `PageCanvas` | `frontend/src/pages/PageView.tsx` |

现状：`Backtest.tsx` 里已有一段「按 renderer 分派」的雏形（第 170 行附近），
但写死在一个页面里。本决定是**把它抽出来**，不是从头设计。

### 决定 3：agent 只产 spec，不产代码，不改 DOM

沿用 AGENTS.md 反模式「让 agent 生成前端代码或直接改 DOM（它只能产 View / artifact）」。

`POST /api/pages` 走 `validate_spec`：
- 形状不符 schema → 400
- `analysis_ref.fn` 不在 `alpha.registry` 白名单 → 400
- `chart.renderer` 与 `RENDERER_BY_FN` 映射不一致 → 400

**agent 无法凭空造一个取数函数**，它只能组合已登记的 17 个 fn。
这是这套机制唯一的安全边界，也是它比「agent 直接写 React」强的地方。

### 决定 4：不做拖拽编辑器

明确不做：拖动重排、自由 resize、画布内拖入组件。

理由：
1. 用户选的是读法 B，不是 Retool。
2. `span` 是**固定三列栅格**，不是自由坐标。真做拖拽要给 schema 加
   `x/y/w/h`，那是改契约，影响 `validate_spec` 与全部内置页。
3. 拖拽编辑器是独立的产品（撤销栈、碰撞检测、吸附、移动端降级），
   与「个人自用投研工具」的定位不匹配。

将来若要加，是「在既有 spec 上加位置字段」的增量工作，不需要推翻本决定。

### 决定 5：迁移范围 = 图表型页面

本轮只迁**图表型**页面（回测 / 相关性 / 因子）。理由：

- 这些页面本来就是 `renderPage` 的消费者，spec 已声明好 block，收益最大
- **CRUD 表格型**（Runs / 研报 / 股票池 / 日志 / 组合）本质是表格 + 表单，
  套进 widget 只会更难用
- **看板型**（复盘看板 549 行、宏观看板）有大量专用布局与跨块联动，
  组件化的收益中等、风险高

## 与已废弃结论的冲突（必须说清）

ROUND2-BRIEF 里有两条结论被本 ADR 部分推翻：

| 原结论 | 当时理由 | 现在 |
|---|---|---|
| **B1：删 Build** | 发布只写库，前端永远读不到 → 空转 | **保留删除的是 Build 那个具体页面**（它的编辑交互没用了），但「spec 落库 → 前端渲染」这条链路**要建起来**。Build 死于**没有渲染器**，不是死于「页面由数据驱动」这个想法 |
| **A1：不补 published 路由** | 用户说删 Build，所以不需要自定义页 | **要补**。补的是 `/p/:slug` 通用渲染路由，服务于 agent 产出的 spec，不是服务于 Build 的草稿编辑 |

**这不是反复，是当初诊断不完整。** 当时的诊断停在「发布看不见」，没有继续问
「为什么发布看不见」——答案是缺通用渲染器，而缺它的原因是所有页面都是手写 TSX。
修掉手写 TSX，Build 想解决的问题会以更适合的形态（agent 产 spec）回来。

## 后果

**好的**：
- 加一个新分析页 = 写一条 spec，**不写 React**（原本要 200+ 行 TSX）
- agent 能自己扩展产品能力，且受白名单约束，无法越权取数
- 图表分工（LWC vs ECharts）由服务端 `RENDERER_BY_FN` 裁决，前端不猜

**坏的 / 要认的代价**：
- 通用渲染器必然比手写页面**丑一点**。手写页面可以为某个图表调 20 行 CSS，
  `BlockRenderer` 只能给一套通用外观。这正是 D 阶段（UI 重设计）要先定标度的原因
- spec 多一层间接：改一个图的呈现要改渲染器，改不了「某一个图」
- 迁移期新旧并存：已迁页面走 spec，未迁页面仍是手写 TSX

## 不做什么

- ❌ 拖拽 / 自由布局编辑器（决定 4）
- ❌ 让 agent 写 React 组件或改前端代码
- ❌ 迁移 CRUD 表格型页面（决定 5）
- ❌ 给 spec 加自由坐标字段
