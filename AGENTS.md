# AGENTS.md — AlphaCopilot

> **当前状态：v2 重构中。** 开工前必读 [`docs/REFACTOR-PLAN.md`](docs/REFACTOR-PLAN.md)
> 与 ADR-0010 ~ ADR-0013。下文描述的是**重构后的目标形态**；重构前的实现细节
> 以 `main` 分支现状和 `docs/adr/0001`–`0009` 为准。
>
> **2026-10-21 修订**：后端保留 Python（不再写 TS）；skills 改为白名单；
> Pi 用项目自持 agent 目录。详见 ADR-0011 §0 与 ADR-0010「修订」。

产品定位：**AI native 的个人本地 A 股低频量化投研工作台**。
确定性计算提供可信数字，agent 提供探索与表达；两者按 provenance 区分（ADR-0012）。

## 结构速记（现状 = 最终形态，ADR-0015 已取消 monorepo 搬迁）

```
frontend/       React 19 + Vite + TS（Lightweight Charts + ECharts）
  pages/        手写页（看板/CRUD）+ PageView（/p/:slug 通用渲染）
  components/page/  BlockRenderer · PageCanvas · ParamBar（ADR-0016）
backend/        Python 3.13 + FastAPI
  api/          session / artifact / view / page / job / SSE / runs / vendor
                emotion_store（emotion_daily 情绪历史表，ROUND2 阶段 1）
  agent/        AgentProvider 契约 + PiProvider
  research/ duanxian/ alpha/   纯函数数据与计算层（不持状态、禁框架依赖）
data-service/   **vendor 运行时宿主**（不是数据服务）：vendor/a-stock-data
                + 独立 venv（vendored mootdx 要 httpx<0.26，与主环境冲突）
  src/loader.py   把 SKILL.md 的 91 个 python 块加载成可调用能力
  src/worker.py   子进程 worker（stdin/stdout JSON 协议）
workspace/      agent 可写区（pi 的 cwd）+ runs/<run_id>/
  .pi/mcp.json  Pi 的项目级 MCP 配置（exposure 必须为 direct）
  .pi-sessions/ Pi session JSONL
skills/         白名单内的 SKILL.md（13 个；不是 88 个全量）
docs/           文档地图见 docs/README.md
  README.md     哪份是活的、哪份是历史（先读这个）
  REFACTOR-PLAN.md  当前计划 M0–M5
  adr/          0001–0016（0001–0008 已被 0009/0010 取代，勿据此实现）
  ROUND2-BRIEF.md · ROUND3-PLAN.md   轮次记录（含诚实清单）
scripts/        vendor-a-stock-data.sh（vendor 同步，只读区靠它更新）
                backfill-emotion.py（情绪历史回填；上游只留 ~28 天）
```

**为什么没有 apps/web + apps/server**（ADR-0015）：monorepo 的收益是多包共享
与独立发版，本项目一个前端一个后端、前后端不同语言（不存在共享代码）、
一起部署——收益为零，代价是全路径改写 + 全部测试重验。

**后端是 Python，不是 TypeScript**（ADR-0011 §0，2026-10-21 修订）。
Pi 走 `--mode rpc` 子进程，这是语言中立边界；不存在跨语言共享类型层，
也没有 `packages/shared`。

**迁移期（M1–M2）目录名保持 `backend/` + `frontend/` 不变**，M3 才搬。

分层职责（四层，不要混）：

- `backend/{research,duanxian,alpha}`：纯函数数据与计算层，**禁加框架依赖**，不持状态。
  其中 `research/astock.py` 是**取数的语义封装层**（`DataUnavailable` / 域名兜底 /
  多源尝试），不是「第二套实现」——见 ADR-0015 决定 1
- `backend/api`：唯一持有产品数据库的角色；唯一与 agent 运行时耦合的角色；
  同进程直接调 `alpha.*` / `research.*`
- `data-service`：**只做 vendor 托管**（SKILL.md + 独立 venv + loader/worker）。
  不承载我们的业务计算。它的存在理由是依赖隔离，不是架构设计（ADR-0015 决定 3）
- `frontend`：只读 API，不读 agent 会话文件

**两套取数入口的分工**（ADR-0015）：
- 页面高频路径 → `research/astock.py`（实测 0.32s/次）
- agent 广度探索 → `/api/v1/invoke` 调 vendor 的 104 个能力
  （实测 0.77s/次：进程 0.01s + vendor load 0.36s + 网络；agent 一轮本身好几秒，可接受）

## 硬规则

1. 从 `main` 拉分支 `feat/<slug>` → squash PR，conventional commits
2. **产品真源在我们的数据库**。agent 的 session 文件是它的内部记忆，前端永不读取；
   `backend/api` 负责把消息与 artifact 落库
3. **agent 不直接写数据库**：写库一律经 `backend/api` 校验（artifact manifest /
   provenance / page spec 白名单）
4. **重活不进 agent 的 turn**：长任务走 job 队列，agent「写代码 → 提交 job → 读结果」
5. **每个 artifact 必须带 provenance**（ADR-0012）：
   `deterministic`（fn + params + dataAsOf）或 `agent`（runId + codeHash + dataAsOf）。
   缺失直接拒收。
   > ✅ **已落地**（M1-7）：`artifact.provenance` 列 + `_validate_provenance` /
   > `_stamp_provenance`；`deterministic` 只能由 `server_stamped=True` 铸造，
   > agent manifest 里声称的 deterministic 一律改写为 `agent` 并记 `claimedKind`。
   > 测试见 `backend/tests/test_provenance.py`。
6. **可信数字的盖章权归服务端**（ADR-0012「已决 1」）。拆成两层，别混：
   - **行为层（建议，非硬约束）**：算回测指标/相关矩阵/因子 IC/敏感性/行情财务数值时，
     agent 应优先调用 `alpha.*` / `research.*`。这只是习惯，**不构成执法**。
   - **展示层（硬约束，可测试）**：`provenance.kind = "deterministic"` 只能由服务端
     调用 `alpha.registry` 铸造。**agent 在 manifest 里写的 provenance 一律不采信**，
     强制改写为 `kind = "agent"`，前端显示 AI 角标。
   - 后果：agent 用 bash 自己手算的数字照样能显示，但**带 AI 角标**，用户知道它不可信。
     这就是本规则的全部效力——不再假装能审计 agent 的代码。
7. **颜色/主题只有一个真源：`frontend/src/theme/tokens.ts`**（ADR-0014）。
   Lightweight Charts、ECharts 都从它读；`index.css` 不再定义颜色。
   （antd 已于 2026-10-23 从依赖中移除：组件全部手写，`antdTheme()` 一并删除。）
   双主题 + 涨跌双口径。**组件里出现 `#` 开头的颜色字面量即违规**；
   **数字一律走 `<Num>` 组件**（等宽 + tabular-nums + 涨跌色），不裸写 `.toFixed()`。
8. 图表分工：K 线/净值/回撤/买卖点 → **Lightweight Charts**；
   热力图/分层/散点/归因 → **ECharts**。**LWC 内多图一律用 pane 分区
   （`addSeries(..., paneIndex)`），不叠加两个 chart 实例**——两个实例会导致
   左右边缘不齐、缩放与十字光标不联动（ADR-0014 §6，实测）。。
   block 必须带 `renderer` 判别符，不能只看 `kind: "chart"`
9. **页面是数据，不是手写 TSX**（ADR-0016）。图表型页面写成 page spec
   （`params` + `blocks[]`），走 `/p/:slug` 通用渲染；加一个分析页**不写 React**。
   agent 只能产 spec，且 `analysis_ref.fn` 必须已在 `alpha.registry` 白名单——
   它无法凭空造取数函数。**不做拖拽编辑器**（span 是固定三列栅格，不是自由坐标）。
   新增 lwc 图表时要同时想清楚「要不要回撤」（`api/page_spec.py` 的 `DRAWDOWN_FNS`）。
10. **agent 拥有完整工具集（含 bash / read / write / edit）**（ADR-0010）。
   这是显式接受的风险，不是疏忽：agent 以 OS 用户权限执行。
   必须有：pi cwd = `workspace/`、`--no-context-files`、session 落 `workspace/.pi-sessions`、
   **`--approve`**（**不要**设 `PI_CODING_AGENT_DIR`，会丢凭据）
   （不加后者，RPC 模式拿不到 project trust → MCP 与 skills 静默不加载，ADR-0010 修订 §1）
11. 不引入实盘/live/channels/qveris/scheduled 相关任何代码。
    **skills 也不得全量恢复**：`qveris` / crypto 系列（`okx-market` `ccxt` `perp-funding-basis`
    `crypto-derivatives` `token-unlock` `stablecoin-flow` `onchain-analysis` `defi-yield`）/
    `shadow-account` / `vnpy-export` / `mootdx` / `tushare` / `yfinance` 一律不迁移。
    白名单见 ADR-0010 修订 §2。
12. LLM 输出合规底线：不荐股、不预测涨跌、不给买卖时机（persona 固化）。
    **这是 prompt 层约束，不是运行时限制**——agent 能力不受限，输出有底线
13. **「图表优先」= 能用图表表达的就不留纯数字**（ROUND2 §9）。孤立数字无法比对，
    必须配历史序列。历史数据在 `emotion_daily` 表（`api/emotion_store.py`）；
    回填用 `scripts/backfill-emotion.py`。
    **东财跌停池只认 `sort=fund:asc`** —— 其余排序返回空数组而不报错，会静默写成
    「这天 0 跌停」（实测 10-21：默认 0 条、`fund:asc` 5 条）。
    上游涨停池只保留约 28 天历史，amcharts/akshare 同源同限制。
    **`range` 参数必须走 `alpha/data.py: closes_for_range()`** —— 直接写
    `{"3m":63,"6m":126,"1y":250}.get(range, 250)` 会让 ISO 日期被静默忽略
    （用户选 2024 却拿到最近 250 天）。前端 date_range 预设也只能给后端认的
    3m/6m/1y，否则就是 UI 撒谎（选 2y 直接 400）。
14. **破坏性操作必须可撤销，不能靠「应该能重新生成」自我说服**（ROUND2 §10.1 事故）。
    用户手写的页面 / 笔记 / 组合**都不是可再生资源**。删除一律软删 + 撤销入口；
    只给确认弹窗不够（弹窗防手滑，防不了「确认了才发现想错了」）。
    实际事故：`PageRepo` 曾是硬 DELETE、前端无确认，一个自定义页被删后
    SQLite 页面重用、无法恢复。
15. **markdown 只有一个引擎：`react-markdown` + `remark-gfm`**（ROUND3）。
    agent 对话（`components/agent/ChatMessage`）与研报（`MyReports`）共用它。
    **不要**再手写第二套解析器 —— 两套并存必然导致同一个回答在两处长不一样，
    而手写版通常还不支持嵌套列表/引用/斜体。想加渲染能力就写
    `components` 映射，不要另起炉灶。

16. **Agent 栏是浮窗，不是常驻右栏**（ROUND3 C2）。它不参与布局流 ——
    `data-region="agent"` 不该存在于 Layout 里，否则又会吃掉一列宽度
    （这正是 ROUND2-C1 修掉的问题）。位置/尺寸/吸附在 `AgentWindow`，
    浮层本身在 `AiConsole`，Layout 只负责渲染 `<AiConsole />`。

17. **派发 subagent 不得使用 `commandcode-plan/*claude*` 系列模型**（成本过高，
    额度已接近耗尽）。可用：`magpie/commandcode-plan/z-ai/glm-5.3-flash`、
    `magpie/commandcode-plan/zai-org/GLM-5.3`、`magpie/commandcode-plan/gpt-5.6-*`、
    `deepseek/deepseek-flash` 等。`pi --list-models` 是唯一权威，但**先看清价格档位**。
    正在运行的 claude 系 subagent 应立即替换（`.pi/` 与 `subagents_list` 可查）

## 反模式（重构中必须避免）

- ❌ 给页面加「问 AI」占位按钮（旧 `AskAiButton`/`DeepDive` 已删）
- ❌ 用 `glass` / `shadow-glow` / 渐变 / `rounded-2xl` 表达层次
- ❌ 让 agent 生成前端代码或直接改 DOM（它只能产 View / artifact）
- ❌ 图表型页面又写手写 TSX（该写 page spec，见 ADR-0016）
- ❌ 给 Pi 传 baseURL/apiKey 并假装它生效（被忽略，见 `agent/provider.py:81`）
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
- ❌ 把 88 个 skills 一次性拷进 `skills/`（白名单，见硬规则 11）
- ❌ 只用当天快照做「趋势」判断（没有历史序列就没有趋势，见硬规则 13）
- ❌ 手写第二套 markdown 解析器（见硬规则 15）
- ❌ 把 Agent 栏做成布局内的常驻右栏（见硬规则 16）
- ❌ 硬删除用户数据 / 只给确认弹窗不给撤销（见硬规则 14）

## 命令

```bash
# 后端 + 数据与计算层（Python）
cd backend && python3 -m pytest -q          # 523 passed
cd backend && ruff check .

# 前端（TS）
cd frontend && npx tsc --noEmit && npx vitest --run && npx vite build   # 350 passed

# vendor（独立 venv，M3-V1）
cd data-service && .venv/bin/python -m pytest tests -q                 # 19 passed
cd data-service && .venv/bin/python -m pytest vendor/a-stock-data/tests -q   # 上游 179 条

# vendor 同步（唯一合法的更新方式，vendor/ 是只读区）
./scripts/vendor-a-stock-data.sh            # 加 DRY_RUN=1 只演练
```

**顺序说明**：先跑 backend 再跑 frontend —— 后端改动（API 契约）会让前端 tsc
先红，反过来不会。

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

