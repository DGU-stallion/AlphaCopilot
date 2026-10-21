# AGENTS.md — AlphaCopilot

> **当前状态：v2 重构中。** 开工前必读 [`docs/REFACTOR-PLAN.md`](docs/REFACTOR-PLAN.md)
> 与 ADR-0010 ~ ADR-0013。下文描述的是**重构后的目标形态**；重构前的实现细节
> 以 `main` 分支现状和 `docs/adr/0001`–`0009` 为准。
>
> **2026-10-21 修订**：后端保留 Python（不再写 TS）；skills 改为白名单；
> Pi 用项目自持 agent 目录。详见 ADR-0011 §0 与 ADR-0010「修订」。

产品定位：**AI native 的个人本地 A 股低频量化投研工作台**。
确定性计算提供可信数字，agent 提供探索与表达；两者按 provenance 区分（ADR-0012）。

## 结构速记（目标形态，M3 完成后）

```
apps/
  web/          React 19 + Vite + TS（Lightweight Charts + ECharts）
  server/       Python 3.13 + FastAPI（session / artifact / view / page / job / SSE）
data-service/   Python 3.13（research · duanxian · alpha），纯函数，不持状态
workspace/      agent 可写区（pi 的 cwd）+ runs/<run_id>/
  .pi/mcp.json  Pi 的项目级 MCP 配置（exposure 必须为 direct）
  .pi-sessions/ Pi session JSONL
skills/         白名单内的 SKILL.md（约 30 个；不是 88 个全量）
docs/           REFACTOR-PLAN.md · PLAN.md · TASKS.md · adr/ · research/
```

**后端是 Python，不是 TypeScript**（ADR-0011 §0，2026-10-21 修订）。
Pi 走 `--mode rpc` 子进程，这是语言中立边界；不存在跨语言共享类型层，
也没有 `packages/shared`。

**迁移期（M1–M2）目录名保持 `backend/` + `frontend/` 不变**，M3 才搬。

分层职责：

- `research/` `duanxian/` `alpha/`：纯函数数据与计算层，**禁加框架依赖**，不持状态
- `apps/server`：唯一持有产品数据库的角色；唯一与 agent 运行时耦合的角色；
  同进程直接调 `alpha.*` / `research.*`
- `apps/web`：只读 API，不读 agent 会话文件

## 硬规则

1. 从 `main` 拉分支 `feat/<slug>` → squash PR，conventional commits
2. **产品真源在我们的数据库**。agent 的 session 文件是它的内部记忆，前端永不读取；
   `apps/server` 负责把消息与 artifact 落库
3. **agent 不直接写数据库**：写库一律经 `apps/server` 校验（artifact manifest /
   provenance / page spec 白名单）
4. **重活不进 agent 的 turn**：长任务走 job 队列，agent「写代码 → 提交 job → 读结果」
5. **每个 artifact 必须带 provenance**（ADR-0012）：
   `deterministic`（fn + params + dataAsOf）或 `agent`（runId + codeHash + dataAsOf）。
   缺失直接拒收。
   > ⚠️ **本条目前未实现**（`artifact` 表无 provenance 列，manifest 校验不查）。
   > M1-7 负责落地；在 M1-7 合入前不要假装它在守门。
6. **可信数字的盖章权归服务端**（ADR-0012「已决 1」）。拆成两层，别混：
   - **行为层（建议，非硬约束）**：算回测指标/相关矩阵/因子 IC/敏感性/行情财务数值时，
     agent 应优先调用 `alpha.*` / `research.*`。这只是习惯，**不构成执法**。
   - **展示层（硬约束，可测试）**：`provenance.kind = "deterministic"` 只能由服务端
     调用 `alpha.registry` 铸造。**agent 在 manifest 里写的 provenance 一律不采信**，
     强制改写为 `kind = "agent"`，前端显示 AI 角标。
   - 后果：agent 用 bash 自己手算的数字照样能显示，但**带 AI 角标**，用户知道它不可信。
     这就是本规则的全部效力——不再假装能审计 agent 的代码。
7. **颜色/主题只写在 `index.css` 的 token 与 `lib/chart-theme.ts` 两处**，
   双主题 + 涨跌双口径（ADR-0013）
8. 图表分工：K 线/净值/回撤/买卖点 → **Lightweight Charts**；
   热力图/分层/散点/归因 → **ECharts**。
   block 必须带 `renderer` 判别符，不能只看 `kind: "chart"`
9. **agent 拥有完整工具集（含 bash / read / write / edit）**（ADR-0010）。
   这是显式接受的风险，不是疏忽：agent 以 OS 用户权限执行。
   必须有：pi cwd = `workspace/`、`--no-context-files`、session 落 `workspace/.pi-sessions`、
   **`--approve`**（**不要**设 `PI_CODING_AGENT_DIR`，会丢凭据）
   （不加后者，RPC 模式拿不到 project trust → MCP 与 skills 静默不加载，ADR-0010 修订 §1）
10. 不引入实盘/live/channels/qveris/scheduled 相关任何代码。
    **skills 也不得全量恢复**：`qveris` / crypto 系列（`okx-market` `ccxt` `perp-funding-basis`
    `crypto-derivatives` `token-unlock` `stablecoin-flow` `onchain-analysis` `defi-yield`）/
    `shadow-account` / `vnpy-export` / `mootdx` / `tushare` / `yfinance` 一律不迁移。
    白名单见 ADR-0010 修订 §2。
11. LLM 输出合规底线：不荐股、不预测涨跌、不给买卖时机（persona 固化）。
    **这是 prompt 层约束，不是运行时限制**——agent 能力不受限，输出有底线

## 反模式（重构中必须避免）

- ❌ 给页面加「问 AI」占位按钮（旧 `AskAiButton`/`DeepDive` 已删）
- ❌ 用 `glass` / `shadow-glow` / 渐变 / `rounded-2xl` 表达层次
- ❌ 让 agent 生成前端代码或直接改 DOM（它只能产 View / artifact）
- ❌ 在 `data-service` 里存应用状态（它必须无状态）
- ❌ 新增只读分析页时先写 React 组件（先看能不能用确定性 View 组合出来）
- ❌ 恢复 mootdx（K 线/盘口/逐笔 2026-09 起失效，本机连财务也取不到）
- ❌ 直接把我们自己的取数逻辑写成第二套：`data-service/vendor/a-stock-data` 是唯一取数实现
- ❌ 裁剪 vendor 的端点：保留全部 15 层（期货/期权/可转债以后会用）
- ❌ 设 `PI_CODING_AGENT_DIR` 指向项目目录 —— 会让 Pi 丢掉 `~/.pi/agent` 的
  `models.json`/`auth.json`（实测报 `Unknown provider`）。隔离靠项目 `.pi/` + `--approve`
- ❌ MCP server 不给 `exposure: "direct"` —— 默认 `codemode` 不把工具声明给模型
- ❌ 在 RPC 模式下依赖 project trust 自动生效（不会弹窗，只会静默不加载）
- ❌ 「反正重写 TS 就能解决」——后端就是 Python（ADR-0011 §0）
- ❌ 把 88 个 skills 一次性拷进 `skills/`（白名单，见硬规则 10）

## 命令

```bash
# 重构期（M1–M2）：后端是 Python，没有第二套后端
cd backend && pytest -q                    # Python 测试（含 PiProvider 契约测试）
cd backend && ruff check .                 # lint
cd frontend && npx tsc --noEmit && npx vitest --run && npx vite build

# 目标形态（M3+）
pytest -q apps/server data-service          # 后端与数据层仍是 Python
pnpm --prefix apps/web build
```

## 数据层冻结（2026-10-21 起，M0-5）

`backend/research/`、`backend/alpha/`、`backend/duanxian/` 在 **M3 数据层换代之前冻结**：

- ✅ **可以**：修阻断性 bug（取数失败、算错、崩溃）
- ✅ **可以**：加测试
- ❌ **不可以**：新增数据源、新增指标函数、重构模块结构、改公开函数签名

理由：这三层即将被 `data-service/vendor/a-stock-data`（上游 V3.10.2，我们落后 7 个版本）
整体替换。在即将被丢弃的代码上加功能，等于把工作量扔进垃圾桶，而且会让 M3 的
替换范围变大、对照变难。

判断标准：**「这个改动，vendor 版会不会自带？」** 如果会，就不做，等 M3。

涉及 `research/` 的改动如果有疑问，先看 `docs/research/a-stock-data-v3.10.md`
（上游能力清单），大部分"想加的功能"上游已经有了。

## 环境依赖

| 依赖 | 版本 | 用途 |
|---|---|---|
| Node | ≥ 22.19 | 前端构建与 Pi（Pi 的 engines 要求；**不作为后端运行时**） |
| pnpm | 11.x | 前端包管理 |
| Python | 3.13 | 后端 + 数据层 |
| akshare | ≥ 1.18 | 财务摘要 / 涨停池 / 日线（可选兜底；上游项目已改直连 HTTP） |
| baostock | latest | 估值历史 / 上市退市日 / ST 名单（仅 Python，需安装） |
| xlrd / openpyxl | latest | 读交易所 xls/xlsx（申万行业、社融、国证、两融） |
| `@earendil-works/pi-coding-agent` | 1.3.0 | agent 运行时（Node 子进程） |
| `lightweight-charts` | 5.x | 金融图表 |

> `mootdx` **不从 pyproject 安装**（K 线/盘口/逐笔 2026-09 起失效），且它锁
> `httpx<0.26` 与 `mcp>=1.9` 冲突。vendor 版若需要，放在 data-service 独立 venv。

密钥：只在 `~/.dsh/.credentials.yaml`（`AGNES_API_KEY` 等）。
**不进仓库、不进 workspace、不写日志。**

## Agent 协作约定

**派发 subagent 时显式指定模型，用本地环境实际可用的 provider，不要用默认值。**

本机 `pi --list-models` 里可用的 provider 有 `deepseek` / `magpie`（32 个模型）等。
默认的 `openrouter/z-ai/*` 在本机不可用，指定它会挂住不动、白等十几分钟。

原则：**不要钉死某一个模型**，按任务挑同 provider 下的合适型号 ——
`pi --list-models` 是唯一权威，选当前可用的。

| 任务类型 | 建议 |
|---|---|
| 机械改代码、批量重命名、跟随明确指令 | 轻量快模型（如 `magpie/workbuddy/glm-5.3-flash`） |
| 需要读多文件再判断、写测试、设计取舍 | 强模型（如 `magpie/workbuddy/glm-5.3`） |
| 纯侦察、找文件、梳理调用链 | scout + 轻量模型即可 |

```
agent: worker
model: magpie/workbuddy/glm-5.3     # 具体型号按上表挑，不是固定值
```

判断依据：派发前先跑 `pi --list-models` 确认该模型存在且 provider 可用。

