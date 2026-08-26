# AlphaCopilot × DeepSeek Harness 重构计划（PLAN）

> 状态：已批准，执行中
> 前置决策：ADR-0004（大重构声明）、ADR-0005（前端即插件）
> 任务拆分见 `docs/TASKS.md`

## 背景与目标

将 AlphaCopilot 的「自然语言取数 → 对话流交互式图表」闭环迁移至 DeepSeek Harness
（dsh）插件体系。旧单体（FastAPI + React 15 页）整体归档于 `archive/pre-dsh`
分支（tag `archive-v0.3`），新 main 为插件化主干。

启动形态：

```bash
dsh --profile alphacopilot     # 一套独立 preset；不影响本机默认 dsh profile
```

## 交付物

| # | 包 | 类型 | 职责 |
|---|---|---|---|
| 1 | dsh-alphacopilot-research | Python / MCP | 65 个数据函数封装为 MCP 工具（首批 8 个）+ 同进程 REST |
| 2 | dsh-alphacopilot-research-bridge | TS bundle | patch 行注册 MCP server（受信任子进程） |
| 3 | dsh-alphacopilot-chart-plot | TS bundle + client | `chart/plot` 会话事件族 + ECharts keyed renderer |
| 4 | dsh-alphacopilot-desk | TS bundle | 合规 prompt 片段 + 领域 skills + swarm preset |
| 5 | dsh-alphacopilot-web | TS bundle + client | 每日复盘面板注入 dsh web UI + 共享主题 token |

宿主：dsh web 应用（唯一前端、唯一端口）；`backend/research/` 为数据层库代码真源。

## 里程碑与门禁

### M0 — Spike 门禁（任一失败 → 备选方案评审，不得带病进 M1）

| Spike | 验证问题 | 通过标准 |
|---|---|---|
| S1 (T05) | bundle 安装/重启/dump-config 流程 | hello bundle 出现在 `--dump-config` |
| S2 (T06) | 自定义 ConversationNodeDefinition 渲染 | mock 事件渲染出一条折线 |
| S3 (T07) | MCP server 注册方式与 transport | agent 调通 get_quote 返回茅台报价 |
| S4 (T14a) | web 插件能否注入整页面板 | 静态数据渲染出每日复盘卡片 |

S3/S2 失败备选：MCP 改 HTTP sidecar / 图表降级为特殊聊天节点。
S4 失败备选：每日复盘做成特殊聊天节点（可行性降级，不阻断）。

### M1 — research MCP（对应需求 P0 数据底座）
首批 8 工具：get_quote / get_kline / get_valuation / get_margin /
get_fund_flow / get_news / get_announcements / get_radar。
统一契约：错误 `{"error": msg}`；单结果截断 ≤6000 字符。

### M2 — chart-plot（对应需求 P0 出图）
事件族 `chart/plot`：`{chartId, series[], norm, title, chartType}`。
Definition 状态机遵守官方 cookbook 五条不变量。Renderer 按需引入 ECharts，
卸载 dispose，主题移植 `chart-theme.ts` 单文件控制。

### M3 — desk（对应需求 P1 人格）
合规 prompt（五维框架+中立规则）入 `ctx.systemPrompt`；
skills 直迁 ×5（candlestick / technical-basic / fundamental-filter /
risk-analysis / sentiment-analysis）；
investment_committee preset 按 spike 结论落地（port 或串行委派链降级）。

### M4 — 发布 v0.1.0
每包 README 四节（兼容版本/安装/验证/卸载）；`pnpm pack` 本地验证；
E2E 场景录屏归档。

## E2E 验收场景

输入「对比贵州茅台和五粮液近60天收盘价走势」：
1. agent 调用 get_kline ×2
2. 对话流出现双线叠加 ECharts（legend 切换 / hover 十字对齐 / dataZoom）
3. 刷新页面后图表从会话日志重建（不重算）

## Git 规范

- trunk-based；`feat/T<nn>-<slug>` 短命分支；一任务一 PR，squash merge
- Conventional Commits，PR 标题带任务号
- CI paths 过滤：`packages/**`→TS 管线；`backend/**`→Python 管线
- `main` 禁 force-push；`archive/pre-dsh` 永久只读

## 编码规范

**TS**：strict、ESM only、Node ≥18、Biome、Vitest、tsdown（prepare 自包含，
不假设 monorepo checkout 存在）、cordis 注册范式（一切经 ctx 注册，可逆清理）。

**Python**：ruff + pyright basic + pytest；MCP 层零业务逻辑（校验→调用
research 函数→JSON 化→截断）；docstring 即 LLM schema。

## 明确不做

quant 实盘/live/channels/qveris/scheduled；旧 15 页 React 前端；
每日复盘迁入 dsh web 的深度优化（仅列展望）。
