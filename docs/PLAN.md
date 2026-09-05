# AlphaCopilot 开发计划（PLAN）

> 状态：定位已调整（ADR-0008）
> 前置决策：ADR-0008（确定性计算为主 + 固定业务页面 + AI 只解释），调整 ADR-0006/0007
> 时期的产品北极星；四层架构（展示 / 业务 / AI / 数据）不变。
> 历史：ADR-0002/0004/0005 时期的对话驱动 / 插件化 PLAN 已作废。

---

## 一、定位：确定性计算为主，AI 只解释

> 本节是防跑偏的锚。任何设计争议先回到这里对照；与本节冲突的方案一律不采纳。

**一句话**：AlphaCopilot 是**个人本地 A 股低频量化投研工作台**。主体是确定性数据与
后端计算产出的固定业务页面；全局页面感知 Agent 作为「分析副驾」，只解释数据、回答
问题、提供观点，不生成计算结果、不下单、不盯盘、不做多智能体辩论。

第一版以 `AlphaTrading/` 下 vibe-astock、Vibe-Research 现成能力为供体缝合，能复用就
不重写；平台先搭起来，后续在使用中迭代。

### 四条定位边界（每条都是锚）

| # | 边界 | 含义 |
|---|------|------|
| A | **确定性为主** | 复盘 / 盘面 / 涨停统计 / 相关性 / 回测 / 组合结果由确定性 Python 算出，不经 AI 生成 |
| B | **AI 只解释** | 全局 Agent 解释当前页面数据、提观点、总结研报；写操作走草案→用户确认，不直接写库 |
| C | **固定业务页面** | 业务页专用 React 实现；参数化只读分析页用 page spec；不追求「AI 任意生成页面」 |
| D | **缝合优先** | 复用 > 适配 > 参考 > 新写；vibe-astock/Vibe-Research 为供体，TradingAgents 仅参考 |

### 明确不做

- 不做实盘下单 / 盯盘 / 个股行情终端（同花顺 / 富途已足够好）
- 不做多智能体辩论 / 分析师团队决策（那是 TradingAgents 定位）
- 不做多用户 / 权限 / SaaS（单人本机）
- 不荐股、不预测涨跌、不给买卖时机（合规底线，固化进 system prompt）
- 第一版不做数据层统一、视觉重做、大而全架构设计

### 典型工作日（形态）

```
早上：复盘看板 → 昨夜海外 / 今日 A 股情绪指标一屏看完（确定性计算）
上午：相关性分析页 → 选 5 只标的 + 沪深300、区间近一年 → 归一化叠加 + 相关矩阵即时算出
下午：回测页 → 对候选策略跑确定性回测 → 净值 / 回撤 / 指标；结果存草稿
      模拟组合页 → 建雪球式组合，记录调仓，跟踪净值 vs 沪深300
晚上：右下角浮标唤出 Agent「解释一下这个组合的相关性风险」→ 只读解释，不改数据
      我的研报 → 上传年报，Agent 总结带出处
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

---

## 九、下一步开发计划（第一版缝合）

> 原则：**复用 > 适配 > 参考 > 新写**。供体在 `AlphaTrading/`。每个阶段迁完即验证，
> 验证通过再进下一阶段；旧代码在替代能力验证通过后才删。

### 来源映射总表（10 页 + Agent）

| 目标页面 | 来源 | 方式 | 供体模块 |
|---|---|---|---|
| 复盘看板 | vibe-astock | 适配 | `duanxian/emotion_metrics.py`(money_effect/promotion_rates/consec_premium/ladder_gap/cycle_position/build_metrics)、`breadth.py`、`market_facts.py` |
| 盘面数据 | vibe-astock | 适配 | `duanxian/market_facts.py`、`fetchers.py` |
| 涨停样本统计 | vibe-astock | 适配 | `duanxian/stats_context.py`、`backtest.py`(样本统计口径) |
| 交易日志 | vibe-astock | 适配 | `duanxian/journal.py`（+ 新增 `journal` 表） |
| 股票池 | vibe-astock | 适配 | `duanxian/positions.py`（自选/watchlist 部分，+ 新增 `stock_pool` 表） |
| 我的研报 | Vibe-Research + 现有 | 复用 | 现有 `doc` 表 + `DocRepo`；参考 Vibe-Research 研报页交互 |
| 回测 | Vibe-Research | 参考→适配 | `backtest/engines/*`、`gate.py`、`run.py`、`metrics.py`、`loader.py`（替换现 `alpha/backtest.py` 玩具引擎，保留 JobQueue/artifact 外壳） |
| 相关性分析 | 现有 | 复用 | `alpha/factor.py`（口径已正确，直接用） |
| 模拟组合 | 全新 | 新写 | 雪球式调仓事件模型（+ 新增 `portfolio`/`rebalance` 表） |
| 接入 AI/设置 | 现有 | 复用 | 现有 `agent/provider` + `main.py` 凭据读取 |
| 全局 Agent 页面感知 | Vibe-Research | 参考→新写 | 参考 `AiPageProvider/useAiPage`；本项目新写页面上下文接缝 |

### 数据层供体（共享，先迁）

| 供体 | 方式 | 说明 |
|---|---|---|
| vibe-astock `duanxian/fetchers.py`、`data.py` | 适配 | A股涨停池/龙虎榜/资金流取数；接入本项目 `research/`/`alpha.data` 门面 |
| vibe-astock `duanxian/trade_calendar.py` | 复用 | 交易日历（相关性对齐/回测/组合净值都要） |
| 现有 `research/astock.py` 等 | 复用 | live 数据层保留 |

### 缝合顺序（最小可用，逐步含验收）

> 调整（2026-09-05）：**先把确定性平台跑通，Agent 作为后置增量到 S5 才真正接入**。
> S1–S4 全程 Agent 只留**占位 UI + 接口约定**，不接任何 provider。接缝设计为
> **provider 中立**——不预设接什么 agent 框架（dsh / Codex / Claude CLI / 其它均可经
> `AgentProvider` 防腐层接入）；**dsh 相关代码保留**，作为一个既有候选实现，不删。
> 当前 dsh SDK 签名不匹配的 8 个测试已 `@pytest.mark.skip`（reason 指向本节 S5），
> 使基线全绿；恢复条件写在 skip reason 里。

**阶段 S1 — 接缝准备（不迁业务页，不接 Agent）**
- 内容：新增业务页专用路由（现仅 `pages/:slug`）；**Agent 只做占位**——右下角浮标 +
  chat panel 占位 UI（显示「AI 助手即将上线」），并定义页面向 Agent 暴露上下文的**接口
  约定**（`{key, title, context, suggestions}`），**不接 provider、不发起对话**；
  后端 `agent/provider` 防腐层保持不动、不调用；修 pnpm `allowBuilds` 门禁使 `pnpm test` 可跑。
- 验收：① 新增一条专用路由可渲染占位页；② 页面能向占位接口注册 `{key,title,context}`（有单测断言接口形状）；
  ③ `pnpm test` 与 `pnpm build` 均绿；④ 后端 `88 passed, 8 skipped` 保持；⑤ 全程无任何 provider 调用。

**阶段 S2 — 迁只读确定性页（低风险优先）**
- 顺序：盘面数据 → 涨停样本统计 → 复盘看板（确定性部分，**不含五分析师/复盘裁判**）。
- 方式：适配 vibe-astock 计算模块进 `alpha/`，走 page spec 或专用只读页。
  现有 `daily-review`/`correlation` 两个 builtin 页走确定性 `alpha.review`/`alpha.factor`、
  不经 agent，**保留可用**，作为 S2 先行样例。
- 验收（每页）：① 首屏渲染 **0 次 LLM 调用**（断言无 provider 调用）；② 关键指标数值
  与 vibe-astock 同输入下一致（固定 fixture 断言）；③ 数据源不可用时显式标「不可用」，
  不显示为 0；④ 有针对性单测。

**阶段 S3 — 迁状态型业务页（含 CRUD）**
- 顺序：股票池 → 交易日志 → 我的研报。
- 方式：新增 `stock_pool` / `journal` 表（SQLite Repo）；研报复用现有 `doc` 表。
  专用 React 页，**不塞 page spec**。
- 验收（每页）：① CRUD 落 SQLite 真源，重启后不丢；② 交易日志可导入现有 vibe-astock
  JSON 或标准 CSV（导入前预览校验）；③ 股票池选中可跳相关性/回测/组合；④ 单测覆盖增删改查。

**阶段 S4 — 量化能力**
- 顺序：相关性（复用，仅接线）→ 回测引擎替换 → 模拟组合。
- 相关性验收：叠加图归一化到 100；相关矩阵为日收益率 Pearson；样本不足显式提示不出精确系数。
- 回测验收：迁 Vibe-Research **引擎+gate+run 三件套**（非只搬引擎）；先用固定数据写回归测试
  对齐 upstream 结果，再接 JobQueue；保留 NOTICE 归属；A股 T+1/涨跌停/整手规则生效。
- 模拟组合验收：雪球式调仓事件（生效日期+调权历史不可覆盖）；净值 vs 沪深300 归一化；
  权重不足 100% 视为现金；页面显式声明手续费假设。

> ──────── S1–S4 跑通 = 第一版确定性平台可用（不含 Agent）────────

**阶段 S5 — 引入 Agent（provider 中立，此时才真正接入）**
- 内容：先选定并接入一个 agent provider（dsh / Codex / Claude CLI 均可，dsh 代码已保留）；
  解决所选 provider 的接入问题（如选 dsh 则对齐 `DeepSeekHarnessConfig` 签名 / 锁定 SDK 版本，
  并恢复 8 个 skip 测试）；页面上下文快照接入消费方；只读解释先行；
  再加白名单草案动作 `stock_pool.add/remove`、`portfolio.create/rebalance`（草案→确认→确定性写接口）。
- 验收：① Agent 回答基于页面快照、不另起取数；② 换页不串上下文；③ 写操作必须经用户确认，
  Agent 不直接写库；④ 合规底线（不荐股/不预测/不给买卖时机）测试固化；⑤ 所选 provider 的
  接入测试恢复绿。

**阶段 S6 — 清理遗留**
- 内容：新能力验证通过后，退役旧占位页与不再符合定位的实现。
- 验收：全后端测试绿；无死引用。

### 风险与依赖

- **回测引擎迁移是最大不确定项**：Vibe-Research 引擎依赖其数据 `loader`，迁移时数据源要接到
  本项目取数层；先写回归测试对齐，避免「看着正常其实算错」。列为 S4 高风险子任务。
- **Agent 后置、provider 中立**：S1–S4 不接 Agent，只留占位 UI + 接口约定。接缝经
  `AgentProvider` 防腐层，不预设 agent 框架（dsh/Codex/Claude CLI/其它均可），dsh 代码保留。
  当前 dsh SDK 的 `DeepSeekHarnessConfig.session_root` 不匹配导致 8 个测试已 skip（基线全绿），
  不阻塞 S1–S4（确定性页不经 agent）；S5 接入所选 provider 时再解决并恢复对应测试。
- **技术栈**：Vibe-Research 回测是 Python（与本项目一致，可直接迁）；其 orchestrator 是 TS，
  **不迁**（本项目单 FastAPI 后端，避免双后端）。
