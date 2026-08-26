# ADR-0004 — 迁移至 DeepSeek Harness 插件体系（大重构）

**状态**：已决定
**日期**：2026-08-26

## 背景

AlphaCopilot 原为 FastAPI（:8900）+ React 15 页（:5899）的单体：投研数据层、
量化 agent 循环、会话 SSE、前端全部自研。DeepSeek Harness（dsh）以
「一切皆插件」的 Cordis 内核提供了会话日志、agent loop、模型适配器、web UI
等通用能力，自研部分与它高度重复。

## 决定

1. **大重构，非渐进**：旧主线整体归档为 `archive/pre-dsh` 分支（tag
   `archive-v0.3`，永久只读）；新 main 以 orphan 起点重建。
2. **保留的旧资产仅一处**：`backend/research/` 的 65 个纯数据函数——它们是
   四个插件的共同数据来源，作为库代码继续维护。
3. **裁剪**：quant 实盘/live/channels/qveris/scheduled、FastAPI 路由胶水、
   React 前端 15 页，全部不进新 main（需要时去 archive 分支查）。
4. **交付形态**：5 个 dsh 包 + 独立 profile `alphacopilot`
   （详见 PLAN.md），启动 `dsh --profile alphacopilot`，不影响本机默认 dsh。

## 权衡

- **备选：渐进式共存**（新旧两套并行）→ 否决。两套会话体系/两个前端无法
  共享上下文，维护双倍成本；且用户核心场景（自然语言→图表）只有 dsh 能承载。
- **备选：新建独立插件仓库** → 否决。数据层跨仓库依赖（pip git dependency）
  脆弱；单仓库单 profile 更符合个人项目体量。
- **风险声明**：orphan 切断 git 历史。回溯方式 = archive 分支/tag；
  `git log --oneline archive/pre-dsh` 仍可查全史。

## 影响

- README/AGENTS.md 全部重写；CONTEXT.md 领域词汇表原样保留
- 后续所有开发遵循 docs/TASKS.md 的任务流与分支规范
