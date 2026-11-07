# 开发流程硬规则

> 这套规则解决三个具体问题：
> 1. **通过 session 管开发，越到后面越不知道 agent 在干什么** → 任务离开 session
> 2. **agent / subagent 多了之后，改了什么、有什么后果不知道** → 一任务一 PR + 可视化
> 3. **没想好产品定位就开做，过程中跑偏** → 治理项与执行项物理隔离
>
> 规则编号用 `P`（process），引用时写 `P3`。

---

## P1 — 没有 issue，不开分支，不开 session

任务必须存在于一个不依赖任何对话的地方。

**为什么**：session 会被 compact，上下文会丢，但 issue 不会。你在会话里丢的只是「聊了什么」，
丢不了「要做什么」。

```bash
# 开工前
gh issue create --repo DGU-stallion/<repo> --title "..." --label "execution,ready-for-agent"
# 或领现成的
gh issue list --label ready-for-agent --json number,title,body
```

**唯一例外**：探索性 spike，且明确以「关掉就丢」为前提。这类不开 issue，也不提交代码。

---

## P2 — 一任务一 PR，正文写 `Closes #N`

**为什么**：这是「改了什么」和「有什么后果」之间的唯一可查证连接。
没有它，56 个改动就是一个黑盒 —— 合并出问题无法定位，审查无处落脚。

```bash
gh pr create --base main --head feat/<slug> \
  --title "..." --body "... Closes #12"
```

**合并后**：`Closes #N` 自动关闭 issue，PR 里保留完整 diff 与 review 记录。

---

## P3 — 分支活不过两周

分支存在超过两周，说明它承载了多个任务。拆开。

**判断**：如果分支上的 commit 不能一一对应到 issue，它已经太大了。

**例外**：明确的长周期重构，但必须有 milestone 且每个里程碑合一次 `main`。

---

## P4 — 治理项不进 agent 队列

| | 治理项 | 执行项 |
|---|---|---|
| 问题 | 要不要做？做成什么样？ | 怎么做？ |
| 判断 | 「做完了产品可能还是不该存在」 | 「做完了产品一定更好」 |
| 标签 | `governance` + `ready-for-human` | `execution` + `ready-for-agent` |
| 谁能做 | **只有人** | agent |
| 产出 | `docs/decisions.md` 的一条 D-xx / ADR | commit + PR |

**为什么**：增加执行并发度只改善执行。治理跟不上，更快的执行只是更快烧资源。
agent 不知道「这一卷建议下线」，它会非常认真地优化一个该被砍掉的功能。

**检查**：`gh issue list --label governance --state open` 是人的待办，不是 agent 的。

---

## P5 — 每条 issue 必须有验收标准，否则不打 `ready-for-agent`

缺验收 = 无法判断「做完了」。见 `docs/agents/issue-tracker.md` 的任务契约模板。

验收必须是**可执行的命令 + 期望输出**，不是「功能正常」。

---

## P6 — 计划写在 issue 里，不写在文档里

`docs/` 只放**不随时间漂移**的东西：

| 该放 | 不该放 |
|---|---|
| ADR（为什么不是另一种做法） | 里程碑进度 |
| GLOSSARY / CONTEXT（领域词汇） | 任务清单 |
| 反模式与硬规则 | 「M0 ✅ M1 ✅」这类快照 |
| 需求规格（会变，但要 diff 可查） | 谁在做哪条 |

**为什么**：计划会变，文档不会。一个写着「全部里程碑 ✅」的计划文档，
在 main 落后 9 周时是**主动误导**。

---

## P7 — 依赖要区分「接口合入」和「运行时接入」

下游任务等上游时，明确写清等的是哪一个：

- 等**接口定义合入**（type / 契约 / OpenAPI schema）→ 立刻可并行
- 等**上游模块运行时接入**（能真跑）→ 必须串行

**为什么**：这个区分能把一条串行长链拆成多条并行工作线。这是并发空间的真正来源 ——
不是加更多 agent。

---

## P8 — 每个 commit 必须能回答「这属于哪个 issue」

commit message 里带 issue 号，或 PR 正文写 `Closes #N`。

```bash
git commit -m "fix: 修静态白名单 (closes #8)"
```

**为什么**：这是「有什么后果」可追溯的最小单位。

---

## 怎么检查自己在不在规则里

```bash
# 1. 有没有没进 issue 的活
git log --oneline origin/main..HEAD | wc -l     # 应该等于未完成 issue 数

# 2. 分支活了多久
git log -1 --format=%cr origin/main..HEAD

# 3. 人的待办
gh issue list --label governance --state open

# 4. agent 的待办
gh issue list --label ready-for-agent --state open

# 5. agent 到底干了什么
pi-agents                    # 当前项目最近的 session
pi-agents -s <id> --git      # 单个 session：每个 subagent 改了哪些文件、留下哪些提交
pi-agents --summary          # 跨项目：哪个项目在动
```

---

## 已确立的流程决策

| 日期 | 决策 |
|---|---|
| 2026-11-07 | 不引入 Linear。用 GitHub Issues 作为任务层，理由见下 |

**为什么不引入 Linear**：

- 1 人团队，席位费白花
- 12 个仓库，8 个已停 → Linear 要建 12 个 project
- **最需要的能力是「代码与任务的关联」** → GitHub 原生（`Closes #N`），Linear 要集成
- 已有配置（`triage-labels.md` / `issue-tracker.md` / `gh` 登录 / CI）全在 GitHub

**什么时候该换**：任务数稳定超过 30 条、依赖跨 3 层以上、同时开 5 个以上 worktree，
且开始需要「自动算出当前什么能开工」。那时再评估。
