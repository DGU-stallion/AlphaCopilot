# AlphaCopilot

> ⚠️ **定位调整（2026-09-05）**：已放弃「对话驱动 + AI 写 Python + 页面可生长」旧北极星，
> 改为 **确定性计算为主 + 固定业务页面 + AI 只解释**。见
> [ADR-0008](docs/adr/0008-deterministic-first-fixed-pages.md)。
> 历史决策 ADR-0002/0004/0005/0006/0007 保留作轨迹。

**个人本地 A 股低频量化投研工作台**：以确定性数据和后端计算为主体——市场复盘、
盘面数据、涨停样本统计、相关性分析、回测、雪球式模拟组合、交易日志、研报管理。
全局页面感知 Agent 作为「分析副驾」：解释当前页面数据、回答研究问题、提供观点，
**不生成计算结果、不下单、不盯盘、不做多智能体辩论**。

第一版策略：以 `AlphaTrading/` 下 vibe-astock、Vibe-Research 的现成能力为供体缝合，
能复用就不重写；平台先搭起来，后续在使用中迭代。

```
市场复盘 → 建立股票池 → 相关性/策略假设 → 确定性回测 → 模拟组合跟踪 → 日志/研报沉淀
                              ↑ 全局 Agent 随时解释各页面数据、提供分析观点
```

四项定位边界与页面清单见 [`docs/PLAN.md`](docs/PLAN.md)。

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
