# Issue Tracker

Issues for this repo live in **GitHub Issues** at `DGU-stallion/AlphaCopilot`.

Issue tracker 是**任务的唯一真相源**。计划、进度、验收结论都在这里，不在 markdown 文档里，
也不在任何 agent session 里。

## Operations

- **Create issue**: `gh issue create --repo DGU-stallion/AlphaCopilot --title "..." --body "..."`
- **List issues**: `gh issue list --repo DGU-stallion/AlphaCopilot`
- **View issue**: `gh issue view <number> --repo DGU-stallion/AlphaCopilot`
- **Close issue**: `gh issue close <number> --repo DGU-stallion/AlphaCopilot`
- **Add label**: `gh issue edit <number> --add-label "..." --repo DGU-stallion/AlphaCopilot`

## agent 怎么取活

agent 只能领打了 `ready-for-agent` 标签的 issue：

```bash
gh issue list --repo DGU-stallion/AlphaCopilot \
  --label ready-for-agent --state open \
  --json number,title,body,labels
```

领到后**第一件事**是把标签换成 `in-progress`：

```bash
gh issue edit <N> --remove-label ready-for-agent --add-label in-progress
```

干完 → 提 PR，正文写 `Closes #<N>` → 等 review。

## 任务契约

一个 issue 要能被 agent 独立执行，必须有这五段。缺 `验收` 的一律不打 `ready-for-agent`。

```markdown
## 目标
一句话，可验收。

## 约束
不能做什么、边界在哪。

## 依赖
Depends on #12（明确写：等的是**接口合入**，还是**上游模块运行时接入**）

## 验收
可执行的验证命令 + 期望输出。

## 交付
代码 + 测试 + 变更记录。
```

**为什么「依赖」要区分两种**：下游只需要一份稳定的接口定义时，没必要等上游全部开发和集成完成。
这个区分能把串行计划拆成并行工作线。

## 治理项 vs 执行项

| | 治理项 | 执行项 |
|---|---|---|
| 判断标准 | 「做完了产品可能还是不该存在」 | 「做完了产品一定更好」 |
| 标签 | `governance` + `ready-for-human` | `execution` + `ready-for-agent` |
| 谁能做 | **只有人** | agent |
| 产出 | `docs/decisions.md` 里的一条 D-xx，或一份 ADR | commit + PR |
| 有验收标准吗 | **没有**，只有「需要拍板」 | 必须有 |

**治理项永远不进 agent 队列。** 否则 agent 会非常认真地优化一个该被砍掉的功能。

## 依赖与子任务

`gh` 需要 ≥ 2.94 才支持这两个（当前 2.92，先升级：`brew upgrade gh`）：

```bash
gh issue edit 6 --add-blocked-by 3          # 建依赖
gh issue create --title "..." --parent 3    # 建子任务
gh issue view 3 --json subIssues,blockedBy  # 读依赖
```

## PRs as a request surface

`false` — external PRs are not part of the triage queue.
