# ADR-0012 — 双轨产物规则：确定性结果 vs Agent 表达

**状态**：已决定
**日期**：2026-10-20
**取代**：ADR-0008 决策 1「AI 只解释」、决策 2「页面分层（固定页 vs page spec）」
**继承**：ADR-0006 决策 3（AI 只能建 draft 页）、决策 1 的图表契约（ECharts option）

## 背景

用户选择 B 路线（agent 写代码产图），同时保留「tab 页 + 确定性计算」的产品骨架。
这两个要求表面冲突：

- 老定位：AI **不生成计算结果**，所有数字由确定性 Python 算出
- 新要求：agent 可以写代码、跑回测、产图表、**直接 pin 进主页面**

冲突的根源是把「确定性」和「AI 生成」当成互斥。实际上它们是**同一份产物的两个来源**，
可以用**一条归属规则**共存。

## 决定

### 1. 每个 artifact 必须声明 `provenance.kind`

```ts
type Provenance =
  | { kind: "deterministic"; fn: string; params: object; dataAsOf: string }
  | { kind: "agent"; runId: string; codeHash: string; dataAsOf: string; model: string }
```

- **`deterministic`**：由白名单注册表（`alpha.registry`）里的纯函数产出。
  同样的 params 永远得到同样的结果。前端默认信任它。
  **这个标签只能由服务端铸造**（2026-10-21 修订，见「已决 1」）——
  agent 无权自称。
- **`agent`**：由 agent 写代码产出（bash / run_python）。必须带 `runId` +
  `codeHash`，可回看、可重跑。走 `run_python` 时源码落在
  `workspace/runs/<run_id>/code.py`；走 `bash` 时 `codeHash` 取该 message 期间
  全部 tool call 的 canonical JSON（Pi session 有完整记录）。

**没有任何 artifact 可以不带 provenance。** 这是唯一的硬约束。

### 2. 双轨职责

| | 确定性轨 | Agent 轨 |
|---|---|---|
| 用途 | 默认页面、KPI、核心图表 | 探索性分析、自定义图形、临时标注 |
| 触发 | 页面打开 / 改参数 | 用户提问 |
| 延迟 | 毫秒级 | 秒到分钟级 |
| 可复现 | params 决定 | codeHash 决定 |
| 前端标识 | 无（默认） | 角落小标 `AI` + hover 显示 runId |
| 失败后果 | 页面显示「暂不可用」 | 对话里显示错误，页面不受影响 |

**默认优先确定性**：如果一个图能由确定性函数产出，就不要让 agent 写代码产出。
理由不是安全，是**速度与稳定性**——用户打开复盘看板不应该等模型。

### 3. Agent 产出可以直接 pin 进主页面

用户明确要求：可以。规则：

1. Agent 产出 artifact → 落库（`artifact` 表，带 provenance）
2. 对话流里显示 → 用户点 **Pin**
3. Pin 生成一个 `View`，加入当前 `Page`
4. 页面渲染时按 `Page.views` 顺序渲染，agent 产的 View 显示 `AI` 角标

**可撤销**：每个 AI View 可一键移除；`Page` 保留版本历史（最近 20 版）。

### 4. Page 是保存的 View 集合，不是代码

```ts
type View = {
  id: string;
  title: string;
  blocks: Block[];          // chart | table | metric | markdown
  provenance: Provenance;
  bind?: { pageParam?: string; query?: string };  // 可绑定页面参数，改参重算
};

type Page = {
  slug: string;
  title: string;
  views: View[];
  layout: "grid" | "stack";
  kind: "system" | "user";   // system 不可删；user 可删
};
```

- **`system` 页**：6 个固定 tab（宏观看板 / 复盘看板 / 股票池 / 我的研报 / 回测 /
  相关性 / 模拟组合 / 交易日志），初始 views 由代码注册。
- **`user` 页**：agent 建的 draft 页（ADR-0006 决策 3 继续有效：**必须人工确认才发布**）。

**这样「页面可生长」回来了，但不是「AI 生成前端代码」**——是「AI 生成 View，
你决定要不要放进 Page」。

### 5. 数字只来自确定性函数（保留这条；**执法方式 2026-10-21 修订**）

即使 agent 能写代码，以下数字**必须**由确定性轨产出：

- 回测指标（收益/回撤/夏普/年化/换手）
- 相关矩阵
- 因子 IC / 分层收益
- 敏感性测算（盈亏平衡、营收冲击）
- 行情/财务的数值本身

Agent 可以对它们做**解释、比较、组合、可视化**，但不能自己算。
理由：这些数字一旦错，整个产品的可信度归零，而 LLM 算数一定会错。

**实现方式**（2026-10-21 修订，取代原「code review 检查 code.py」）：

执法点不在 agent 的代码里，而在**产物落库那一刻**。服务端是唯一有权盖
`deterministic` 章的角色：它自己调 `alpha.registry` 里的函数才盖章；agent 在
manifest 里声明的 provenance **一律不采信**，强制改写为 `kind = "agent"`。

于是规则从「不许自己算」（无法验证的语义判断）变成「**自己算的必须挂 AI 角标**」
（可测试的落库校验）。完整推理见文末「已决 1」。

`alpha.*` / `research.*` 仍在 import 路径上（`run_python` 预置），agent 应当优先
调用它们 —— 但这是**使用建议**，不是可执法的硬约束。

## 权衡

| 备选 | 否决原因 |
|---|---|
| 严格 ADR-0008（AI 绝不产图） | 用户明确要 AI native；而且 M2 时代已经跑通过（`test_e2e1_correlation.py`） |
| 完全放开（AI 随便写页面） | 幻觉会污染展示层；且无法复现，出问题查不了 |
| 只允许 agent 产出进对话流 | 用户明确要能 pin 进主页面 |

**代价**：

1. **两条路径都要维护**。缓解：确定性轨覆盖默认页面（90% 使用场景），
   agent 轨只在用户主动探索时产生。
2. **provenance 增加落库复杂度**。缓解：schema 校验，缺失直接拒收
   （复用现有 `ManifestError` 思路）。
3. **AI 角标可能让用户困惑**。缓解：hover 显示「AI 生成 · run abc123 · 可重跑」。

## 影响

- `artifact` 表新增 `provenance` JSON 列。
- `page` 表从「spec + blocks」改为「views 列表」，`page_spec.py` 的白名单机制
  保留用于 `deterministic` 轨的 fn 解析，但**不再是页面渲染的唯一路径**。
- 前端恢复 `ChartBlock` / `TableBlock` / `MetricBlock` / `MarkdownBlock`
  四个渲染器（`dbe7b6e` 删除的那套），并加 `AI` 角标与 Pin 交互。
- `AGENTS.md` 硬规则 6（固定业务页 / 不为单页写组件）需重写为
  「system 页用 View 组合；新增只读分析优先加确定性 View，不写新组件」。

---

## 修订（2026-10-21）：落地状态 + 三个决策面（2 已决 / 1 未决）

本 ADR 的三条硬约束里，§5 的执法方式已被修订（见「已决 1」），
但三条**在代码里目前都还没有实现**：

| 决定 | 代码现状（实测） | 排期 |
|---|---|---|
| §1 每个 artifact 必须带 `provenance` | `api/store.py` 的 `artifact` 表**无 provenance 列**；`api/artifacts.py` 的 `_validate_manifest` 只校验 `kind`/`path`/`payload`；全后端 `grep provenance` = 0 | **M1-7** |
| §3 Agent 产出可 Pin 进 Page | `page` 表有 `spec`/`status`，无 `views`；无 Pin 交互 | M3-3 / M3-4 |
| §4 Page = 保存的 View 集合 | `api/page_spec.py` 白名单机制在，但仍是"固定页 vs spec"二分 | M3-3 |
| §5 数字只来自确定性函数 | 执法靠 `workspace/runs/*/code.py` review；**但 agent 走 bash 时不产 code.py** | **已决 1：盖章权归服务端**（M1-7 落地） |

### 已决 1（2026-10-21）：**盖章权归服务端**，agent 无权自称 deterministic

**问题**：§5「数字只来自确定性函数」原定的执法手段是「code review 时检查
`workspace/runs/*/code.py`」。但 agent 现在能走 `bash`（`python3 -c ...` 或临时脚本），
**这条路不产生 `code.py`**，规则对主力路径是空的。而「这段代码算不算绕开了库函数」
是语义判断，写不成规则 —— 靠审计 bash 只能事后发现，误报多，最后一定被关掉。

**决定**：执法点从「审计 agent 的代码」移到「**卡产物落库那一刻**」。

1. `provenance.kind = "deterministic"` **只能由服务端铸造**：服务端自己调
   `alpha.registry` 注册表里的函数，才盖这个章。
2. **agent 提交的 manifest 里的 provenance 一律不采信**，服务端强制改写为
   `kind = "agent"`。agent 无法自称 deterministic。
3. 于是 agent 就算用 bash 手算了一个夏普塞进表格，它落库时带的是 **AI 角标**，
   用户一眼知道「这不是可信数字」。
4. `runId` / `codeHash` 的取法：`kind = "agent"` 时由服务端在 ingest 时生成
   `runId` 并绑定 Pi 的 session/entry id；`codeHash` 取「该 message 期间全部
   tool call 的 canonical JSON」的 hash（Pi session JSONL 有完整记录）——
   这样**走 bash 也能落地 provenance**，不再依赖 `code.py`。

**这条决定的好处**：规则变得**可测试**。一条测试就是「伪造 manifest 声称
deterministic → 被拒收 / 被改写成 agent」。不需要判断代码语义。

**配套修改**：AGENTS 硬规则 6 拆成两句 —— 行为层是**建议**（优先调库函数），
展示层是**硬约束**（可信数字只能服务端铸造）。原先"agent 不得自己实现"这种
无法执法的表述删除。

### 已决 2（2026-10-21）：`run_python` 通道保留，但重新定位为「记录式执行器」

**问题**：`mcpserver/sandbox.py`（130 行 Seatbelt）作为**安全边界已经等于零** ——
agent 用 bash 能绕开它的全部四条限制（写任意位置 / 读 `~/.ssh` / 联网 / 无限时）。

**但它有三个与安全无关的价值**：

1. **自动留档** —— 分配 `run_id`、建 `runs/<id>/`、代码原样存 `code.py`。这正是
   provenance 需要的 `runId` 来源（走 bash 就得从 session 日志反推）
2. **禁网络是有意的产品约束** —— 让「取数走我们的数据层」成为默认习惯，
   不绕过 as-of / 缓存 / 限流（与「不给 agent 装 vendor 的 SKILL.md」同一理由）
3. **可复现** —— 半年后能翻出当时的代码重跑

**决定**：**保留**，但重新定位并改叙述：

| 项 | 改前 | 改后 |
|---|---|---|
| 定位 | 「沙箱执行器」「安全边界」 | **「记录式执行器」**；Seatbelt 是纵深防御的一层，**不构成安全边界** |
| 命名 | `mcpserver/sandbox.py` | `mcpserver/runner.py`（保留 `run_python` 函数名不变，减少改动面） |
| docstring | 「边界（G3 结论）：限写 / 拒读 / 禁网」 | 明确写「这些限制仅约束**本通道**；agent 整体不受限，见 ADR-0010 §3」 |
| `test_read_secret_denied` | 名为「沙箱能拒读密钥」 | 标注「**仅证明本通道自身的限权**，不代表 agent 整体受限」 |

**删除测试为什么不选删**：删掉后 `run_id` / `code.py` / 产物收集这套逻辑会散到
`session_manager` 与 manifest 校验里去 —— 复杂度不消失，只是搬家。

### 未决 1：`Block` 缺渲染器判别符

本 ADR 继承「图表契约 = ECharts option」，但 ADR-0013 把 K 线/净值/回撤划给
Lightweight Charts。同一个 `kind: "chart"` 现在有两个可能的渲染器，
不区分会出现**两套库画同一种图**。M2-5 补 `renderer: "echarts" | "lwc"`，
并约定：`deterministic` 轨的 `backtest.equity` / `backtest.drawdown` 产 LWC 输入，
`correlation.overlay` 一类产 ECharts option。
