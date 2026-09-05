# ADR-0008 — 确定性计算为主 + 固定业务页面 + AI 只解释

**状态**：已决定
**日期**：2026-09-05
**取代**：ADR-0002（对话为主入口，已由 ADR-0007 降级）遗留措辞；调整 ADR-0006/0007
时期 PLAN 第一节「北极星」的产品定位。四层架构划分（展示 / 业务 / AI / 数据）不变。

## 背景

经过对 `AlphaTrading/` 下三个参考项目（vibe-astock、Vibe-Research、TradingAgents-astock）
的调研与本项目复盘，确认早期北极星「对话驱动 + AI 写 Python 算结果画图 + 页面可生长」
方向偏差，是导致反复大改与 bug 的根因之一：

1. **AI 写 Python 做研究**不该是产品核心。用户要的是确定性、可复核的固定业务页面，
   AI 只做解释和提供观点。
2. **page spec 用过头**：适合参数化只读分析页（相关性 / 盘面统计），不适合有 CRUD
   的业务页（交易日志 / 股票池 / 研报 / 组合）。硬塞会把 page spec 扩成低代码框架。
3. **多智能体辩论 / 分析师团队**不在范围内（那是 TradingAgents 的定位）。

## 决定

### 1. 产品定位：确定性计算为主，AI 只解释

- 平台主体是**确定性数据与后端计算**：复盘看板、盘面数据、涨停样本统计、相关性、
  回测、模拟组合等，结果由确定性 Python 算出，不经 AI 生成。
- **全局页面感知 Agent**（右下角浮标唤出的 chat panel）只做：解释当前页面数据、
  回答研究问题、提供分析观点、总结研报。**不生成计算结果、不写数据库**（写操作走
  草案 → 用户确认 → 确定性写接口）。
- 明确**不做**：实盘交易 / 盯盘 / 个股行情终端 / 多智能体辩论决策。

### 2. 页面分层：固定业务页 vs 参数化分析页

- **专用 React 业务页**（有交互 / CRUD）：复盘看板、交易日志、股票池、我的研报、
  回测、模拟组合、设置。
- **参数化 page spec 分析页**（只读 / 改参重算）：相关性、盘面统计、涨停样本统计。
- page spec 保留（ADR-0007 的白名单注册表机制不变），但降级为分析页工具，不再是
  «承诺 B：页面可生长» 那种产品级北极星。

### 3. 缝合优先：复用 > 适配 > 参考 > 新写

第一版以 vibe-astock / Vibe-Research 现成能力为供体，能搬运就不重写：

- **vibe-astock**：复盘 / 盘面 / 涨停样本统计 / 交易日志 / 股票池的确定性计算与数据层。
- **Vibe-Research**：我的研报、成熟回测引擎（engines/gate/run，移植开源 HKUDS/Vibe-Trading
  MIT，保留 NOTICE 归属）、全局 Agent 页面上下文设计。
- **TradingAgents-astock**：不进入第一版，仅作研究参考。

## 权衡

- **保留 dsh provider 而非立即替换** → dsh 作为当前 Agent runtime 的一个 provider 实现
  暂留（ADR-0007 的 provider 防腐层已就绪）；是否引入其它 runtime 后续按需决定。
  注：当前 dsh SDK 版本与 `agent/providers/dsh.py` 存在 `DeepSeekHarnessConfig` 签名
  不匹配，属独立的 provider 维护问题，不在本次定位调整范围内。
- **旧 research 模块先删无引用者**（chat/cli_runtime/portfolio/myreports/caches），
  live 数据层（astock/gstock/market/newsradar/models）保留。

## 影响

- README / AGENTS / CONTEXT / PLAN / TASKS 的「北极星 / 典型工作日 / 词汇表」需与本 ADR
  对齐（本轮同步更新）。
- 历史 ADR-0002/0004/0005/0006/0007 保留作决策轨迹，不删。
- 第一版页面清单与缝合顺序见 PLAN「下一步开发计划」章节。
