# AlphaCopilot 重构计划（PLAN）

> 状态：待评审
> 前置决策：ADR-0006（应用自持前后端，dsh 降级为 SDK 内嵌）
> 形态与契约补充：ADR-0007（页面驱动主入口 + Agent Provider 解耦 + 参数化 Page Spec）
> 取代：ADR-0004 / ADR-0005 时期的插件化 PLAN
> 任务拆分见 `docs/TASKS.md`

---

## 一、北极星：我要的最终效果

> 本节是防跑偏的锚。任何设计争议先回到这里对照；与本节冲突的方案一律不采纳。

**一句话**：AlphaCopilot 是一个**对话驱动的量化投研工作台**。我用自然语言描述研究
意图，AI 写 Python 代码在我的数据上算出结果、画成可交互图表；值得留下的结果固化成
可随时新增的展示页；同时能基于研报／年报／公告／资讯产出带出处的投研报告。全部产出
最终服务于一件事：**理解不同市场／行业／标的之间的联系，并构建交易策略**。

### 四项能力承诺（每项都必须可验收）

| # | 承诺 | 验收含义 |
|---|------|---------|
| A | **对话即研究** | 自然语言 → AI 生成并执行 Python → 交互式 ECharts + 表格 + 文字结论，全程在对话流内 |
| B | **页面可生长** | 任一研究产出可发布为展示页；**新增页面不改前端代码、不重新部署、不重启服务** |
| C | **文档可追溯** | 研报／年报／公告／资讯 → 投研报告，每个结论可点回原文出处 |
| D | **策略可沉淀** | 一次性分析代码 → 提炼为 `alpha.*` 库函数 → 回测 → 策略记录 |

### 明确不做（反例同样是锚）

- 不做实盘下单 / live / 券商通道 / 定时自动交易
- 不做多用户、权限体系、SaaS 化（单人本机系统）
- 不做荐股、不预测涨跌、不给买卖时机（合规底线，固化进 system prompt）
- 不自研 agent loop、模型适配、上下文压缩（这些用 dsh）

### 典型工作日（形态而非功能清单）

> 形态更新见 ADR-0007：**页面驱动、对话辅助**。左侧 tab 选展示页，右下角浮标唤出
> 右侧 chat panel。对话不再是唯一主入口，而是「按需唤出的分析副驾」。

```
早上：左侧 tab 点开「每日复盘」页 → 昨夜美股 / 今日 A 股开盘前信息一屏看完
上午：左侧 tab 点开「相关性分析」页 → 选 5 只白酒标的 + 沪深300、窗口 60 日、区间近一年
      → 归一化叠加走势 + 相关矩阵 + 滚动相关三张图即时算出；改参数即时重算
下午：右下角浮标唤出 chat panel「用 20/60 金叉在这 5 只上回测三年，看净值和回撤」
      → 提交 job → 完成推送 → 净值/回撤双图 + 指标卡 → 存为策略草稿
晚上：chat panel「根据我扔进 docs 的三份年报，写一份对比报告」
      → 带出处的 markdown 报告 → 存进「我的报告」
```

---

## 二、整体架构

```
┌─ 展示层（React SPA · 本仓库自持）───────────────────────────────┐
│  Chat 时间线（主入口） │ 动态页面渲染器 │ Artifact / 策略 / 报告浏览器 │
│  block 渲染器 ×4：chart(ECharts) / table / markdown / metric      │
└──────────▲── SSE（消息·job 事件）──── REST（page spec·artifact）──┘
           │
┌─ 业务层（FastAPI · 本仓库自持）─────────────────────────────────┐
│  会话编排：dsh notification 流 → 前端消息流                        │
│  Job 队列：回测等长任务异步执行，事件回推                            │
│  领域存储：message / artifact / page / strategy / doc                │
│  分析库 alpha.*：data · chart · factor · backtest · report          │
└────┬──────────────────────────────────────┬────────────────────┘
     │ stdio JSON-RPC（3 个方法）            │ import（同一 venv）
┌────▼── AI 能力层（dsh runtime exe）──┐     │
│  agent loop / compaction / skills    │     │
│  subagent（研究委员会）               │     │
│  fs 工具（workspace-write 隔离）      │     │
│  mcp-client ─────────────────────────┼─────┤
└──────────────────────────────────────┘     │
                              ┌──────────────▼───────────────┐
                              │ 我们的 MCP server（Python）    │
                              │ run_python · publish_artifact │
                              │ create_page · search_docs     │
                              │ submit_backtest · get_quote   │
                              └──────────────┬───────────────┘
┌─ 数据层 ──────────────────────────────────▼────────────────────┐
│  backend/research/*（A股·全球·资讯·持仓，纯函数，原样保留）          │
│  文档库（PDF → 解析 → FTS5 索引；MinERU 预留）                     │
│  本地缓存 / DB（行情·因子·回测结果·artifact 文件）                   │
└────────────────────────────────────────────────────────────────┘
```

### 依赖方向（单向，违反即架构劣化）

- 展示层只认业务层的 REST / SSE，不认 dsh，不认数据层
- 业务层是唯一持有产品数据库的角色
- AI 层只能通过 **MCP 工具** 与 **workspace 文件系统** 触碰业务层，无反向调用
- 数据层是纯函数库，不知道上面三层存在（禁加框架依赖）

### 三条不可协商的边界

1. **dsh 的 session JSONL 是 agent 内部记忆，不是产品数据。** 前端永不读取。
   理由：dsh 协议明文 "no compatibility promise"。
2. **agent 不直接写数据库。** 它写 workspace 文件 + 调副作用 MCP 工具，
   由业务层校验后落库。否则一次幻觉即污染策略库。
3. **重活不在 agent 的 turn 里跑。** agent 只「写代码 → 提交 job → 读结果」。
   附带收益：turn 变短，抵消 SDK 协议无中途取消的缺陷。

---

## 三、三个核心契约

契约先于实现。这三个 JSON 形状定了，四层就能并行开发。

### 1. Artifact 契约（AI 的产出物）

```
workspace/runs/<run_id>/
  manifest.json     # 见下
  chart.json        # kind=chart：完整 ECharts option（可交互）
  data.csv          # kind=table：表格数据
  report.md         # kind=markdown：带出处引用的报告
  figure.png        # kind=image：matplotlib 兜底（异形图才用）
  code.py           # 生成该产出的代码，原样留存（可重跑、可提炼）
```

```jsonc
// manifest.json
{
  "run_id": "r-20260829-1a2b",
  "artifacts": [{
    "id": "a-...", "kind": "chart|table|markdown|metric|image",
    "title": "白酒板块与沪深300滚动相关性（60日）",
    "path": "chart.json",
    "inputs": { "symbols": ["600519.SH"], "window": 60 },  // 可重跑的参数
    "created_at": "..."
  }],
  "code_ref": "code.py",
  "session_id": "s-...", "message_id": "m-..."
}
```

- 图表**默认产 ECharts option JSON**，由 `alpha.chart.*` helper 生成，保证
  legend 切换 / hover 十字对齐 / dataZoom 可用；PNG 仅用于 helper 表达不了的图形。
- 大小上限与 JSON 可序列化校验在业务层入库时执行，不信任 agent 输出。

### 2. Page Spec 契约（承诺 B 的实现基础）

```jsonc
{
  "id": "p-...", "slug": "baijiu-correlation", "title": "白酒相关性",
  "status": "draft|published",          // AI 只能建 draft，发布需人工确认
  "layout": "grid|stack",
  "blocks": [
    { "kind": "chart",  "artifact_id": "a-...", "span": 2 },
    { "kind": "metric", "analysis_ref": { "code_ref": "...", "inputs": {...} } },
    { "kind": "markdown", "text": "## 结论\n..." }
  ],
  "refresh": { "mode": "manual|on_open|cron", "cron": "0 9 * * 1-5" }
}
```

**新增页面 = 插一条数据库记录。** 前端只实现一个通用渲染器读 spec，
零前端改动、零部署。「每日复盘」从写死页面降级为一条内置 page spec + 一个定时 job。

### 3. Job 契约（长任务）

```
submit_backtest(params) → { job_id }        # agent 的 turn 立即结束
job 事件流：queued → running(progress) → succeeded(run_id) | failed(error)
前端经 SSE 订阅；完成后 artifact 自动挂到会话消息上
```

---

## 四、安全边界（本机执行的知情取舍）

| 层 | 机制 | 覆盖 |
|---|------|-----|
| agent 文件工具 | `dsh-fs-sandbox` + `sandbox-policy` = `workspace-write` | 写入限 workspace |
| 代码执行 | 我们的 `run_python`：macOS `sandbox-exec`（Seatbelt profile） | 读写白名单目录 |
| 副作用 | agent 不能直接写库；`create_page` 只能产 draft | 展示层不被污染 |
| 不给 | **不挂 bash**（闭包无 `bash-sandbox`，`bash-local` 不隔离） | — |

**残余风险（已知情接受）**：dsh 的 `SandboxMode` 仅管文件写入，不管读取与网络；
真正的隔离需容器／microVM。缓解为 Seatbelt profile 显式 deny 读非白名单路径，
且密钥与 workspace 物理分离。**这不等于容器级隔离。**

---

## 五、里程碑与门禁

### M0 — Spike 门禁（任一失败 → 方案评审，不得带病进 M1）

| Spike | 验证问题 | 通过标准 |
|---|---|---|
| G1 (T21) | SDK + 自写 cordis.yml 能否挂我们的 MCP server | agent 调通 `get_quote` 返回茅台报价 |
| G2 (T22) | notification → SSE 端到端 | 浏览器逐字出字；杀进程可停；**同 session_id 重启后历史能否续上（实测结论必须写进文档）** |
| G3 (T23) | `run_python` 沙箱 | 能 import `alpha`、能写 runs 目录、**读 `~/.ssh` 被拒** |
| G4 (T24) | skills + 合规 prompt 在 SDK 组合内是否对模型可见 | model-visible 自查见 5 skills + 合规 section |

G1 失败 → 整个 SDK 路线作废，回插件路线。
G3 失败 → 降级为容器执行（推翻决策 2，需你确认）。

### M1 — 骨架贯通（承诺 A 的地基）
FastAPI 应用 + DB schema（message/artifact/page/job/doc）+ React shell + SSE 打通，
跑通「说一句话，AI 回一句话，浏览器逐字显示」。

### M2 — 对话即研究（承诺 A 达成）
`run_python` + artifact 契约 + chart block 渲染器。
E2E-1：「分析近一年白酒板块 5 只标的与沪深300的相关性」→ 对话流内出现可交互热力图。

### M3 — 分析层与长任务（承诺 D 地基）
`alpha.data / chart / factor / backtest` 最小可用 + job 队列。
E2E-2：「用 20/60 金叉在茅台回测近三年，画净值和回撤」→ job 完成后双图 + 指标卡。

### M4 — 页面可生长（承诺 B 达成）
page spec + 通用页面渲染器 + draft/发布确认流 + 每日复盘作为内置 spec。
E2E-3：把 E2E-1 的产出「发布为页面」，刷新浏览器后页面仍在，且不曾改动前端代码。

### M5 — 文档与报告（承诺 C 达成）
手动投喂 + FTS5 + `search_docs` + 报告 artifact（`DocParser` 接口预留 MinERU）。
E2E-4：「根据我放进 docs 的三份年报写对比报告」→ markdown artifact，结论可点回原文。

### M6 — v0.2.0
README 四节 / 一键启动脚本 / 四个 E2E 录屏归档。

---

## 六、迁移策略

**从 `archive/pre-dsh` 只取 4 类资产**（不整体复用 15 页前端）：

1. `frontend/src/lib/echarts.ts` + `chart-theme.ts`（ECharts 主题单点控制）
2. `frontend/src/hooks/useSSE.ts`
3. 对话时间线骨架：`ConversationTimeline` / `MessageBubble` 及其测试
4. `lib/formatters.ts` / `indicators.ts` 及其测试

design token 层（`index.css` 的 HSL 变量结构）保留结构、值随时可换；
`GlassCard` 等旧视觉语言不搬。**后期换风格只需改 token + `chart-theme.ts`，
或改 ~6 个组件（AppShell / PageRenderer / 3 个 block / ChatTimeline）。**

**从现 main 取**：`backend/research/*` 原样；`packages/dsh-alphacopilot-research`
迁入 `backend/mcp/`（同 venv，`run_python` 才能注入 `alpha.*`）；
`dsh-alphacopilot-desk/skills/*.md` 5 篇迁入 `skills/`；
chart renderer 的 ECharts 配置逻辑回收进 `alpha.chart`。

**归档**：现 main 打 tag `archive-dsh-plugins-v0.1`，另 4 个 TS 包不进新工作线。
不做 orphan 分支手术。

---

## 七、目标目录结构

```
AlphaCopilot/
├── backend/
│   ├── research/        # 数据层：纯函数，禁加框架依赖（原样保留）
│   ├── alpha/           # 业务层库：data · chart · factor · backtest · report
│   ├── api/             # FastAPI：会话编排 · SSE · artifact · page · job
│   ├── agent/           # dsh 适配层：cordis.yml + HarnessSession 包装（唯一耦合点）
│   └── mcp/             # 我们的 MCP server
├── frontend/            # React SPA（Vite + Tailwind + ECharts）
├── workspace/           # agent 可写工作区（sandbox 根），内含 runs/<run_id>/
├── skills/              # 投研方法论 skills ×5
└── docs/
```

---

## 八、编码规范

**Python**：ruff + pyright basic + pytest；`research/` 与 `alpha/` 是纯库
（无 FastAPI 依赖）；MCP 工具层零业务逻辑（校验 → 调 `alpha.*` → JSON 化 → 截断）；
docstring 即 LLM schema——**`alpha.*` 的 docstring 质量直接决定 AI 会不会用它**。

**TS**：strict、ESM、Biome、Vitest；页面渲染器数据驱动，禁止为单个页面写组件；
颜色/主题只写在 `index.css` token 与 `chart-theme.ts` 两处。

**Git**：trunk-based；`feat/T<nn>-<slug>` 短命分支；一任务一 PR，squash merge；
Conventional Commits，PR 标题带任务号；任务号从 T21 续编。
