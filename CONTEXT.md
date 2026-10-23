# AlphaCopilot — 领域词汇表

> 纯词汇表，不含实现细节。写代码/文档时用这里的词，不要另造同义词。
> 决策依据见 `docs/adr/`，硬规则见 `AGENTS.md`。

## 产品

**AlphaCopilot**
个人本地 A 股低频量化投研工作台，单机运行。**AI native**（ADR-0009）：
不是「AI 只能解释」，而是「AI 参与探索与表达，但数字的可信度必须可区分」。
以 `AlphaTrading/` 下 Vibe-Research 与 vibe-astock 的能力为供体缝合，能复用就不重写。

**投研（Research）**
以人工阅读判断为主的工作流：宏观看板、复盘看板、股票池、研报管理。

**量化（Quant）**
以程序化分析为主的工作流：相关性、回测、模拟组合、因子研究。

## 数字可信度（贯穿全产品的核心区分）

**确定性层（Deterministic Layer）**
`backend/{research,duanxian,alpha}`。纯函数、不持状态、不依赖框架。
「这个数字是怎么算出来的」有代码可查、可重跑。

**provenance（来源凭证）**
每个 artifact 必带。两种：
- `deterministic` —— 可以给到 `fn + params + dataAsOf`，**只能由服务端调用
  `alpha.registry` 白名单函数铸造**；
- `agent` —— agent 自己算/自己写的，带 `runId + codeHash + dataAsOf`，前端显示 AI 角标。

agent 在 manifest 里声称的 `deterministic` 一律被改写为 `agent` 并记 `claimedKind`。
这不是不信任 agent 的诚实，是因为**无法审计它的代码**——所以退一步，把「可不可信」
做成可见的属性，而不是假装能守住（ADR-0012）。

**artifact**
一次产出的结构化结果（表格 / 序列 / 图表数据 / 文本），带 provenance。
不是「文件」，是「可被页面引用的一块内容」。

**run**
一次计算的记录：谁、什么参数、哪份数据、什么时候跑的。软删（可恢复）+ 备注。
硬删会毁掉「当时跑的是哪版代码」的证据链。

## 页面

**page spec**
页面即数据，不是手写 TSX（ADR-0016）。由 `params`（可调参数）+ `blocks[]` 组成，
走 `/p/:slug` 通用渲染。加一个分析页**不写 React**，只写 spec。

**block**
页面里的一个内容块。必须带 `renderer` 判别符（`lwc` / `echarts` / `table` / …），
不能只看 `kind: "chart"` —— 决定用哪个库渲染的是 `renderer`。

**analysis_ref**
block 引用确定性计算的方式：`{fn, params}`，`fn` 必须在 `alpha.registry` 白名单内
（现有 17 个）。agent 造不出取数函数，这是 spec 的安全边界。

**图表分工（ADR-0014）**
K 线 / 净值 / 回撤 / 买卖点 → **Lightweight Charts**（金融时间序列）；
热力图 / 分层 / 散点 / 归因 → **ECharts**。不能混用，也不叠加两个 chart 实例。

## 取数

**capability（vendor 能力）**
`data-service/vendor/a-stock-data` 从 SKILL.md 加载的可调用函数，现有 104 个，覆盖
15 层（A 股 / 基金 / 期货 / 期权 / 可转债…）。agent 广度探索走 `/api/v1/invoke`。
**不让裁剪**：今天用不到的层，以后会用。

**两条取数入口（ADR-0015）**
- 页面高频路径 → `research/astock.py`（语义封装：`DataUnavailable` / 域名兜底 / 多源尝试）
- agent 广度探索 → vendor 的 capability

**data-service**
**vendor 运行时宿主，不是我们的数据服务**。存在的唯一理由是依赖隔离
（vendored mootdx 锁 `httpx<0.26`，与主环境冲突）。它必须无状态。

**取不到 ≠ 0**
任何数据缺失一律 `available: false` + 非空 `reason`。返回空数组冒充成功会画成一条平线，
比不画更误导。

## Agent

**AgentProvider**
agent 运行时的防腐层契约。当前唯一实现是 **PiProvider**：Pi 以 `--mode rpc`
子进程运行，`cwd = workspace/`，`--approve`（否则 RPC 下 MCP 与 skills 静默不加载）。

**skill（白名单）**
`skills/` 下 13 个 SKILL.md，不是上游全量 88 个。qveris / crypto 系列 / mootdx /
tushare / yfinance 一律不迁移（AGENTS 硬规则 11）。

**页面上下文（Page Context）**
当前页面向 agent 暴露的「已展示的确定性数据快照」，agent 据此解释，不另起取数。

**AiConsole（会话面板）**
右下角浮标唤出的**浮窗**（可拖动 / 缩放 / 吸附 / 窄屏抽屉），覆盖在所有页面之上，
**不参与布局流**。会话历史读数据库，不读 Pi 的 session 文件（那不是产品真源）。

## 各看板

**宏观看板（Macro Dashboard）**
一屏看宏观脸色：社融、PMI、国债收益率曲线、LPR、回购利率、北向、两融。
每块都是「历史序列 + 当前读数」，不是孤立数字 —— 孤立数字无法比对。

**复盘看板（Daily Review）**
盘面复盘一屏：市场情绪、打板情绪、连板梯队、成交额榜、板块资金轮动。
含涨停样本统计（次日表现统计，不是策略回测）。不含自选（自选见股票池）。

**回测（Backtest）**
策略在历史数据上的表现评估。逐 bar 撮合 + A 股市场规则（移植自 HKUDS/Vibe-Trading，
MIT，保留 NOTICE）。策略可插拔（`STRATEGIES` 注册表）。

**模拟组合（Simulated Portfolio）**
雪球式持续组合：标的 + 权重 + 调仓事件，从创建日起记净值，默认基准沪深 300。
不涉及真实下单。

**相关性分析（Correlation）**
归一化走势叠加 + 日收益率 Pearson 相关矩阵。基于收益率而非价格（避免伪相关），
多标的按交易日交集对齐。

## 导航分组

**市场复盘**：宏观看板 / 复盘看板（含涨停样本统计）
**研究管理**：股票池 / 我的研报
**量化研究**：回测 / 相关性分析 / 模拟组合 / Run 记录
**个人与系统**：交易日志 / 接入 AI（设置）
