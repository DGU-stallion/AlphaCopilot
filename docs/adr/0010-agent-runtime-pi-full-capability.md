# ADR-0010 — Agent 运行时改用 Pi SDK，并授予完整能力（含 bash）

**状态**：已决定（**2026-10-21 修订：RPC 模式下的资源挂载与 skills 白名单**——见文末「修订」）
**日期**：2026-10-20 · 修订 2026-10-21
**取代**：ADR-0006 决策 4（代码执行只经自有 `run_python`、不给 agent bash）、
ADR-0007 决策 2 的准入约束（provider 必须能禁用 shell）、AGENTS 硬规则 9。
**保留**：ADR-0007 决策 2 的**结构性成果**——`AgentProvider` 中立契约继续有效，
Pi 只是它的第二个实现。

## 背景

### 1. dsh 已不可用且不可持续

- `backend/agent/providers/dsh.py:42`、`backend/conftest.py:12`、`scripts/dev_keyless.sh:10`
  三处硬编码 `/Users/a19150/Project/deepseek-harness/`，该目录已不存在。
- 后果：后端 AI 对话 500（`ModuleNotFoundError: deepseek_harness`），
  `pytest` **8 failed / 153 passed**，而这 8 个正是唯一覆盖 AI 能力的测试。
- 即使修复依赖，dsh 仍在 developer preview：官方 README 明写「THERE WILL BE
  COMPATIBILITY-BREAKING CHANGES」，协议文档明写「no compatibility promise」，
  npm `latest` 仍是 `0.1.2-alpha.2`。

### 2. dsh 与产品形态存在类别错配

dsh 是为**编码 agent**（bash / 读写文件 / apply patch）设计的运行时。本项目的
原始定位却是「AI 只解释」，因此历史上一直在改 dsh 来禁用它的主要能力：

| 改动 | 目的 |
|---|---|
| patch 停用 `persistent-bash` | 不给 shell |
| 改 `DSH_SESSION_ROOT` | 避免与其它 profile 的 JSONL 压缩冲突 |
| 加 `llm-pi-ai` adapter | agnes 走 openai-completions |
| 收敛 `max_tokens` 到 65536 | agnes 端点上限 |
| 置空 `all_proxy` | socks 代理 dsh 不支持 |

同时协议层缺陷恰好命中产品需求：**无中途取消**（放弃 turn 只能杀进程）、
**审批流是 dead capability**。

### 3. 产品方向已改为 AI native，需要完整能力

用户在 2026-10-20 明确：
- 选择 B 路线（agent 写代码产图），而非「AI 只解释」；
- **不限制 agent 能力，把完整 Pi 集成进项目**；
- 理由：个人投研量化、不涉及交易、出错不造成重大损失、可接受 AI 的锯齿状能力。

这使 ADR-0008「AI 只解释」的核心约束失效，需要显式取代而非静默违背。

## 决定

### 1. Agent 运行时 = Pi SDK（`@earendil-works/pi-coding-agent` 1.3.0）

- MIT 许可，npm `latest` 稳定版（非 rc）。
- 接入形态：**`pi --mode rpc` 常驻子进程 + JSONL over stdio**。
  Python 后端通过 `PiProvider` 驱动，不写 TS 业务代码。
- 理由：Pi 只有 Node/TypeScript 实现（无官方 Python SDK；PyPI 上的
  `pi-coding-agent` / `pi-sdk` 均为无关项目）。RPC 模式是官方支持的语言中立
  边界，官方文档自带 Python 最小客户端示例。
- `RpcClient`（TypeScript）与 Python 自写 client 二者之间，本项目用后者，
  因为它让整个业务后端保持 Python。

### 2. 授予完整工具集（含 bash / read / write / edit）

- 不裁工具。Pi 默认工具集（`read` / `bash` / `edit` / `write`）全部保留，
  另加项目自定义工具与 MCP server。
- `run_python` **保留但降级**：从「唯一代码执行通道」变为「**带留档的便利封装**」
  （预置 alpha 导入路径、自动分配 `run_id` + 存 `code.py`、结构化产出契约）。
  agent 也可以直接用 bash 跑 python。
  「先调 `alpha.*` 库函数算指标」这不再是合规要求，只是一条使用建议 ——
  真正的硬约束在产物侧（服务端盖章权，ADR-0012「已决 1」）。

### 3. 安全边界：接受残余风险，用配置降低而非架构保证

**风险陈述（必须显式记录）**：Pi 工具以启动进程的操作系统用户权限执行。
Pi 官方安全文档：*"Watching the transcript, using project trust, and reviewing
changes do not create a security boundary."* 因此：

- agent 可读取本机任意该用户可读的文件，包括 `~/.dsh/.credentials.yaml`、
  `~/.pi/`、SSH key、以及整个 `~/Project/`；
- agent 可写、可删该用户可写的文件；
- 网络访问不受限（可外发数据）。

**接受理由**：单人本机、无实盘下单、无他人数据、可接受重装成本。

**降低措施（配置层，非安全边界）**：

| 措施 | 做法 |
|---|---|
| cwd 限定 | Pi 进程以 `workspace/` 为 cwd 启动，工具默认路径落在此处 |
| 不读项目文件 | `--no-context-files`，避免 Pi 把 `AGENTS.md` 之外的目录当上下文 |
| session 就地 | `--session-dir workspace/.pi-sessions`，不污染 `~/.pi/agent` |
| 密钥不落 workspace | 沿用现有约定：密钥只在 `~/.dsh/.credentials.yaml`，代码不读不写 |
| 可回滚 | Pi 的 session JSONL 保留完整 tool call 记录，误改可追溯 |
| **`--approve` + 项目 `.pi/`** | 启用项目信任；**不设** `PI_CODING_AGENT_DIR`（**2026-10-21 实测修正**，见修订 §1） |

### 4. 保住 `AgentProvider` 契约（ADR-0007 的结构性遗产）

`backend/agent/provider.py` 的 `AgentProvider` / `AgentEvent` / `ProviderSpec`
**不改**。`PiProvider` 实现该 Protocol，事件映射：

| Pi 事件 | 中立事件 |
|---|---|
| `message_update.assistantMessageEvent.text_delta` | `text_delta` |
| `tool_execution_start` | `tool_started` |
| `tool_execution_end` | `tool_result` |
| `agent_settled` | `turn_end`（`aborted` → `finish_reason`） |
| provider `error` | `error` |

业务层（`api/*`）、前端 SSE、`useAiChat` 零改动。

**这意味着「以后还能换 agent」仍然成立**，但准入约束从「必须能禁用 shell」
改为「必须能流式输出、能执行工具、能被中止」。第三个条件是新加的——它把
dsh 排除在外（无中途取消）。

## 权衡

| 备选 | 否决原因 |
|---|---|
| 继续用 dsh（修 pip 依赖即可） | 2 行能修好今天的故障，但 developer preview + 类别错配 + 无 abort 依旧 |
| PydanticAI（纯 Python 同进程） | 测试成本、类型安全更优，但用户明确选择 pi，且 pi 的 skills/MCP/compaction 生态已熟悉 |
| smolagents（CodeAgent） | 概念最贴「agent 写代码」，但 skills/MCP/compaction 要自己补，本地沙箱不安全 |
| 自研 loop | 零框架依赖，但重试/流式工具调用/压缩都要自己写，与本项目价值无关 |

**代价**：

1. **多一个 Node 常驻进程**（Pi 是 Node 程序）。Python 业务后端 + Node agent
   运行时并存。
2. **JSONL 桥接需自写**（约 200 行 Python client）。
3. **失去 dsh 曾提供的沙箱假象**——但这本来就是假象（dsh 的 `SandboxMode`
   只写不管读和网络）。

## 影响

- `backend/agent/providers/dsh.py` 删除；`backend/agent/cordis.yml` 删除；
  `~/.dsh/profiles/alphacopilot-prod` 不再被项目使用（保留不删，属本机其它用途）。
- `backend/conftest.py` / `scripts/dev_keyless.sh` 的 `sys.path` hack 删除。
- **AGENTS 硬规则 9 重写**：从「不给 agent bash」改为「agent 拥有完整工具集；
  cwd 限定在 workspace；密钥不入库不进 workspace」。
- **ADR-0008 的「AI 只解释」被本 ADR 取代**。ADR-0008 的其余部分（固定业务页面、
  确定性计算为主、四个导航分组）继续有效——见 ADR-0011 的双轨产物规则。
- 新增依赖：Node ≥ 22.19（Pi 的 engines 要求）、`@earendil-works/pi-coding-agent`。
- 8 个红测试重写为 `PiProvider` 契约测试，并要求能在无真实模型的情况下
  （Pi 的 JSON 模式 + 固定输入）跑通，避免再次「AI 坏了没人知道」。

---

## 修订（2026-10-21）：RPC 模式下的资源挂载 + skills 白名单

> 触发原因：对 pi 1.3.0 实测后发现，按原文的启动参数，agent 会**静默地**
> 看不到我们的 MCP 工具和 skills。这不会红测试，只会表现为「AI 好像变笨了」。

### 1. 项目自持 agent 目录，而不是散着配

**实测事实**（`docs/security.md`、`docs/configuration.md`、`docs/settings.md`）：

- RPC / JSON / print 模式**无法弹 project trust 提示**。若 `defaultProjectTrust`
  为默认值 `"ask"`，则**跳过** 项目 `.pi/settings.json` / `.pi/mcp.json` / `.pi/skills`
  —— 不报错，只是不加载。
- `defaultProjectTrust` **只能在 agent 目录的 settings.json 里设**，不能设在项目 `.pi`。
- skills 的项目发现从 cwd 向上找，而 pi 的 cwd 是 `workspace/`；`skills/` 在仓库根，
  **不在 cwd 的祖先链上** → 递归发现不到。
  （解法：用 `--skill <dir>` 显式挂载，不依赖自动发现。）

**决定（2026-10-21 实测后修正）**：只用 `--approve`，**不设 `PI_CODING_AGENT_DIR`**。

```bash
pi --mode rpc \
   --no-context-files \
   --approve \
   --session-dir <repo>/workspace/.pi-sessions \
   --append-system-prompt "<合规 persona>"
```

> ⚠️ **原方案（`PI_CODING_AGENT_DIR=<repo>/workspace/.pi-agent`）已废弃**。
> 实测：把该变量指向项目的空目录，Pi 会**丢掉 `~/.pi/agent` 下的
> `models.json` 与 `auth.json`**，直接报 `Unknown provider "magpie"` /
> `No models available. Use /login ...`。而把 `auth.json` 复制进 workspace
> 又违反「密钥不进 workspace」的硬约束。两者不可兼得，所以放弃隔离 agent 目录。

前面担心的「与 `~/.pi` 互相污染」，实测影响面小于预期：我们要隔离的
MCP 与 skills 都在**项目 `.pi/`** 下（由 `--approve` 启用），
user-level 的 `~/.pi/agent/mcp.json` / `skills/` 只是不被动用，并不冲突。

项目 `.pi/` 内容（由 `agent/pi_env.py` 的 `write_project_pi_config` 生成）：

| 文件 | 作用 |
|---|---|
| `mcp.json` | 我们的 MCP server（`run_python` / `get_quote` / `submit_backtest`），**`exposure` 必须为 `"direct"`** |

> ⚠️ **`exposure: "direct"` 是必须的**（实测）。Pi 默认给 MCP server
> `codemode` exposure：工具**不声明给模型**，只能从 codemode 脚本间接调用。
> 实测对比（真 pi 1.3.0 + 最小 MCP server）：
> - 缺省 → `toolsAdded` 只有内置工具，没有 `mcp__*`
> - `"direct"` → `toolsAdded` 出现 `mcp__echosrv__hello`
>
> 这个差异**不红任何测试**，只表现为 agent 说「我没有量化工具」，转而用 bash 瞎算。

skills 由 `--skill <dir>` 显式挂载；不给时加 `--no-skills` 禁用自动发现
（否则会全量加载仓库根 88 个，见 §2）。

**对 `ProviderSpec` 的影响**：`system_prompt` 仍走 `--append-system-prompt`，
其余字段不变，`AgentProvider` 契约**不动**。

### 2. skills 白名单（撤回「全量恢复 88 个」）

原 M1-7「恢复 88 个 skills（从 `archive-v0.3`）」**违反 AGENTS 硬规则 10**（现为 M1-9），
且代价未计：88 个 description 合计 **17,603 字符 ≈ 5.9k tokens**，
每轮常驻 system prompt（最长单条 787 字符）。

**决定**：按白名单加载，分三档。

| 档 | 处理 | 内容 |
|---|---|---|
| **A · 加载**（约 30 个） | 进 `skills/` | A 股/财务/宏观/技术/风险/研究纪律类：`ashare-pre-st-filter` `candlestick` `chanlun` `correlation-analysis` `cross-market-strategy` `dividend-analysis` `doc-reader` `earnings-forecast` `earnings-revision` `event-driven` `factor-research` `financial-statement` `fund-analysis` `fundamental-filter` `global-macro` `macro-analysis` `management-deep-dive` `minute-analysis` `multi-factor` `pair-trading` `performance-attribution` `quant-statistics` `regulatory-knowledge` `report-generate` `research-discipline` `research-goal` `risk-analysis` `seasonal` `sector-rotation` `sentiment-analysis` `technical-basic` `thesis-tracker` `trade-journal` `valuation-model` `volatility` |
| **B · 不进 skills 目录，作为参考文档** | 保留在 `docs/research/skills-ref/`，agent 需要时用 `read` 读 | `deep-company-series` `private-company-research` `bottleneck-hunter` `behavioral-finance` `execution-model` `market-microstructure` `research-*` 长文类 |
| **C · 不迁移** | 违反硬规则 10 / 反模式 | `qveris`（硬规则 10 点名）`okx-market` `ccxt` `perp-funding-basis` `crypto-derivatives` `token-unlock` `stablecoin-flow` `onchain-analysis` `defi-yield` `shadow-account` `vnpy-export` `mootdx` `tushare` `yfinance` `eastmoney` `pine-script` |

**A 档的验收**：`pi --mode json "列出可用 skill"` 快照里
能见到且**仅见到** A 档条目；description 总字符数 < 8,000。

> C 档的判据：涉及实盘/合约/crypto/第三方付费数据源/已死数据源。
> B 档的判据：写长文的框架（进 system prompt 只为了被路由，不划算；用 `read` 按需读）。

### 3. 不可靠的假设要写成断言

原文「Pi 事件 → 中立事件」的映射表里，`text_delta` 的真实路径是
`message_update.assistantMessageEvent` 里 `type == "text_delta"` 的 `delta` 字段
（不是 `text`），`tool_execution_end` 的结果字段名是 `result`，
`agent_settled` 才有 `aborted`。**M1-1 的契约测试必须逐字段断言**，
不要靠对字段名的记忆实现。

