# AlphaCopilot v2 重构方案（REFACTOR PLAN）

> 决策依据：ADR-0010（agent→pi）、ADR-0011（前端 TS + 后端/数据 Python）、
> ADR-0012（双轨产物）、ADR-0013（UI 设计系统 v1）、**ADR-0014（UI 设计系统 v2，取代 0013 §1–3）**
> 编写：2026-10-20 · 修订：**2026-10-21** · 基准 commit：`84198c5`（main）
>
> **2026-10-22 进度快照**：M0 ✅ M1 ✅ M2 ✅（11/11）·
> M3 部分完成（1/2/3/4 后端、V1/V2/V3）· M4-1 ✅ · M5-4/M5-5 ✅。
> 未做：M3-5 monorepo 搬迁、M3-4 的 Rerun、M3-V4/V5/V6/V7、
> M4-2~M4-5、M5-1~M5-3。**vendor 已可加载（101 个函数），但尚未接进 REST**。
>
> **2026-10-21 修订要点**（重要，先看这个）：
> 1. **应用后端保留 Python**，不做 TS 重写（ADR-0011 §0）——M1/M3 任务表已同步
> 2. **vendor a-stock-data 从 M0 移到 M3**（M0 只做真止血；依赖与主环境冲突）
> 3. **M1-3 新增**：Pi 运行环境（`--approve` + 项目 `.pi/mcp.json`），
>    否则 MCP/skills 静默不加载（ADR-0010 修订 §1，已按实测修正）
> 4. **M1-9 skills 白名单**：源是 HKUDS/Vibe-Trading 的 90 个（实测 description
>    18,330 字符 ≈ 6.1k tokens/轮）。**选 12 个 ≈ 700 tokens**，剔除 15 个硬规则 10
>    禁止项，取数指引改到 `alpha.data`（ADR-0010 修订 §2）
> 5. **M1-7 补上 provenance 落地 + 盖章权**（ADR-0012 的硬规则目前无任何实现）：
>    agent 交来的 provenance 一律不采信，`deterministic` 只能服务端铸造
> 6. **M1-6 补 `sandbox.py` → `runner.py` 重新定位**（ADR-0012「已决 2」：
>    它不是安全边界，是带留档的执行通道）
> 7. **M2-5 新增 block 的 `renderer` 判别符**（ADR-0012 ECharts 契约 vs ADR-0013 LWC 冲突）
> 8. 更正实测数字：`AskAiButton` 14 处/7 文件（非 6 处）；vibe 28 行（非 76）；
>    页面 11 个（非 8）；`stockPool` 并非死方法

---

## 0. 一句话目标

把 AlphaCopilot 从「Python 后端 + dsh（已坏）+ 玻璃拟态 UI」
重构为 **「Python 后端 + TS 前端 + Pi agent（完整能力）+ 交易终端风 UI + 双轨产物」** 的
AI native 个人投研量化工作台。

---

## 1. 起点诊断（实测，2026-10-20）

| 项 | 状态 |
|---|---|
| 前端构建 | ✅ `vite build` 通过；`tsc --noEmit` 0 错误 |
| 前端测试 | ✅ 60 passed / 4 个文件（**页面组件 0 测试**） |
| 后端测试 | ❌ **153 passed / 8 failed**（8 个全是 AI 链路） |
| 后端 lint | ❌ ruff 50 个问题（36 个可自动修） |
| AI 对话 | ❌ 500（`ModuleNotFoundError: deepseek_harness`） |
| `/openapi.json` | ❌ 500（`BacktestIn` ForwardRef） |
| 确定性数据端点 | ✅ 20+ 个全部 200（茅台 1331.88、涨停 54 家、美债 4.77%） |
| CI | ❌ 无（`.github` 已删） |

**核心判断**：确定性的那一层是健康的；AI 那一层是断的，且断了没人知道
（因为唯一覆盖它的 8 个测试正好红着，且无 CI）。

---

## 2. 目标架构

> **2026-10-21 修订**：应用后端保留 **Python**（ADR-0011 §0）。后端与数据层
> **同进程**，不再有 `MarketDataPort` / 数据服务 HTTP 那一跳。

```
┌─────────────────────────────────────────────────────────────┐
│ apps/web         React 19 + Vite 6 + TS                        │
│                  Lightweight Charts（K线/净值/回撤）             │
│                  ECharts（热力图/分层/散点）                     │
│                  block 渲染器 ×4（带 renderer 判别符）           │
│                  + AI 角标 + Pin                               │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTP + SSE
┌────────────────────▼────────────────────────────────────────┐
│ apps/server      Python 3.13 + FastAPI（**原地保留，不重写**）   │
│                  · session / message / artifact / view / page   │
│                  · job 队列（回测等长任务）                      │
│                  · SSE 事件流（中立事件）                        │
│                  · Store（SQLite，唯一产品真源）                   │
│                  · alpha.* / research.* 直接调用（同进程）         │
└──────────┬──────────────────────────────────────────────────┘
           │ JSONL over stdio（语言中立边界）
┌──────────▼──────────────────────────────────┐
│ Pi agent 常驻子进程（Node 22，外部依赖）        │
│ @earendil-works/pi-coding-agent 1.3.0        │
│ 完整工具集（含 bash）· skills · MCP · abort    │
│ cwd = workspace/                             │
│ MCP 配置 = workspace/.pi/mcp.json（exposure=direct）│
└─────────────────────────────────────────────┘
```

**M3 后才搬目录**（本图用目标名；M1–M2 仍是 `backend/` + `frontend/`）：

---

## 3. 里程碑（M0–M5）

### M0 — 止血与可信度（3–4 天）

**目标**：让「测试全绿」变成真的，让 AI 不可用这件事以后再也不会被忽略。

| ID | 任务 | 验收 |
|---|---|---|
| M0-1 | 加回 CI（GitHub Actions）：`pytest` + `tsc` + `vitest` + `build` + `ruff`。**runner 必须 `macos-latest`**（`test_runner.py`（原 `test_sandbox.py`）与两个 E2E 在非 darwin 上 `skipif`，ubuntu 上等于不跑） | PR 上能看到 red/green；CI 汇总行显示 skip 数 |
| M0-2 | 8 个红测试标记 `xfail(strict=True, reason="M1 换 Pi 后重写")`，**同 PR 加门禁：xfail 数不得增加** | `pytest` 全绿；xfail 数写进 CI summary 且被断言 |
| M0-3 | 修 `/openapi.json` 500：`api/app.py:114` 的 `class BacktestIn` 在函数内定义 → 挪到模块级 | `curl /openapi.json` 返回 200，且含 `/backtest` |
| M0-4 | `ruff check .` 清零（36 个 `--fix`，14 个手工） | ruff exit 0 |
| M0-5 | **冻结旧数据层**：只修阻断性 bug，不再加功能（即将被 vendor 版替代） | 约定写入 AGENTS |
| M0-6 | 前端删死代码：`AskAiButton`（**14 处 / 7 个文件**）/ `DeepDive`（11 处）/ `Placeholder` / `SaveNoteButton` / `lib/notes.ts`；`lib/api.ts` 里 `portfolio`（后端是 `/portfolios`）与 `myreports`（后端是 `/reports`）两组错路径 | `grep -rn "AskAiButton" frontend/src` 为空 |
| M0-7 | 清 **28 行** vibe 痕迹（注释/文案）；`vibe` 全仓另有 docs/archive 里的历史记录，不动 | `grep -ri vibe frontend/src backend --include=*.ts* --include=*.py` 为空 |
| M0-8 | `docs/TASKS.md` 重编号（T41–T48 各出现 2 次），且顶部标注「v2 期间以 REFACTOR-PLAN 为准」 | 编号唯一 |

**为什么不是 M1 先做**：换 agent 的过程中你会反复跑测试。如果基线是红的，
你无法区分「我改坏了」和「本来就坏」。

> **2026-10-21 修订**：原 M0-5b（vendor a-stock-data，2–3 天）**移到 M3**。
> 理由：M0 的目标是「止血」，而 vendor 在 M3-7 之前对用户**零可见收益**
> （端点仍走旧 `astock.py`）；且它需要 `baostock`/`xlrd`/`openpyxl`，
> 而 `mootdx` 锁 `httpx<0.26`、本仓库 `mcp>=1.9` 要 `httpx>=0.27`，
> 在同一环境里装必然冲突。vendor 与 data-service 独立 venv 一起进 M3。

---

### M1 — 换 Agent（4–6 天）

**目标**：AI 真正可用，且能中断、能执行、能产 artifact、**重启后还记得**。

| ID | 任务 | 验收 |
|---|---|---|
| M1-1 | **先写测试**：`PiProvider` 契约测试（假 pi 进程，无需真实模型），覆盖 5 类中立事件 | **已完成**：7 条红 → 绿，1.3s；变异测试 6 个注入 bug 全部被抓住 |
| M1-2 | PiProvider 实现：`backend/agent/providers/pi.py`（RPC client）。事件映射逐字段对齐 `message_update.assistantMessageEvent.text_delta.delta` / `tool_execution_start\|end` / `agent_settled.aborted` | **已完成**：真 pi + 真模型端到端跑通；11 条测试（含 4 条配置契约） |
| M1-3 | **Pi 运行环境就位**（ADR-0010 修订 §1，**已实现**）：`agent/pi_env.py` 生成 `<workspace>/.pi/mcp.json`（`exposure: "direct"`），`--approve` 启用项目信任，不设 `PI_CODING_AGENT_DIR` | 已验：真 pi + 真模型下模型自主调 `mcp__alphacopilot__get_quote` 拿到茅台 1313.29 |
| M1-4 | abort 能力（契约 + provider + HTTP 端点） | **已完成**（后端）；真 pi 验证：中止→`finish_reason=aborted`→进程存活→下一轮正常。前端按钮接通留 M2-7 |
| M1-5 | **会话续接** | **已完成**：`ProviderSpec.session_id` + `--session-id` + store 落库。真实链路连跑 3 次 PASS（记「紫金铜锣」→ 重启服务 → 答对）；顺带修了「关服务时 turn 还在跑 → 写已关闭的库」 |
| M1-6 | 删 dsh 全部痕迹 + `sandbox.py` → `runner.py` 重新定位 | **已完成**：`grep dsh` 仅剩历史说明；**8 条 xfail 全部转绿**（mock 端点手法失效 → 改为注入假 provider）；`XFAIL_BUDGET` 8→0；全量 258s→8.7s |
| M1-7 | **provenance 落地 + 盖章权** | **已完成**：`artifact.provenance` 列 + 校验拒收缺失 + **agent 交来的声明一律降级为 `agent` 并记 `claimedKind`**，deterministic 只能服务端铸造（job 走 `server_stamped=True`）。10 条测试，变异 5/5 变红 |
| M1-8 | job 事件流接通 | **已完成**：补 `job/completed`（带 artifact_ids）与 `job/failed`，都发到**会话**流（用户盯对话不是 job id）。前端能渲染 job 结果 |
| M1-9 | **skills 白名单**（ADR-0010 修订 §2） | **已完成**：源是 HKUDS/Vibe-Trading 的 90 个（实测 6.1k tokens），**选 12 个**（约 700 tokens）；剔除 15 个硬规则 10 禁止项；取数指引改到 `alpha.data`。18 条守门测试 |
| M1-10 | 页面感知 | **已完成**：8 页登记真实快照（LimitUpStats 由 DailyReview 内嵌不重复登记，Settings 不需要）。**顺带补 `ai-page` 基础设施 7 条测试**（此前零覆盖），4 个变异全红 |

**M1 的 DoD**：一句话说「分析白酒四家和沪深300 近一年相关性」→ 对话流出图 →
点 Pin → 图进页面 → 刷新还在 → 杀掉 pi 进程重问，它还记得上文。

---

### M2 — UI 换皮（5–7 天）

> **2026-10-21 重写**：M2 原任务表是照 ADR-0013 写的，但 ADR-0013 只有方向没有手段，
> 实际做了 4 版原型才收敛。现以 **ADR-0014** 为准重写本表，并把原型里已验证的实现
> 直接搬进来（原型在 `frontend/src/pages/__proto__/`，是 throwaway，不并入 main）。

| ID | 任务 | 验收 |
|---|---|---|
| ID | 任务 | 状态 | 验收 | |
|---|---|---|---|---|
| **M2-0** | **文档先行**（ADR-0014 + 本表 + AGENTS 硬规则 7/8 修订） | ✅ | 三处表述一致 | |
| **M2-1** | `theme/tokens.ts` 落地：深浅两套 Palette + antd token + 字体/间距/字号 | ✅ | 颜色字面量只在 tokens.ts | |
| **M2-2** | 迁 `index.css`：旧 HSL token 值 → 新 palette；删 glass/glow/渐变/大圆角 | ✅ | 守门 grep 为空 | |
| **M2-3** | `chart-theme.ts` 改为从 tokens 读，LWC 与 ECharts 同源 | ✅ | 7 条测试 + 3 变异 | |
| **M2-4** | `Num` 组件 + 自托管字体（Inter Variable / JetBrains Mono） | ✅ | 16 条测试 + 4 变异 | |
| **M2-5** | 三区布局：左导航 176/52 + 顶栏 48 + 主画布 + Agent 栏 360/44 + 底栏 28 | ✅ | 9 条测试 + 4 变异 | |
| **M2-6** | **单 chart 多 pane**：K线+成交量、净值+回撤各一个实例 | ✅ | canvas 左坐标实测相等 | |
| **M2-7** | `renderer: "lwc" \| "echarts"` 判别符 + fn 映射白名单 | ✅ | 9 条测试 + 5 变异 | |
| **M2-8** | 10 个页面按新 token 重排 | ✅ | 7 页截图核对 | |
| **M2-9** | 涨跌双口径 + localStorage 持久化 | ✅ | 15 条测试 + 变异 | |
| **M2-10** | LWC v5 skill 纳入白名单 | ✅ | RPC 实测 13 个 skill 加载 | |

**M2 完成状态：11/11 ✅（2026-10-21）**

**M2 的 DoD**：`grep` 三连为空（glass/glow、颜色字面量、`toFixed` 裸渲染）；
双主题 + 双口径切换无样式漂移；K 线与成交量左右严格对齐且缩放联动；
10 个页面视觉一致。

**DoD 实测结果**（2026-10-21）：
- 守门测试 7 条全绿：旧视觉残留 / 颜色字面量 / 裸 `toFixed` / 单文件单
  `createChart` / 建实例 effect 不依赖 palette / 带符号数字不套固定语义色 /
  页面不给 ECharts 传 legend
- K 线双 pane：canvas 左坐标 217 == 217，宽 914 == 914；净值双 pane：217/928 一致
- 双口径：`html.caliber-intl` 派生 `--danger/--success`，45 处调用点零改动；
  **UI 语义色（操作成功/失败）不随口径翻转**（拆成 danger/success 两个概念）
- 前端 154 passed / 后端 258 passed

**已验证的实现参考**（原型 v4，可直接抄结构，不要抄代码）：
- `frontend/src/pages/__proto__/ProtoApp.tsx` —— 三区布局 + 可折叠 Agent 栏 + 单 chart 双 pane
- `frontend/src/theme/tokens.ts` —— Palette 结构 + antd token 映射

### M3 — 对象化 + 数据层换代（2–4 周）

> **2026-10-21 修订**：后端不重写（ADR-0011 §0），M3 不再包含「重写 2600 行
> 为 TS」这一隐藏大头；但原 M0-5b 的 vendor 全套（2–3 天）回到这里，
> 且 monorepo 搬迁是纯搬目录。

| ID | 任务 | 状态 | 验收 | |
|---|---|---|---|---|
| M3-1 | `Run` registry（参数 + codeHash + dataAsOf + 指标 + artifacts） | ✅ | 每次回测可比较、可复现 | |
| M3-2 | `Universe` as query（不是 localStorage 代码串） | ✅ | 改条件重算；数据变了自动更新 | |
| M3-3 | `View` / `Page` 模型（ADR-0012） | ✅ 后端 + 页面 | 页面 = 保存的 View 集合 | |
| M3-4 | Pin / Rerun / Diff 交互 | ⚠️ Diff+Pin 已做，**Rerun 未做** | 两个 Run 可对比差异 | |
| M3-5 ⬜ | 迁移到 monorepo 布局（`apps/web` + `apps/server` + `data-service`）。**纯目录搬迁**，同时修所有 `Path(__file__).parents[N]` 与 `sys.path.insert` | `git log --follow` 仍可追溯；`pytest` 与 `vite build` 均绿 |
| **M3-V1** ✅ | **data-service 独立 venv**（vendor 依赖 `baostock`/`xlrd`/`openpyxl` 与主环境 `mcp>=1.9`→`httpx>=0.27`、`mootdx`→`httpx<0.26` 冲突，必须环境隔离）；**`mootdx` 不装**（ADR-0011 事实 1：连财务也拿不到） | vendor 测试能在独立 venv 里跑；主环境不需装 `mootdx` |
| **M3-V2** ✅ | Vendor `SKILL.md`（V3.10.2 / commit `29b07d2e3700`）+ `LICENSE` + `CHANGELOG.md` + `tests/` + `NOTICE` 到 `data-service/vendor/a-stock-data/`，**按 [`research/a-stock-data-v3.10.md` §7.1](research/a-stock-data-v3.10.md) 的 curl 命令钉死 commit** | `SKILL.md` 7585 行 / 91 个 python 块 / sha256 记入 NOTICE |
| **M3-V3** ✅ | 写 loader（骨架见 [§7.4](research/a-stock-data-v3.10.md)）：抽 91 块 → AST 去示例调用 → 同 namespace exec | `list_capabilities()` 列出 87 个端点；182 定义 / 181 唯一名 |
| **M3-V4** ⬜ | 跑上游 `tests/`（179 条离线测试，从 SKILL.md 抽代码执行） | 179 条全绿，不联网 |
| **M3-V5** ⬜ | 两层暴露：agent 走 `/v1/capabilities` + `/v1/invoke`（87 个），页面继续走现有 curated 端点，**不重复实现「第二套 REST」** | agent 能调任意 vendor 端点；页面无回归 |
| **M3-V6** ⬜ | `scripts/vendor-a-stock-data.sh`：下载 → 跑测试 → 绿则更新 NOTICE，红则回滚；**`vendor/` 目录只读约定**（CI 校验无本地改动） | 一条命令完成同步；CI 里 `git diff --exit-code vendor/` 绿 |
| M3-7 ⬜ | 删除旧移植 `backend/research/astock.py`（被 vendor 替代） | `grep -r "移植自 a-stock-data"` 为空 |

---

### M4 — 量化深度（2–3 周）

调研结论（成熟项目的分水岭）：

| 项目 | 值得抄的 |
|---|---|
| Qlib | 配置驱动工作流、PIT 数据库、因子表达式引擎 |
| vectorbt | 向量化参数扫描（1 万组合出热力图）、walk-forward |
| Alphalens | 因子分析标准报告（IC/分层/换手/衰减） |
| QuantStats | tear sheet 标准（滚动 Sharpe、月度热力图、暴露） |
| WorldQuant BRAIN | alpha 表达式 + 即时模拟 |
| NautilusTrader | 回测与实盘同一套代码（我们不做实盘，只取「回测即代码」） |

| ID | 任务 | 验收 |
|---|---|---|
| M4-1 ✅ | Factor lab：IC / RankIC / ICIR / 衰减 / 分位数收益 / 换手 | 因子页能回答「这个信号有没有用」 |
| M4-2 ⬜ | Tear sheet 标准化（滚动 Sharpe、月度热力图、回撤持续期、暴露） | 每份回测都有标准报告 |
| M4-3 ⬜ | 参数扫描 + 热力图（vectorbt 式） | 一次跑 100+ 参数组合 |
| M4-4 ⬜ | Walk-forward / 样本外 | 防止「参数扫出来的漂亮曲线」 |
| M4-5 ⬜ | 归因（Brinson + 因子归因） | 收益拆解到行业/因子 |

---

### M5 — AI native 打磨（持续）

| ID | 任务 | 验收 |
|---|---|---|
| M5-1 ⬜ | 命令栏（⌘K）自然语言入口 | 输入「把这三个票和沪深300 做 60 日滚动相关」直接出图 |
| M5-2 ⬜ | Build 模式：agent 产出 View 草稿 → 预览 → 确认落地 | 一句话产出新 View 并保存 |
| M5-3 ⬜ | 研究线（Note → Run → View → 复盘 Note） | 半年后能回答「我当时为什么买、后来对了吗」 |
| M5-4 ✅ | 数据 as-of 全站可见 + 跨日失效 | 早上打开看到的数字带时间戳 |
| M5-5 ✅ | 缓存加 TTL | 不会静默用昨天的数据 |

---

## 4. 关键技术决策摘要

| 决策 | 选择 | 为什么 |
|---|---|---|
| Agent 运行时 | **Pi SDK 1.3.0（RPC 子进程）** | MIT 稳版；skills/MCP/abort 齐全；用户熟悉 |
| Agent 能力 | **完整（含 bash）** | 用户明确；个人本机、无交易、可接受风险 |
| 应用后端 | **Python + FastAPI（原地保留）** | RPC 已是语言中立边界，重写无收益；省 2–3 周（ADR-0011 §0） |
| 数据层 | **Python 原地保留（同进程）** | pandas/baostock 无 TS 等价物；回测引擎是 A 股规则沉淀；全量 vendor a-stock-data |
| 图表 | **Lightweight Charts + ECharts** | TradingView 观感 + 复杂图形表达力；block 带 `renderer` 判别符 |
| 页面模型 | **View 集合（可 Pin AI 产出）** | AI native；可撤销；可版本化 |
| 数字来源 | **只来自确定性函数** | 数字错一次，产品可信度归零；**但 bash 路径下不可验证**，见 §5 风险 |
| 安全模型 | **接受 OS 级权限，配置层降低风险** | 见 ADR-0010 §3 |
| skills | **白名单 30 个，不全量恢复** | 88 个 description ≈ 5.9k tokens/轮；含硬规则 10 禁止项（ADR-0010 修订 §2） |
| Pi 配置 | **项目 `.pi/mcp.json` + `--approve`** | RPC 无法弹 project trust；且 `exposure` 必须 `direct`，否则工具不声明给模型（ADR-0010 修订 §1） |

---

## 5. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| **agent 有 bash = OS 级权限** | 可读写本机任意文件、可外发数据，包括 `~/.dsh/.credentials.yaml` | ADR-0010 显式记录；cwd 限 `workspace/`；`--no-context-files`；session 就地；可回滚 |
| ~~配置静默失效~~ | 已解决 | M1-3 已实现并实测：`--approve` + `exposure: "direct"`。反例已验证（去掉 approve 或改回 codemode，工具就消失） |
| ~~“数字只来自确定性函数”在 bash 路径下不可验证~~ | 已消失 | **已决 1**：执法点移到产物落库那刻——盖章权归服务端，agent 无权自称 deterministic，手算的数字必带 AI 角标（ADR-0012）。规则变得可测试 |
| **provider 重启 → agent 记忆断链** | 前端看到历史，agent 不记得；`_ensure_runtime` 现成行为 | M1-5 必验：杀掉 pi 子进程后用 `switch_session`/重建上下文续上；或明确约定「重启=新会话」并告知用户 |
| **图表两套库画同一个东西** | K 线用 ECharts option 还是 LWC？ADR-0012 与 ADR-0013 冲突 | M2-5：block 增加 `renderer` 判别符 |
| **skills 全量恢复违反硬规则 10 + 5.9k tokens/轮常驻** | 合规破洞 + 每轮成本 | 白名单三档，A 档约 30 个（ADR-0010 修订 §2） |
| vendor 依赖与主环境冲突 | `mootdx` 锁 `httpx<0.26` vs `mcp>=1.9` 要 `>=0.27` | M3-V1：data-service 独立 venv；**不装 mootdx** |
| Pi 是 Node 程序，需 Node 22.19+ | 部署多一个运行时 | 外部依赖，与我们代码无关；启动时前置检查 |
| JSONL 桥接自写 | 事件映射 bug（字段名弄错不报错，只是事件丢） | M1-1 契约测试先红、逐字段断言；M1-2 实现 |
| 数据源变更（东财/腾讯改接口） | 页面降级 | vendor 上游修复（约每周一次），同步脚本一条命令；保留 available/reason 降级 |
| ~~60 分钟线不可用~~ | 已解决 | 腾讯 `mkline`；注意科创板量纲与 320 根上限 |
| ~~全栈重写期间两套代码并存~~ | 已消失 | 后端不重写（ADR-0011 §0）；M3 只搬目录 |
| 工期失控 | — | 每个 M 有独立 DoD，可停在任何里程碑 |

---

## 6. 数据源现状（实测结论，供 M4/M5 参考）

| 能力 | 源 | 状态 |
|---|---|---|
| A 股实时行情 | 腾讯 gtimg | ✅ 0.34s |
| A 股日/周/月 K 线 | 腾讯 gtimg（mootdx 兜底已死） | ✅ 0.73s |
| A 股 1/5/15/30/60 分钟线 | 腾讯 `mkline`（`ifzq.gtimg.cn`） | ✅ 实测可用；科创板量纲是股、单次 ≤320 根 |
| 财务摘要（营收/净利/ROE/毛利率） | akshare 同花顺 | ✅ 0.66s |
| 利润表（有效税率推导） | akshare 东财 | ✅ 8.3s |
| 估值与一致预期 | 腾讯 + akshare | ✅ 1.2s |
| 涨停/炸板/跌停池 | 东财 push2ex + akshare | ✅ 0.3–5.7s |
| 板块资金 / 成交额榜 | 东财 clist | ✅ 2.1s |
| 海外指数 + 七姐妹 | 腾讯 gtimg | ✅ 0.16s |
| 美债收益率曲线 | 美国财政部 CSV | ✅ 1.0s |
| 大宗商品 / 汇率 | 腾讯 gtimg | ✅ 0.15s |
| 加密（BTC） | 无免费源 | ❌ 降级 |
| 资讯雷达（108 个 RSS） | 公开 RSS | ✅ |
| 公告 / 新闻 / 个股信息 | akshare | ❌ 三个接口已坏（正则转义 / 代理拦截 / 结构变更）——a-stock-data 直连 HTTP 可替代 |

---

## 7. 开工顺序（给新会话的第一个任务）

```
M0-1 加 CI（macos runner）  ← 先做，否则后面全是裸奔
M0-2 xfail 8 个 + xfail 门禁
M0-3 openapi 500（2 行：BacktestIn 挪模块级）
M0-4 ruff 清零
M0-5 数据层冻结（写入 AGENTS）
M0-6/7 前端死代码 + vibe 痕迹（28 行）
M0-8 TASKS.md 重编号
   ↓  ← 到此为止就是「止血」，3–4 天，交付一个全绿的基线
M1-1 PiProvider 契约测试（先红，假 pi 进程）
M1-2 PiProvider 实现 + 事件映射
M1-3 Pi 运行环境（.pi/mcp.json + --approve）← 已完成，真模型验过
M1-4 abort → M1-5 会话续接 → M1-6 删 dsh + runner.py 重新定位（8 条测试转真绿）
M1-7 provenance 落地 + 盖章权 ← 新规则第一次真正生效
M1-8 job 订阅 / M1-9 skills 白名单 / M1-10 页面感知
   ↓
M2（换皮）→ M3（对象化 + vendor）→ M4（量化深度）→ M5（打磨）
```

**M0 全部做完之前不要碰 M1 的功能开发**——理由见 M0 的说明。

**M1-3 是新增的关键路径**：不做它，agent 起来看不到 MCP 工具和 skills，
而这件事**不会红任何测试**，只会在 E2E 时表现为「AI 怎么这么笨」。

---

## 附：本次重构不做什么

- ❌ 不做实盘下单 / 盯盘（原边界，继续有效）
- ❌ 不做多智能体辩论 / 分析师团队（原边界，继续有效）
- ❌ 不做多用户 / 权限 / SaaS（单人本机）
- ❌ 不追求「AI 任意生成前端代码」（只生成 View）
- ~~❌ 不为 60 分钟线找替代源~~ → **已推翻**：腾讯 `mkline` 可用（见 ADR-0011 事实 1）
- ❌ 不迁移 dsh 的 profile 配置（整条链路废弃）
- ❌ 不把后端重写成 TypeScript（2026-10-21 新增，见 ADR-0011 §0）
- ❌ 不恢复 88 个 skills 全量（白名单 30 个，ADR-0010 修订 §2）
- ❌ 不为 vendor 单独造第二套 REST（页面走现有 curated，agent 走 `/v1/invoke`）
- ❌ 不审计 agent 的 bash 命令来验证「数字来自库函数」（语义判断，写不成规则；
  改用服务端盖章权，ADR-0012 已决 1）
- ❌ 不删 `runner.py`（原 `sandbox.py`）——留档 `run_id`/`code.py` 是 provenance 的抓手，
  但也不再吹它是安全边界（已决 2）

---

## 附二：文档索引（新会话从这里开始）

| 文档 | 内容 |
|---|---|
| [`docs/adr/0009`](adr/0009-v2-ai-native-pivot.md) | **总纲**：v2 转向 AI native，取代 ADR-0008 的哪几条、继承哪几条 |
| [`docs/adr/0010`](adr/0010-agent-runtime-pi-full-capability.md) | Agent 运行时 → Pi SDK；完整能力（含 bash）；**安全风险显式记录** |
| [`docs/adr/0011`](adr/0011-typescript-migration-python-data-service.md) | **前端 TS + 后端/数据 Python**（§0 已修订，后端不重写）；数据源实测结论 |
| [`docs/adr/0012`](adr/0012-dual-track-artifacts.md) | 双轨产物（deterministic vs agent）、provenance、View/Page 模型；**已决 1：盖章权归服务端**、**已决 2：runner.py 重新定位** |
| [`docs/adr/0013`](adr/0013-ui-design-system.md) | UI 设计系统 v1：token、双主题、涨跌双口径、图表分工 |
| [`AGENTS.md`](../AGENTS.md) | 硬规则（已按 v2 重写）+ 反模式清单 |
| [`docs/research/a-stock-data-v3.10.md`](research/a-stock-data-v3.10.md) | 数据层供体调研：上游 V3.10.2 现状、我们落后的 7 个版本、可直接借用的能力 |
| 本文件 | M0–M5 任务分解 + 风险对策 + 数据源现状 |

**开工顺序**：M0（止血）→ M1（换 agent）→ M2（换皮）→ M3（对象化 + vendor）→ M4（深度）→ M5（打磨）。

**第一个任务**：`M0-1 加回 CI`。理由：基线现在是 153 passed / 8 failed，
在红基线上做重构无法区分「我改坏了」和「本来就坏」。

**M0 的实际预算**：5 项任务，3–4 天，交付一个「全绿 + CI 看得见」的基线。
vendor（原 M0-5b，2–3 天）不在其中——它对用户零可见收益，且依赖与主环境冲突。
