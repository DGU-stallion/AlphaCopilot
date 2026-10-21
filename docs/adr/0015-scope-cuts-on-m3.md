# ADR-0015：M3 范围内的三处「不做」

- 状态：已决定 2026-10-22
- 取代：REFACTOR-PLAN 的 M3-5（monorepo 搬迁）与 M3-7（删除 astock.py）
- 相关：ADR-0011（后端不重写）、ADR-0012（双轨产物）、REFACTOR-PLAN M3

## 背景

M3 原表里有三件事在动手前需要重新审视。判断标准是**第一性原理**：
每一层/每个目录存在的理由必须能被说清；说不清的就是臃肿。

## 决定 1：不删除 `backend/research/astock.py`（原 M3-7）

### 原计划

「删除旧移植 `astock.py`，被 vendor 替代」，验收是
`grep -r "移植自 a-stock-data"` 为空。

### 为什么不做

**它不是「第二套取数实现」，是语义封装层。** 三处 vendor 没有的东西：

1. **`DataUnavailable`** —— 区分「这只票没数据」与「取数环境坏了」。
   vendor 的函数失败方式不统一（有的返回 `{}`、有的抛 requests 异常）。
   我们踩过这个坑：取数失败静默返回空 → 模型以为没数据 → 自己编了个 r=0.7716。
2. **域名兜底** —— 实测 `web.ifzq.gtimg.cn` 返回 501、`ifzq.gtimg.cn` 正常。
   这类「同名多域名」的经验是运行中积累的，vendor 不保证。
3. **`kline()` 的多源尝试** —— 单一数据源不可用时换下一个。

AGENTS 反模式禁的是「重复实现取数」，不是「在取数之上加业务语义」。
删掉封装层，意味着把这三种语义分散回 12 个调用点——**代码总量会变多，不是变少。**

### 性能实测（决定性的）

| 路径 | 单次耗时 |
|---|---|
| `astock.tencent_quote` 直连 | 0.32s |
| vendor 经子进程 | 0.77s |

拆解：进程启动 0.01s + vendor `load()` 0.36s + 网络请求。
页面高频路径（一屏 5–20 只票）走 vendor 会明显卡。

### 结论

**分层保留**：`astock` 是页面的高频语义封装，vendor 经 `/v1/invoke`
是 agent 的**广度**入口（期货/期权/可转债等我们还没做的领域）。
两者不是竞争关系，是频率与广度的分工。

## 决定 2：不搬迁到 monorepo（原 M3-5）

### 原计划

`apps/web` + `apps/server` + `data-service`。

### 为什么不做

monorepo 的真实收益是**多包共享 + 独立发版**。本项目：

- 一个前端（`frontend/`）+ 一个后端（`backend/`）
- 没有需要跨包共享的代码（前端是 TS、后端是 Python，本来就不共享）
- 没有独立发版需求（个人本地工作台，一起测一起上）

代价却很实在：全部 `Path(__file__).parents[N]` 与 `sys.path.insert` 要改，
358 后端 + 173 前端测试要全部重验，`git log --follow` 断代。

**纯风险，零收益。** 目录叫 `frontend/` 还是 `apps/web/` 对使用者没有区别。

### 结论

保留 `backend/` + `frontend/` + `data-service/`。
AGENTS、PLAN、README 里的「目标形态」图需要修正，不要留一个永远不打算兑现的描述。

## 决定 3：`data-service/` 的真实定位是「vendor 运行时宿主」

### 现状

它不承载我们的数据与计算（那些在 `backend/{research,alpha,duanxian}`），
只装 vendor 的 SKILL.md 和一个独立 venv。

### 它存在的唯一理由

**依赖隔离**：vendored 的 `mootdx` 要 `httpx<0.26`，主环境 `mcp` 要 `>=0.27`。
区间不相交，同一个解释器装不下。这不是设计选择，是硬约束。

### 结论

不要假装它是「数据服务」（AGENTS 原来的描述是 `data-service/` 承载
`research · duanxian · alpha`，这与现实不符）。文档改为：
**`data-service/` = vendor 运行时宿主 + 独立 venv**。

保留目录名（改名会牵连 CI 与脚本，收益只是名字更好听）。

## 影响

- REFACTOR-PLAN 的 M3-5、M3-7 标记为「已取消，见 ADR-0015」
- AGENTS 的目录速记与分层职责需按上面三条修正
- M3 剩余：V5 已完成；V6 已完成；M3-4 Rerun 已完成

## 重新审视的触发条件

如果将来出现以下情况，本 ADR 应当被重新打开：

1. **vendor 的调用变成页面高频路径**（比如某天我们要用 vendor 特有的数据源
   做主体页面）→ 那时需要常驻 worker 而不是每调一个子进程
2. **真的出现第二个前端/第二个后端**（比如做移动端）→ monorepo 才有意义
3. **`astock.py` 里出现第三套取数实现**（而不是语义封装）→ 那时它才该被删
