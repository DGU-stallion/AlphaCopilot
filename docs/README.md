# 文档地图

先说结论：**只有 `REFACTOR-PLAN.md`、`adr/`、`AGENTS.md` 是「照着它实现不会错」的。**
其余是按轮次留下的记录，读来了解「为什么」，不要当作当前实现说明。

## 活文档（改代码前该读）

| 文件 | 是什么 | 什么时候读 |
|---|---|---|
| [`../AGENTS.md`](../AGENTS.md) | 硬规则 + 目录职责 + 反模式 | **每次动代码前**。规则 1 条就能让你少走一天弯路 |
| [`agents/WORKFLOW.md`](agents/WORKFLOW.md) | **流程硬规则 P1–P8**（任务怎么进 issue、治理 vs 执行、一任务一 PR） | 开工前；觉得「不知道 agent 在干什么」时 |
| [`../CONTEXT.md`](../CONTEXT.md) | 领域词汇表（纯词汇，无实现） | 不确定某个词在项目里指什么 |
| [`REFACTOR-PLAN.md`](REFACTOR-PLAN.md) | v2 重构的**决策依据**、目标架构、风险对策（**不含进度**） | 想知道当初为什么这么设计 |
| [`adr/`](adr/) | 架构决策记录 0001–0016 | 想知道「为什么不是另一种做法」 |

**进度和任务状态不在 `docs/` 里，在 issue tracker**（P6）：

```bash
gh issue list --repo DGU-stallion/AlphaCopilot --state open
gh issue list --repo DGU-stallion/AlphaCopilot --label ready-for-agent
```

ADR 里 **0001–0008 已被取代**（插件化 / dsh SDK 路线 → ADR-0009/0010 的 Pi 路线）。
保留不删是因为它们记录了试错过程；但**不要把 0001–0008 当实现依据**。
每份 ADR 顶部有状态标注。

## 轮次记录（了解上下文用，不是当前状态）

| 文件 | 覆盖 |
|---|---|
| [`ROUND2-BRIEF.md`](ROUND2-BRIEF.md) | 用户 10 条反馈的核实与执行；A5 起止日期 + 3 个真 bug |
| [`ROUND3-PLAN.md`](ROUND3-PLAN.md) | 包划分与交付契约；末尾「执行结果」逐条对账，含未做项与原因 |

这两份的价值在**诚实清单**：哪些做了、哪些没做、为什么没做、挖出什么 bug。
里面的代码片段可能已随重构变化，以代码为准。

## 素材

| 路径 | 是什么 |
|---|---|
| [`research/`](research/) | 上游能力清单（a-stock-data v3.10）、UI 设计调研 |
| [`prototypes/`](prototypes/) | 三版设计原型（D-A/B/C）+ 截图，ADR-0014 取舍的视觉依据 |
| [`agents/`](agents/) | **流程规则**：`WORKFLOW.md`（P1–P8 硬规则）、`issue-tracker.md`（agent 怎么取活）、`triage-labels.md`（标签映射）、`domain.md` |

## 已删除（2026-10-23）

`PLAN.md`、`TASKS.md`、`spikes/`（15 个 dsh/cordis 路线验证）、
`alphacopilot-planning-transcript.md`（3200 行原始对话）。

删除理由：它们描述的是**已被 ADR-0009/0010 取代的路线**，留在原地会让 agent
和人都读到错误的前提。仍在 git 历史里（`git log --diff-filter=D -- docs/`）。
ADR-0004/0006/0007 正文里的引用已就地标注「已删除」，不留死链。
