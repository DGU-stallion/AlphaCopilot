# ADR-0011 — 前端迁移 TypeScript，后端与数据层保留 Python
>
> 原题（2026-10-20）：《前后端迁移 TypeScript，Python 降为内部数据服务》。
> 2026-10-21 修订后后端不再重写，题名同步修正，文件名保持不变以保留链接。

**状态**：已决定（**2026-10-21 修订：后端保留 Python，TS 只到前端**——见 §0）
**日期**：2026-10-20 · 修订 2026-10-21
**补充**：ADR-0003（统一后端 A 股数据为主）、ADR-0006 决策 1（应用自持前后端）
**取代**：ADR-0008 中「AI 只解释」的约束（由 ADR-0010 取代）；其余继续有效

---

## 0. 修订（2026-10-21）：后端不做 TS 重写

**原决定 §1/§4/影响 里「`backend/api/*` + `agent/*` + `mcpserver/*`（约 2600 行 / 43 个端点）
用 TypeScript 重写」被撤销。**

**理由**：原论据是「与 Pi 同语言」。但 ADR-0010 选的接入形态是
`pi --mode rpc` 子进程 + JSONL over stdio——**这本身就是语言中立边界**（官方文档
自带 Python 最小客户端示例）。一旦走 RPC，「同语言」这个理由就自动失效；
而按原方案，`PiProvider` 要在 M1 写一遍 Python、M3 再扔掉写一遍 TS，
同一个模块两次实现、同一套接口——违反「两个 adapter 才算真 seam」。

**修订后的分层**：

| 层 | 语言 | 位置 |
|---|---|---|
| 前端 | TypeScript | `frontend/`（M3 后 `apps/web`） |
| 应用后端 + agent 适配 | **Python**（原地保留） | `backend/`（M3 后 `apps/server`） |
| 数据 / 计算 | Python | `backend/{research,duanxian,alpha}`（M3 后 `data-service`） |
| Agent 运行时 | Node（外部子进程） | `@earendil-works/pi-coding-agent` |

**保留自原决定的部分**（这些与语言无关，继续有效）：

1. **Python 不持有应用状态**、不调 Node、单向依赖（§2 硬规则 1–2）
2. **响应带 `asOf`**（§2 硬规则 4）
3. **数据层先清理再暴露**；全量 vendor a-stock-data（§3，见
   [`docs/research/a-stock-data-v3.10.md`](../research/a-stock-data-v3.10.md) 与
   REFACTOR-PLAN M3-V1～M3-V6）
4. **分阶段搬迁**：M1–M2 保持 `backend/` + `frontend/` 目录名，M3 才搬目录（§4）
5. `MarketDataPort` **不再需要**——同一进程内直接调 `alpha.data`，少一跳 HTTP。
   若将来热点路径真要换 TS 直连，那时再引入 seam（一个 adapter 不算 seam）

**代价变更**：

- ✅ 省下约 2–3 周（2600 行重写 + 两套后端并存期）
- ✅ 少一个后端运行时；`pytest` 仍是唯一后端测试入口
- ⚠️ 后端与 Pi 跨语言：靠 RPC JSONL 契约（M1-1 的契约测试守这条边界）
- ⚠️ 前后端类型契约需手工同步（前端 `lib/api.ts` 的接口定义 → 后端 Pydantic 模型）

---

## 背景

用户决定：应用层与 Agent 层迁移到 Node/TypeScript，Python 数据层原地保留为内部服务。
理由是「整套架构换成 NodeJS，用 TypeScript 重写」+「留下 python（数据层）」。

在决策前对数据层做了逐函数实测（2026-10-20），得到三个关键事实。

### 事实 1：mootdx 已死；但 60 分钟线并非不可用（更正）

```
mootdx：ValueError: not enough values to unpack (expected 2, got 0)   # BESTIP bug
Quotes.factory(server=("119.147.212.81",7709)) → 73.6s，finance 返回 0 行
```

mootdx 的 K 线/盘口/逐笔在 2026-09 起失效（a-stock-data issue #52）；我们本机连**财务**
也拿不到。结论：**mootdx 整体放弃**。

**但 60 分钟线是可用的**：腾讯 `mkline` 端点支持 1/5/15/30/60 分钟（实测通过）：

```
https://ifzq.gtimg.cn/appstock/app/kline/mkline?param=sh600519,m60,,5
```

注意三点（a-stock-data V3.10.1 踩过的坑）：
① 必须用 `ifzq.gtimg.cn`，`web.ifzq.gtimg.cn` 的 `mkline` 会 301；
② **科创板（688/689）成交量单位是「股」，其余是「手」**（实测 600519=34136 手 vs 688017=10632800 股）；
③ 单次最多 320 根；当日分钟量取整到手，次日才回填成精确股数。

日/周/月线继续走腾讯 `fqkline`。

### 事实 2：akshare 可用，但上游项目已放弃它

实测（全部成功）：

| akshare 接口 | 用途 | 耗时 | 行数 |
|---|---|---|---|
| `stock_financial_abstract_ths` | 财务摘要（营收/净利/ROE/毛利率） | 0.66s | 103 |
| `stock_zt_pool_previous_em` | 昨日涨停池（涨停样本统计） | 0.26s | 46 |
| `stock_zt_pool_em` | 今日涨停池 | 0.23s | 54 |
| `stock_profit_sheet_by_report_em` | 利润表（有效税率推导） | 8.33s | 103 |
| `stock_zh_a_hist` | 日线（前复权） | 0.26s | 190 |

akshare 直接打 HTTP 接口，不经过 TDX 协议。

**但 a-stock-data V3.0 起已彻底移除 akshare**，理由是「中间层增加故障点（版本兼容 bug、
pandas 3.0 ArrowInvalid 等）」。我们的 `stock_news()` 正是 `ArrowInvalid` —— 同一个 bug。

因此本 ADR 的「必须留 Python」论据修正为：**pandas 数据处理 + baostock（估值历史/
上市退市/ST，TCP 客户端）+ 我们自己的回测引擎**，而不是 akshare 本身。

### 事实 3：astock.py 有一半是死代码

全仓库引用扫描（api / alpha / duanxian / mcpserver）：

```
定义 41 个函数 / 外部引用 10 个 / 模块内被调 16 个 / 活跃 21 个 / 死代码 20 个
```

死代码清单：`announcements` `block_trade` `concept_blocks` `disclosure`
`dividend_history` `dragon_tiger_board` `eastmoney_industry_reports`
`eastmoney_reports` `financials` `holder_num_change` `hot_concepts`
`individual_info` `industry_comparison` `investor_qa` `lockup_expiry`
`margin_trading` `pdf_url` `stock_fund_flow_120d` `stock_news`
`valuation_percentile`

其中 `stock_news`（ArrowInvalid 正则转义）、`individual_info`（ProxyError）、
`disclosure`（KeyError）**本来就是坏的**。

### 事实 4：指数有三套实现，两套重复

| 端点 | 底层 | 源 | 实测 |
|---|---|---|---|
| `/api/indices` | `astock.index_quote` | 腾讯 gtimg | ✅ A 股四大指数 |
| `/api/global/indices` | `gstock.global_indices` | 东财 push2 | ✅ 道指 52451.21 |
| `/api/market/overseas` | `overseas.overseas_snapshot` | 腾讯 gtimg | ✅ 道指 52453.53 |

后两者返回**同一批数据**，价差 < 0.01%（不同源采样时刻差异）。属于应合并的冗余。

## 决定

### 1. 应用层 + Agent 层 = Node 22 / TypeScript

> **2026-10-21 修订**：应用后端保留 Python，本节表格已更新。详见 §0。

| 层 | 技术 |
|---|---|
| 前端 | React 19 + Vite 6 + TypeScript + Tailwind + **Lightweight Charts** + ECharts |
| 应用后端 | **Python 3.13 + FastAPI**（原地保留，不重写） |
| Agent | Pi SDK 1.3.0（RPC 子进程，Python 侧自写 client，见 ADR-0010） |
| 数据 / 计算 | **Python 3.13 原地保留**（本节第 2 条） |
| 存储 | SQLite（沿用；Python 侧 `sqlite3` + 现有 `Store` 仓储层） |

### 2. Python 保留为计算层（**2026-10-21 修订：不再是独立 HTTP 服务**）

**保留范围**：`backend/research/` + `backend/duanxian/` + `backend/alpha/`
（计算库：backtest_engine / factor / limit_up_sample / chart），
**外加 `backend/api/` + `agent/` + `mcpserver/`**（修订后一并保留）。

分层纪律：计算层不 import `api.*` / FastAPI；`api/` 可 import 计算层。
这样 `run_python` 通道才能单独 import `alpha`（`mcpserver/runner.py` 的 `_preamble`
依赖这个方向）。

**理由**：

- **akshare 是硬依赖**。它封装了 100+ 个接口的中文字段解析、报告期排序、
  脏数据归一。TS 侧无等价物（`akshare` npm 包不存在）。
- **回测引擎是 A 股规则的沉淀**（T+1、涨跌停、停牌、复权、印花税/佣金/滑点），
  215 行已验证代码，重写风险高且无收益。
- **未来生态都是 Python**：qlib / vectorbt / alphalens / FinBuddy 的敏感性测算，
  全部只存在于 Python。

**服务形态**（2026-10-21 修订）：

```
前端  ──HTTP/SSE──>  apps/server（Python + FastAPI）
                        ├── 直接 import alpha / research（同进程，不经 HTTP）
                        ├── .../api/*  （现有 43 个端点，不重写）
                        └── PiProvider ──JSONL/stdio──> pi --mode rpc
```

~~Node 应用 ──HTTP/JSON──> Python 数据服务（:8901）~~ → **取消**：多一跳只是为了
跨语言，而修订后不存在跨语言的后端边界。

**边界的硬规则**（**2026-10-21 修订：§2 的「数据服务 = 独立 HTTP 进程」已取消**，
后端与数据层同进程；下方 1/2/4 条保留为分层纪律，第 3 条作废）：

1. **计算层不持有应用状态**。`research/` `duanxian/` `alpha/` 无 session、
   无 message、无 page、无用户数据。只做「输入参数 → 输出」。
2. **`research/duanxian/alpha` 不 import FastAPI / `api.*`**。单向依赖，
   这样计算层可被 `run_python` 沙箱单独 import（已有测试盖住）。
3. ~~Node 侧定义 `MarketDataPort`~~ → **作废**。同进程直接调 `alpha.data`，
   少一跳 HTTP。将来若某热点路径真要换语言，那时再引入 seam。
4. **响带 `asOf`**（数据时点）。现在只有 `duanxian/live_emotion.py` 有
   `as_of`，其余端点均无——这是 M5-4 要做的事，不是已完成项。

### 3. 数据层先清理再包接口

在暴露 HTTP 之前完成（否则等于把死代码固化成 API）：

| 清理项 | 动作 |
|---|---|
| astock.py 20 个死函数 | 删 |
| `astock.finance()`（mootdx 唯一残留） | 删 |
| `mootdx` 依赖 | 从 pyproject 删（实测连财务都取不到） |
| `astock.kline()` 的 60 分钟分支 | 改走腾讯 `mkline`（见事实 1），注意科创板量纲 |
| `gstock.global_indices` + `/api/global/indices` | 删；海外统一走 `overseas.overseas_snapshot` |
| `astock.financials()` / `valuation_percentile()` | 由 vendor 版本接管（估值历史走 baostock，实测需补装） |
| `newsradar`（108 个 RSS 源） | 保留（资讯雷达是复盘页的输入） |

**最终做法：全量 vendor 上游当前版本**（见 `docs/research/a-stock-data-v3.10.md`）。

我们的移植停在 v3.3，上游已到 **V3.10.2**（commit `29b07d2e3700`）：15 层 / 87 端点 /
34 源 / 179 条离线测试，Apache 2.0。**保留全部能力，不裁剪**——期货/期权/可转债/
事件驱动现在不用，但扩展时会用。

> **2026-10-21 修订**：本节整套动作从 **M0-5b 移到 M3-V1～M3-V6**（REFACTOR-PLAN）。
> 理由：它在 M3-7 之前对用户零可见收益；且依赖与主环境冲突
> （`mootdx` 锁 `httpx<0.26`，本仓库 `mcp>=1.9` 要 `httpx>=0.27`），
> 必须与 **data-service 独立 venv（M3-V1）** 一起做。
> **`mootdx` 不装**（实测连财务都取不到）。

vendor 形态：

1. `SKILL.md` 原样入库（425KB / 7585 行 / 91 个 python 块）+ `LICENSE` + `NOTICE`
2. 自写 **loader**：按序抽块 → AST 去掉模块级示例调用 → 同一 namespace exec → 导出函数
   （实测 182 个定义 / 181 唯一名，仅 `_macro_get` 重复）
3. 复用其 **179 条离线测试**作为 data-service 基线
4. 两层暴露：

   | 层 | 用途 |
   |---|---|
   | Curated REST（约 15 个） | 页面用的确定性数据，带缓存 + `asOf` |
   | `GET /v1/capabilities` + `POST /v1/invoke` | agent 走全部 87 个端点 |

5. `scripts/vendor-a-stock-data.sh`：重新下载 → 跑离线测试 → 绿则更新 NOTICE 里的 commit

清理后规模约 **loader 100 行 + vendor 425KB / 87 端点**；依赖
`pandas numpy requests baostock xlrd openpyxl`（**无 mootdx**）。

### 4. 单仓库布局（2026-10-21 修订：后端不重写，因此布局只是「搬」）

```
AlphaCopilot/
├── apps/
│   ├── web/                  # React SPA（原 frontend/，原样搬）
│   └── server/               # 应用后端 + PiProvider（原 backend/{api,agent,mcpserver}，原样搬）
├── data-service/             # 数据与计算（原 backend/{research,duanxian,alpha}，原样搬）
│   ├── pyproject.toml
│   ├── src/
│   ├── tests/
│   └── vendor/a-stock-data/  # 只读；见 docs/research/a-stock-data-v3.10.md
├── workspace/                # agent 可写区（pi 的 cwd）+ runs/<run_id>/
├── skills/                   # 白名单内的 SKILL.md（见 ADR-0010 修订 §5）
└── docs/
```

**没有 `packages/shared`**：修订后不存在跨语言共享类型层。`AgentProvider` 契约
留在 `backend/agent/provider.py`（Python），前端只认 SSE 事件名（已是中立的字符串）。

**分阶段落地**：M1–M2 保持 `backend/` 与 `frontend/` 目录名不变（降低重构噪音），
M3 再搬目录。理由：目录搬迁会让 `git blame` 断掉，且与功能改造混在一起无法 review。

> ⚠️ 坑：`data-service/src/loader.py` 里 `Path(__file__).parents[2]` 这类相对定位
> 在搬运后会指错。搬运 PR 必须同时修所有 `parents[N]` 与 `sys.path.insert`，
> 并有测试盖住（loader 一跑就能暴露）。

## 权衡

| 备选 | 否决原因 |
|---|---|
| A. 全量 TS 重写（放弃 Python） | 数据层多 3–4 周；87 个端点的中文列名解析要重新实现；复权/估值历史/申万行业变迁等口径要重新踩坑；回测引擎重写风险高 |
| C. 混合（高频 TS、长尾 Python） | 两个方向都有运行时，边界比 B 更乱；收益不足以抵消 |
| 保持 Python 全栈 | 与 ADR-0010 冲突（Pi 只有 Node）；用户明确要求 TS |

**代价**（2026-10-21 修订后）：

1. **后端与 Pi 跨语言**。缓解：RPC JSONL 是官方支持的语言中立边界；
   M1-1 的 PiProvider 契约测试用假 pi 进程守这条边界，不需要真模型。
2. **前后端类型契约手工同步**。缓解：后端 Pydantic 模型 → `openapi.json`
   始终可用（M0-3 修好 500），前端接口手写但由 `tsc` 守住形状。
3. ~~两套运行时、两套测试~~ → 只有 Pi 一个是 Node 程序（外部依赖，不是我们的代码）。
4. ~~多一跳 HTTP~~ → 同进程直接调用，无此代价。

## 影响

- ~~`backend/api/*`、`backend/agent/*`、`backend/mcpserver/*` 用 TypeScript 重写~~
  → **2026-10-21 撤销**。这些模块原地保留，M3 只搬目录。
- `backend/agent/providers/dsh.py` 删除，新增 `backend/agent/providers/pi.py`
  （Python 的 RPC client，约 200 行）——这是**唯一**要做实质改动的后端模块。
- `backend/research/*`、`backend/duanxian/*`、`backend/alpha/*`（计算部分）
  → 原地保留，M3 搬到 `data-service/`。
- AGENTS 硬规则 2/3/5 **不需要**因换语言而重写（真源仍是我们的数据库，实现语言不变）。
  但硬规则 5（provenance）目前**未落地**，见 REFACTOR-PLAN M1-5。
- 前端死方法清理不属于本 ADR（见 M0-6）。实际数字：`lib/api.ts` 424 行，
  `myreports` / `portfolio` 系列确有 404（后端是 `/portfolios`、`/reports`，
  不是 `/portfolio`、`/myreports`）；`stockPool` 实际存在（`/stock-pool`），不是死方法。
