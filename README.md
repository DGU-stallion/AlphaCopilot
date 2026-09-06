# AlphaCopilot

> ⚠️ **定位调整（2026-09-05）**：已放弃「对话驱动 + AI 写 Python + 页面可生长」旧北极星，
> 改为 **确定性计算为主 + 固定业务页面 + AI 只解释**。见
> [ADR-0008](docs/adr/0008-deterministic-first-fixed-pages.md)。
> 历史决策 ADR-0002/0004/0005/0006/0007 保留作轨迹。

**个人本地 A 股低频量化投研工作台**：以确定性数据和后端计算为主体——宏观看板、
复盘看板（含涨停样本统计）、相关性分析、回测（多策略可插拔）、雪球式模拟组合、
交易日志、研报管理。全局页面感知 Agent 作为「分析副驾」：解释当前页面数据、回答
研究问题、提供观点，**不生成计算结果、不下单、不盯盘、不做多智能体辩论**。
（Agent 已接入真实对话：dsh SDK + agnes 端点 + 项目专属 profile `alphacopilot-prod`，
右下角可调整大小的对话面板，页面快照作上下文，合规底线由后端 persona 固化。）

第一版策略：以 `AlphaTrading/` 下 vibe-astock、Vibe-Research 的现成能力为供体缝合，
能复用就不重写；平台先搭起来，后续在使用中迭代。

```
市场复盘 → 建立股票池 → 相关性/策略假设 → 确定性回测 → 模拟组合跟踪 → 日志/研报沉淀
                              ↑ 全局 Agent 随时解释各页面数据、提供分析观点
```

四项定位边界与页面清单见 [`docs/PLAN.md`](docs/PLAN.md)。

## 架构分层

```
展示层  React SPA        固定业务页（缝合 vibe-astock/Vibe-Research）+ 全局 AI 对话面板
业务层  FastAPI + alpha  REST 端点 / 页面渲染 / 领域存储 / 分析库 / 会话编排 + SSE
AI 层   dsh runtime      agent loop / skills / MCP 工具（已接入：dsh SDK + agnes，node carrier）
数据层  research + docs  A股·全球·宏观·资讯·持仓纯函数 + 文档库
```

> 前端已由旧 page-spec 动态渲染整体替换为固定业务页（10 页缝合完成）；
> 回测/相关性仍走 `/api/pages/{slug}/render`，其余页直连专用 REST 端点。
> AI 对话走 `/api/sessions` + SSE（中立事件 text_delta/turn_end/…），provider 见 `backend/agent/`。

## 项目结构

```
AlphaCopilot/
├── backend/
│   ├── research/    # 数据层：纯函数（A股/全球/宏观/资讯），禁加框架依赖
│   ├── duanxian/    # 复盘/情绪/涨停样本等 A 股复盘计算（缝合自 vibe-astock）
│   ├── alpha/       # 业务层库：data · chart · factor · backtest · portfolio · registry
│   ├── api/         # FastAPI：会话编排 · SSE · artifact · page · job · 市场/业务端点
│   ├── agent/       # dsh SDK 适配层（与 dsh 的唯一耦合点）+ 合规 persona + cordis
│   └── mcpserver/   # 我们的 MCP server：run_python / get_quote / submit_backtest
├── frontend/        # React SPA（固定业务页 + AiConsole 对话面板 + useAiChat）
├── workspace/       # agent 可写工作区（sandbox 根），内含 runs/<run_id>/
├── skills/          # 投研方法论 skills ×5
└── docs/            # PLAN.md · TASKS.md · adr/ · spikes/
```

> AI 运行时用项目专属 dsh profile `~/.dsh/profiles/alphacopilot-prod`（不在仓库内，
> 见 `docs/adr/0007` 与 `backend/agent/`）；exe carrier 未构建的机器需 `DSH_RUNTIME_MODE=node`。

## 开发

- 北极星与计划：`docs/PLAN.md`；任务状态：`docs/TASKS.md`（改代码前先看）
- 后续开发从 **`main`**（当前可用版本）拉功能分支：`feat/<slug>`，squash merge，conventional commits
- 启动：
  ```bash
  cd backend && DSH_RUNTIME_MODE=node python -m api.main    # FastAPI :8900（AI 走 agnes+代理）
  cd frontend && pnpm dev                                    # Vite :5899，/api 代理到 :8900
  ```
- 验证：`cd backend && pytest`（默认跳过 `-m live`；真实 agnes 用 `pytest -m live`）/ `ruff check .`；
  `cd frontend && npx tsc --noEmit && npx vitest --run && npx vite build`

## 安全须知

AI 生成的 Python 在**本机**执行。隔离由 `run_python` 的 macOS Seatbelt profile 与
dsh 的 `workspace-write` 文件沙箱承担，**不等于容器级隔离**：dsh 的 SandboxMode
只管文件写入，不管读取与网络。请勿把密钥放在 workspace 内，详见
[ADR-0006 残余风险](docs/adr/0006-app-owns-ui-dsh-as-sdk.md)。
