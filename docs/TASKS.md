# 任务清单（TASKS）

> 依据 `docs/PLAN.md`（北极星 + 三契约）与 ADR-0006。
> 每任务一分支一 PR：`feat/T<nn>-<slug>`，squash merge。规模：S ≤半天，M 1–2 天。
> **任务号从 T21 续编**；T01–T20 属插件化路线，见文末归档说明。

## M0 — Spike 门禁（任一失败 → 方案评审，不得带病进 M1）

| ID | 任务 | 产出 | 依赖 | DoD | 规模 | 状态 |
|----|------|------|------|-----|------|------|
| T21 | G1：SDK + 自写 cordis.yml 挂我们的 MCP server | `docs/spikes/g1.md` + 最小 cordis.yml + 驱动脚本 | - | agent 调通 `get_quote` 返回茅台真实报价；`initialize` 就绪边界确认（首个 prompt 已能看到 MCP 工具） | M | ✅ PASS（茅台 1297.4；node+exe 两 carrier；negative control 证因果） |
| T22 | G2：notification → SSE 端到端 | `docs/spikes/g2.md` + 最小 FastAPI demo | T21 | ① 浏览器逐字出字 ② 杀子进程可中止 turn ③ **同 `session_id` + 同 `session_root` 重启后历史能否续上——实测结论（含证据）必须写进文档** | M | ✅ PASS（SSE 25 条流式 + 停止；跨进程复用旧 id 被 dsh id-collision 拒绝，须全新 id + 业务层重建） |
| T23 | G3：`run_python` 沙箱边界 | `docs/spikes/g3.md` + Seatbelt profile | - | 沙箱内：能 `import alpha`、能写 `workspace/runs/`、**读 `~/.ssh/*` 被拒绝**、超时被杀；三条各有一个断言 | M | ✅ PASS（5 断言全绿：import/写/读secret拒/超时/网络拒） |
| T24 | G4：skills + 合规 prompt 在 SDK 组合内可见 | `docs/spikes/g4.md` | T21 | 导出 model-visible 快照，见到 5 个 skill 条目与合规 section；不靠"应该能用"下结论 | S | ✅ PASS（keyless mock 捕获 model-visible：工具/skill/合规5关键词可见 + 真实调用回流） |

> G1 失败 → SDK 路线作废，回插件路线（现 main 的 tag）。
> G3 失败 → 改容器执行，需推翻 ADR-0006 决策 2 并由你确认。

## M1 — 骨架贯通

| ID | 任务 | 产出 | 依赖 | DoD | 规模 | 状态 |
|----|------|------|------|-----|------|------|
| T25 | 仓库结构手术 | `backend/{research,alpha,api,agent,mcp}` + `workspace/` + `skills/`；现 main 打 tag `archive-dsh-plugins-v0.1` | M0 全绿 | `pytest` 绿；`packages/` 4 个 TS 包移除；tag 已推远端；**不做 orphan 分支** | M | ✅ |
| T26 | 领域存储 schema | SQLite schema + migration + 仓储层 | T25 | message / artifact / page / job / doc 五张表建起，CRUD 单测绿 | M | ✅ |
| T27 | dsh 适配层（唯一耦合点） | `backend/agent/harness.py`：一会话一子进程、线程 + 队列 → asyncio | T21,T26 | 并发两个会话互不干扰；进程泄漏测试（close 后无残留子进程）绿 | M | ✅ |
| T28 | 会话 API + SSE | `POST /sessions/{id}/messages`、`GET /sessions/{id}/stream` | T27 | 消息落库 + SSE 推流单测绿；断线重连从 last_event_id 续传 | M | ✅ |
| T29 | 前端骨架 | Vite + Tailwind + router + design token 层；从 archive 取 4 类资产 | T25 | `pnpm build` 绿；暗/亮主题切换可用；**改 token 即全站变色**（一处改动截图对照） | M | ✅ |
| T30 | Chat 时间线打通 | ChatTimeline + useSSE 接入 | T28,T29 | **M1 验收：浏览器里说一句话，AI 逐字回一句话** | M | ✅ |
| T31 | 合规底线落位 | `skills/*.md` ×5 迁入 + 合规 prompt 进 cordis persona | T24,T27 | 追问「帮我推荐一只能涨的票」被拒绝并给出中立替代表述，测试固化该行为 | S | ✅ |

## M2 — 对话即研究（承诺 A）

| ID | 任务 | 产出 | 依赖 | DoD | 规模 | 状态 |
|----|------|------|------|-----|------|------|
| T32 | `alpha.chart` 与 ECharts option 契约 | `backend/alpha/chart.py` + JSON schema + 校验 | T26 | line/bar/heatmap/candlestick 四种 helper 产出的 option 通过校验；非法 option 被拒（各一条测试） | M | ✅ |
| T33 | `run_python` MCP 工具 | `backend/mcp/tools/run_python.py` | T23,T32 | 沙箱内执行、artifact 写入 `runs/<run_id>/`、超时/输出截断契约单测绿；**工具层零业务逻辑** | M | ✅ |
| T34 | artifact 入库与投递 | manifest 校验 → 落库 → 挂到消息 → REST 读取 | T33 | 非法 manifest 被拒（不信任 agent 输出）；artifact 与消息关联单测绿 | M | ✅ |
| T35 | block 渲染器 ×3 | ChartBlock / TableBlock / MarkdownBlock | T29,T34 | 对话流内出现可交互图：legend 切换、hover 十字对齐、dataZoom 三项手测 + 组件测试 | M | ✅ |
| T36 | **E2E-1 相关性场景** | 录屏 + 场景测试 | T35,T31 | 输入「分析近一年白酒板块 5 只标的与沪深300 的相关性」→ 对话流内出现可交互热力图 + 文字结论 | M | ✅ |

## M3 — 分析层与长任务（承诺 D 地基）

| ID | 任务 | 产出 | 依赖 | DoD | 规模 | 状态 |
|----|------|------|------|-----|------|------|
| T37 | `alpha.data` 门面 | 包住 `research.*` 的稳定 API + 高质量 docstring | T25 | AI 在不看源码的情况下能正确取到 K 线/估值/资金流（用 3 个真实提问验证）；**不再包 65 个 MCP 工具** | M | ✅ |
| T38 | Job 队列 | 提交 / 状态 / 事件流 + `submit_*` MCP 工具 | T28 | 长任务不阻塞 turn；job 事件经 SSE 到前端；失败路径有测试 | M | ✅ |
| T39 | `alpha.backtest` 最小引擎 | 信号 → 持仓 → 净值 / 回撤 / 年化 / 夏普 | T37 | 已知输入的净值曲线与手算基准一致（固定 fixture 断言） | M | ✅ |
| T40 | **E2E-2 回测场景** | 录屏 + 场景测试 | T38,T39,T35 | 「20/60 金叉在茅台回测近三年」→ job 完成 → 净值 + 回撤双图 + 指标卡 | M | ✅ |

## M4 — 页面可生长（承诺 B）

| ID | 任务 | 产出 | 依赖 | DoD | 规模 | 状态 |
|----|------|------|------|-----|------|------|
| T41 | page spec 存储 + `create_page` 工具 | REST + 工具（只能产 draft） | T26,T34 | AI 建出的页面 status 恒为 draft；spec 校验拒绝非法 block | M | ⬜ |
| T42 | 通用页面渲染器 + 发布流 | PageRenderer + 侧边栏导航 + 发布确认 UI | T41,T35 | **新增一个页面全程零前端代码改动、零重启**（用 curl 插一条 spec 验证） | M | ⬜ |
| T43 | 每日复盘作为内置 spec | 内置 page spec + 定时刷新 job | T42,T38 | 每日复盘页由 spec 渲染，4 段内容来自真实数据；定时任务可手动触发 | M | ⬜ |
| T44 | **E2E-3 发布页面** | 录屏 | T42 | 把 E2E-1 的产出发布为页面 → 刷新浏览器仍在 → 期间未改前端代码 | S | ⬜ |

## M5 — 文档与报告（承诺 C）

| ID | 任务 | 产出 | 依赖 | DoD | 规模 | 状态 |
|----|------|------|------|-----|------|------|
| T45 | 文档摄取 + FTS5 | `DocParser` 接口 + 朴素 PDF 解析 + FTS5 索引 | T26 | 手动投喂 3 份真实年报可检索；**`DocParser` 留好 MinERU 实现位（接口测试覆盖）** | M | ⬜ |
| T46 | `search_docs` + 报告 artifact | 工具 + markdown 报告契约（含出处） | T45,T34 | 报告中每个结论带 `doc_id + 页码/段落` 引用；引用可解析回原文（测试） | M | ⬜ |
| T47 | **E2E-4 报告场景** | 录屏 | T46 | 「根据我放进 docs 的三份年报写对比报告」→ 报告 artifact，结论可点回原文 | M | ⬜ |

## M6 — 发布

| ID | 任务 | 产出 | 依赖 | DoD | 规模 | 状态 |
|----|------|------|------|-----|------|------|
| T48 | v0.2.0 | README 四节 + 一键启动脚本 + 4 段 E2E 录屏归档 + tag | T36,T40,T44,T47 | 干净机器按 README 能起来；四项能力承诺各有一段录屏 | M | ⬜ |

## 关键路径

```
M0: {T21,T23} → T22 → T24
  → T25 → T26 → {T27 → T28, T29} → T30 → T31          （M1 骨架 + 合规）
  → T32 → T33 → T34 → T35 → T36                        （M2 对话即研究）
  → {T37 → T39, T38} → T40                             （M3 分析与长任务）
  → T41 → T42 → T43 → T44                              （M4 页面可生长）
  → T45 → T46 → T47                                    （M5 文档与报告）
  → T48
```

## 工作流约定

每个任务：开分支 → 红-绿-重构 → lint + test 全绿 → squash PR
（`feat(T33): run_python sandboxed tool`）→ 删分支。
spike 类任务（T21–T24）允许无测试，但**必须产出结论文档**（含命令输出/截图），
且必须明确回答"通过/不通过"，不接受"看起来可行"。

每完成一个 M，回到 `docs/PLAN.md` 第一节核对四项能力承诺，防跑偏。

## ADR-0007 迭代（T41–T50）：页面驱动 + dsh 解耦 + 参数化 page spec + 真实 agnes

依据 ADR-0007。三波并行推进，波间以测试全绿为门禁。

| ID | 任务 | DoD | 状态 |
|----|------|-----|------|
| T41 | dsh 解耦：AgentProvider/AgentEvent 中立契约 + DshProvider 下沉 + 前端换中立事件名 | grep 无 dsh 词汇泄漏；86 passed | ✅ |
| T42 | 真实 agnes 接通（strip \t baseURL + max_tokens cap 65536 + 去 thinking） | live 实测真实回复非空 | ✅ |
| T43 | alpha.factor.correlation：日期对齐(交集)/归一化叠加/收益率相关矩阵/滚动相关 | 手算 fixture；收益率相关≠价格相关 | ✅ |
| T44 | alpha.registry 白名单注册表 + ParamSpec.coerce | 未注册 fn 拒收；越界拒收 | ✅ |
| T45 | store 按聚合拆仓储 + page 表加 kind + validate_spec（fn 白名单） | 91 passed；fn=os.system 被拒 | ✅ |
| T46 | AppShell 页面驱动布局：可收展 tab + 右下浮标 + 右侧 chat panel + 会话状态提层 | 收展持久化；panel 开关不丢会话；69 passed | ✅ |
| T47 | 通用 PageRenderer：据 params 自动生成控件 + 改参重算 | 三种控件断言；改参触发 render；73 passed | ✅ |
| T48 | page render 端点 + 两条内置 spec（correlation/daily-review） | 97 passed；render 三 block 非空 series | ✅ |
| T49 | live E2E：真实 agnes 调 run_python 产图 | 实测：agnes 自主调 run_python → 产出合法 chart.json | ✅ |
| T50 | 承诺 B 验收：curl 插 page spec | 实测：curl POST → GET 立即多一页，零前端改动零重启 | ✅ |

已知环境阻塞（非代码缺陷）：A 股行情源 mootdx 在本环境不可达（`Quotes.factory` 即时失败），
故 correlation 页 render 真实行情返回 503（已做优雅降级，非 500）；T49 用 run_python 内合成
数据验证「模型写并执行分析代码产图」的能力链。真实行情接通留待数据源可达环境。

## 归档说明：T01–T20

T01–T20 属 ADR-0004/0005 的 dsh 插件化路线，已于 2026-08-29 由 ADR-0006 取代。
其中 T01–T18a 已完成，代码在 tag `archive-dsh-plugins-v0.1`。
资产回收清单见 `docs/PLAN.md` 第六节；spike 结论 `docs/spikes/s1–s4.md` 保留
（S3 的 MCP stdio 定论对 T21 仍有效，S2/S4 的插件渲染结论已作废）。
