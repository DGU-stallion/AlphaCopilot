# AlphaCopilot

**AI native 的个人本地 A 股低频量化投研工作台。**

确定性计算提供可信数字，agent 提供探索与表达；两者按 provenance 区分，
前端对 AI 产出的数字打角标。单机运行，不联网存数据，不做实盘。

```
市场复盘 → 建立股票池 → 相关性/假设 → 确定性回测 → 模拟组合 → 日志/研报沉淀
                                   ↑ 全局 agent 随时解释当前页面
```

## 快速开始

```bash
# 后端（FastAPI，8900）
cd backend && python3 -m api.main

# 前端（Vite，5899）
cd frontend && npx vite --port 5899

# vendor 能力宿主（独立 venv。只跑加载器/能力时用得上，后端已内嵌调用）
cd data-service && .venv/bin/python -m pytest tests -q
```

依赖：Node ≥ 22.19、Python 3.13、`@earendil-works/pi-coding-agent`。
密钥只在 `~/.dsh/.credentials.yaml`，不进仓库、不进 workspace、不写日志。

## 目录

```
frontend/        React 19 + Vite + TS
  pages/         手写页（看板/CRUD）+ PageView（/p/:slug 通用渲染）
  components/page/  BlockRenderer · PageCanvas · ParamBar
backend/         Python 3.13 + FastAPI
  research/ duanxian/ alpha/   纯函数数据与计算层（不持状态、禁框架依赖）
  api/           唯一持有数据库、唯一耦合 agent 运行时
  agent/         AgentProvider 契约 + PiProvider（--mode rpc 子进程）
data-service/    vendor 运行时宿主（不是数据服务）：a-stock-data + 独立 venv
workspace/       agent 可写区（Pi 的 cwd）+ runs/<run_id>/
skills/          白名单内的 13 个 SKILL.md（不是全量 88 个）
docs/            见 docs/README.md（哪份是活的、哪份是历史）
scripts/         vendor 同步脚本、情绪历史回填
```

## 页面

| 路径 | 类型 | 说明 |
|---|---|---|
| `/macro` | 手写 | 宏观看板：社融 / PMI / 国债曲线 / LPR / 回购 / 北向 / 两融 |
| `/daily-review` | 手写 | 复盘看板：情绪趋势、连板梯队、封板率、板块资金 |
| `/watchlist` `/reports` | 手写 | 股票池 / 研报归档 |
| `/portfolios` `/journal` `/runs` | 手写 | 模拟组合 / 交易日志 / 回测记录 |
| `/settings` | 手写 | 接入 AI：模型选择、连通自检、合规边界 |
| `/p/:slug` | **page spec** | 数据驱动渲染（回测、相关性等）。加分析页不写 React |

`/p/*` 由后端 page spec（`params` + `blocks[]`）驱动，见 ADR-0016。
新增只读分析页优先组合确定性 block，而不是写新组件。

## 文档

| 想看什么 | 去哪 |
|---|---|
| 当前要做什么 | [`docs/REFACTOR-PLAN.md`](docs/REFACTOR-PLAN.md)（M0–M5） |
| 硬规则（改代码前必读） | [`AGENTS.md`](AGENTS.md) |
| 术语 | [`CONTEXT.md`](CONTEXT.md) |
| 为什么这么设计 | [`docs/adr/`](docs/adr/)（0001–0016，含被取代的旧决策） |
| 最近两轮改了什么 | [`docs/ROUND2-BRIEF.md`](docs/ROUND2-BRIEF.md) · [`docs/ROUND3-PLAN.md`](docs/ROUND3-PLAN.md) |
| 上游能力清单 | [`docs/research/a-stock-data-v3.10.md`](docs/research/a-stock-data-v3.10.md) |

## 四条最容易踩的线

1. **产品真源是数据库，不是 agent 的会话文件。** 前端永不读 Pi 的 JSONL。
2. **`provenance.kind = "deterministic"` 只能服务端铸造。** agent 在 manifest 里
   声称的一律改写为 `agent`，前端显示 AI 角标 —— 数字照样能显示，但用户知道它不可信。
3. **颜色只有一个真源** `frontend/src/theme/tokens.ts`；组件里出现 `#` 颜色字面量即违规，
   数字一律走 `<Num>`。
4. **破坏性操作必须可撤销**，不能靠「应该能重新生成」自我说服。

完整清单见 `AGENTS.md` 的「硬规则」。
