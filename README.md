# AlphaCopilot

> ⚠️ **架构调整中（2026-08-29）**：已放弃「整体重写为 dsh 插件」路线，改为
> **应用自持前后端 + 通过 Python SDK 内嵌 DeepSeek Harness 作为 Agent 运行时**。
> 见 [ADR-0006](docs/adr/0006-app-owns-ui-dsh-as-sdk.md)（取代 ADR-0004/0005）。
> 插件化产物归档于 tag `archive-dsh-plugins-v0.1`；更早的单体在 `archive/pre-dsh`。

**对话驱动的量化投研工作台**：用自然语言描述研究意图，AI 写 Python 代码在你的数据上
算出结果、画成可交互图表；值得留下的结果固化成可随时新增的展示页；并能基于
研报／年报／公告／资讯产出带出处的投研报告。目标是理解不同市场／行业／标的之间的
联系，并据此构建交易策略。

```
对话：「分析近一年白酒板块 5 只标的与沪深300 的相关性」
  ↓ AI 生成 Python → 在沙箱内跑在你的数据上
对话流内出现可交互相关性热力图 + 文字结论
  ↓ 「发布为页面」
侧边栏多出一个展示页 —— 不改前端代码、不重启服务
```

四项能力承诺与验收口径见 [`docs/PLAN.md`](docs/PLAN.md) 第一节「北极星」。

## 架构分层

```
展示层  React SPA        Chat 时间线 + 动态页面渲染器 + 4 类 block 渲染器
业务层  FastAPI + alpha  会话编排 / job 队列 / 领域存储 / 分析库
AI 层   dsh runtime      agent loop / skills / subagent（经 Python SDK 内嵌）
数据层  research + docs  A股·全球·资讯·持仓纯函数 + 文档库
```

## 项目结构（目标形态）

```
AlphaCopilot/
├── backend/
│   ├── research/   # 数据层：纯函数，禁加框架依赖
│   ├── alpha/      # 业务层库：data · chart · factor · backtest · report
│   ├── api/        # FastAPI：会话编排 · SSE · artifact · page · job
│   ├── agent/      # dsh 适配层（与 dsh 的唯一耦合点）
│   └── mcp/        # 我们的 MCP server：run_python / publish_* / search_docs
├── frontend/       # React SPA
├── workspace/      # agent 可写工作区（sandbox 根），内含 runs/<run_id>/
├── skills/         # 投研方法论 skills ×5
└── docs/           # PLAN.md · TASKS.md · adr/ · spikes/
```

## 开发

- 北极星与计划：`docs/PLAN.md`；任务状态：`docs/TASKS.md`（改代码前先看）
- 分支规范：`feat/T<nn>-<slug>`，squash merge，conventional commits，任务号从 T21 起
- 命令：`cd backend && pytest` / `ruff check .` / `pyright`；`cd frontend && pnpm build && pnpm test`

## 安全须知

AI 生成的 Python 在**本机**执行。隔离由 `run_python` 的 macOS Seatbelt profile 与
dsh 的 `workspace-write` 文件沙箱承担，**不等于容器级隔离**：dsh 的 SandboxMode
只管文件写入，不管读取与网络。请勿把密钥放在 workspace 内，详见
[ADR-0006 残余风险](docs/adr/0006-app-owns-ui-dsh-as-sdk.md)。
