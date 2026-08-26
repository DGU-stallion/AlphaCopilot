# AlphaCopilot

> ⚠️ **大重构进行中**：项目已从 FastAPI + React 单体迁移至
> [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 插件体系。
> 旧单体完整归档于 `archive/pre-dsh` 分支（tag `archive-v0.3`），见
> [ADR-0004](docs/adr/0004-dsh-plugin-rewrite.md)。

个人量化投研系统：以自然语言驱动研究数据查询与交互式图表分析，
运行于 dsh agent 底座之上。

```
对话：「对比贵州茅台和五粮液近60天收盘价走势」
  ↓ agent 调用 MCP 数据工具
对话流内出现双线叠加 ECharts（可 legend 切换 / hover / 缩放）
```

## 项目结构

```
AlphaCopilot/
├── packages/
│   ├── dsh-alphacopilot-research/         # Python：MCP 数据服务（65 函数封装）
│   ├── dsh-alphacopilot-research-bridge/  # bundle：注册 MCP server
│   ├── dsh-alphacopilot-chart-plot/       # bundle+client：对话流交互图表
│   ├── dsh-alphacopilot-desk/             # bundle：合规 prompt / skills / swarm preset
│   └── dsh-alphacopilot-web/              # bundle+client：每日复盘面板
├── backend/research/                      # 数据层库代码真源（A 股/全球/资讯/持仓）
├── docs/
│   ├── PLAN.md                            # 重构计划
│   ├── TASKS.md                           # 任务拆分与状态
│   └── adr/                               # 架构决策记录
└── CONTEXT.md                             # 领域词汇表
```

## 启动（目标形态）

```bash
dsh --profile alphacopilot    # 独立 profile，不影响本机默认 dsh
```

## 开发

- 计划与进度：`docs/PLAN.md`、`docs/TASKS.md`
- 分支规范：`feat/T<nn>-<slug>`，squash merge，conventional commits
- TS 包：pnpm workspace（`packages/*`）；Python：`backend/` 与包 1

## 历史

原 Vibe-Research + Vibe-Trading 合并版（投研看板、回测、因子库）见
archive 分支；其能力将按 `docs/TASKS.md` 的节奏以插件形式回归。
