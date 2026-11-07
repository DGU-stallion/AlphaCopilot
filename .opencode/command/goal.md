---
description: 自主跑完目标范围内的全部任务，不中途请示
agent: build
---

你是自主执行模式。目标：$ARGUMENTS

规则：
1. 依据仓库的 `AGENTS.md`（硬规则）与 `docs/REFACTOR-PLAN.md`（当前计划）执行任务，从最小未完成项开始按依赖顺序推进，直到目标范围内全部完成或被硬阻塞。
2. 决策依据优先级：`AGENTS.md` 硬规则 > `docs/REFACTOR-PLAN.md` > ADR（仅 0009 及以后；0001–0008 已被取代）> 轮次记录（`docs/ROUND*.md`）。
3. 不要向用户提问。遇到歧义选与既有架构最一致的一项，并记录进任务产出文档。
4. 每个任务完整走流程：分支 `feat/<slug>` → 实现 → 本地验证（backend `pytest -q` + `ruff check .`；frontend `tsc --noEmit` + `vitest --run` + `vite build`）→ squash PR → merge → 删分支 → 更新计划文档的状态列。
5. 遇到 CI 失败：修复后重推；连续 2 次修不好则回滚该分支并在最终报告中说明。
6. 全部完成后输出总结报告：完成任务列表、PR 号、CI 状态、遗留问题。

现在开始，直到目标达成前不要停下来等我确认。
