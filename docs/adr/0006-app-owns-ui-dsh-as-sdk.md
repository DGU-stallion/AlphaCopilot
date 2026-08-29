# ADR-0006 — 应用自持前后端，dsh 降级为 Python SDK 内嵌的 Agent 运行时

**状态**：已决定
**日期**：2026-08-29
**取代**：ADR-0004（迁移至 dsh 插件体系）、ADR-0005（前端即插件）

## 背景

ADR-0004/0005 把 AlphaCopilot 整体重写为 5 个 dsh 插件，产品形态变成
「一个 dsh profile」。执行到 T18a 后暴露出方向性问题：本项目的差异化价值是
**投研领域应用的展示层**（可交互图表、可生长的展示页、投研报告），而 dsh 的插件
体系是为「在通用 coding agent 外壳内扩展 agent 能力」设计的。宿主与客体关系倒置，
症状是 5 个包里 2 个是 UI bundle，且仅为证明「能画出一条折线」「能注入整页面板」
就消耗了 S2、S4 两个 spike。

进一步明确的最终效果（见 PLAN「北极星」）要求「在网页里随时新增展示页」，
而 dsh 的 client module 注册机制只支持编译期已知的页面，该需求在插件形态下
无法成立。

### 调研到的事实（deepseek-harness 源码，2026-08-29）

1. **官方 Python SDK 存在且是一等公民**：`python/sdk`（`deepseek-harness-sdk`，
   导入名 `deepseek_harness`）+ `python/sdk-runtime`（自带单文件 exe，目标机
   无需 Node）。形态为「Python 起 dsh 子进程，走 stdio 上行分隔 JSON-RPC」，
   插件组合由调用方提供的 `cordis.yml` 决定。
2. **SDK 运行时插件集是封闭的**：单文件 exe 的 VFS 内是固定包树，
   「开放插件集（从磁盘加载用户插件）」被官方明确列为已否决/未来演进。
   自研 TS bundle 无法挂入。
3. **但 `@deepseek-ai/dsh-mcp-client` 被特意纳入闭包**，作为「显式支持的
   自定义配置插件」，可连 stdio / Streamable HTTP MCP server 并注册其工具。
4. **闭包同时包含** skill / skill-filesystem / tool-skill、system-prompt / persona、
   subagent（spawn/fork in-process）、session-persistence-jsonl|sqlite、
   compaction、fs-sandbox / sandbox-local（含 macOS Seatbelt）/ sandbox-policy /
   permission-presets、tool-web / web-fetch / web-search；**不含**任何 client/web UI 包。
5. **协议面极小且有硬限制**（`packages/sdk/protocol/README.md`）：
   client→server 仅 `initialize` / `session/prompt` / `shutdown`；
   无协议版本协商，"no compatibility promise"；
   **无中途取消**（放弃一次 turn 只能关闭运行时进程）；
   **server→client 请求是 dead capability**（审批流不可用）。
6. **闭包内无 `dsh-bash-sandbox`**，只有不隔离的 `dsh-bash-local`；而
   `permission-presets` 在非隔离 bash 执行器上组合会直接抛错。
   `SandboxMode` 仅管文件写入，不管读取、不管网络。

## 决定

1. **产品由本仓库自持前后端**：React SPA（展示层）+ FastAPI（业务层）+
   Python 数据层；dsh 通过 Python SDK 作为**库**内嵌，只承担 AI 能力层。
2. **耦合面收敛到两处**：SDK 的 3 个 wire 方法 + 我们自写的 `cordis.yml`。
   dsh 的 session JSONL 视为 agent 内部记忆，**前端永不读取**；产品真源
   （消息 / artifact / 页面 / 策略 / 文档索引）在我们自己的数据库。
3. **该拥有的「插件」是 MCP server，不是 UI bundle**：MCP 是标准协议，
   同一个 server 既服务本应用，也可被任意 dsh profile 挂载。
4. **代码执行由我们自己的 `run_python` MCP 工具承担**，不给 agent bash；
   agent 的文件工具经 `dsh-fs-sandbox` + `sandbox-policy` 限定 `workspace-write`。
5. **重活不进 agent 的 turn**：回测等长任务走业务层 job 队列，agent 只负责
   「写代码 → 提交 job → 读结果」。这同时化解了协议无中途取消的缺陷。
6. **不再做 orphan 分支手术**：新工作线从 `archive/pre-dsh` 取资产，现 main
   打 tag `archive-dsh-plugins-v0.1` 保留（chart renderer、skills 仍需回收）。

### 已确认的五项取舍

| # | 决策 | 取舍 |
|---|------|------|
| 1 | 图表产出 = **ECharts option JSON** 为主，PNG 兜底异形图 | 要交互（legend/hover/dataZoom），代价是 Python 侧需 `alpha.chart` helper 约束输出 |
| 2 | **本机执行**，隔离由我们的 `run_python`（macOS Seatbelt profile）+ `fs-sandbox` 承担 | 不引入容器，代价是残余风险自担（见下） |
| 3 | AI 只能建 **draft 页面**，发布需人工确认 | 防幻觉污染展示层，代价是多一步交互 |
| 4 | 文档层起点 = **手动投喂 + SQLite FTS5**，MinERU 后续接入 | PDF 解析质量决定一切，先小样本摸底；预留 `DocParser` 接口 |
| 5 | 从 `archive/pre-dsh` **取资产而非整体复用**，只搬 4 类 | 旧视觉语言不留；新架构把换风格的表面从 15 页收缩到 ~6 组件 |

## 权衡

- **备选：继续 dsh 插件路线** → 否决。理由见背景；补充一条诚实的反面：
  「AI 写代码做研究」恰是 dsh 的主场（bash/editor/skills/compaction/subagent
  全部对口），且其 web UI 已免费提供 chat + 工具调用展示。若需求止于
  「对话 + 看图」，插件路线更快。是「随时新增展示页 / 页面即产品」把天平压向自有前端。
- **备选：SDK 但用 `launch_args_override` 跑 Node 组合** → 暂不采用，列为逃生口。
  它允许挂自研 TS 插件与官方 `dsh-code-runtime-python`（Code Mode），
  代价是重新引入 Node 依赖，且该后端文档自述「only 'typescript' has a
  published backend」，成熟度未知。等工具层超出 MCP 表达能力时再启用。
- **备选：Docker 隔离代码执行** → 用户明确选择本机。

## 残余风险（知情接受）

1. **本机执行 LLM 生成的代码等价于授予其当前用户权限**。`workspace-write`
   只约束写入，不约束读取与网络，裸用它 AI 仍可读 `~/.ssh`、`~/.aws` 并联网外传。
   缓解措施是 `run_python` 的 Seatbelt profile 显式 deny 读非白名单路径
   （G3 spike 的验收点），并把 workspace 与密钥物理分离。**这不等于容器级隔离。**
2. **dsh 处于 developer preview（0.1.0-rc.8）**，无兼容承诺。缓解：耦合面只有
   3 个 wire 方法 + 一个 cordis.yml；session 事件词汇表的变化只影响适配层一个文件。
3. **无中途取消**：停止 = 杀子进程。缓解：一会话一子进程 + 重活外移到 job。
   跨进程重启后同 `session_id` 能否续上历史**尚未实测**（G2 验收点）。
4. **平台限制**：runtime wheel 仅 linux x64/arm64 与 macOS 14+ arm64，无 Windows。

## 影响

- README / AGENTS.md 硬规则重写（原第 2/3/5 条是 TS 插件规则，已失效）
- `docs/PLAN.md`、`docs/TASKS.md` 重写；任务号从 **T21** 续编，不复用 T01–T20
- `packages/dsh-alphacopilot-research` 迁入 `backend/mcp/`（与业务层同 venv，
  `run_python` 才能注入 `alpha.*`）；另 4 个包随 tag 归档，不进新工作线
- 工具层方向调整：**不再把 65 个数据函数包成 MCP 工具**，收缩为
  「副作用类 + 快问快答类 + run_python + search_docs」，数据层价值转移到
  `alpha.*` 的 docstring 与 skills 文档
