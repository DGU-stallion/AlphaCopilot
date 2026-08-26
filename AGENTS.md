# AGENTS.md — AlphaCopilot（dsh 插件化重构中）

大重构背景见 `docs/adr/0004-dsh-plugin-rewrite.md`。旧单体在 `archive/pre-dsh`。

## 结构速记

- `packages/dsh-alphacopilot-*`：5 个 dsh 插件（1 Python MCP + 4 TS bundle），职责见各包 README
- `backend/research/*.py`：数据层库代码真源（纯函数，禁加框架依赖）
- `docs/PLAN.md` 当前计划；`docs/TASKS.md` 任务状态（改代码前先看，完工后更新状态列）

## 硬规则

1. 一切开发走任务流：分支 `feat/T<nn>-<slug>` → squash PR，标题带任务号
2. TS 包构建必须自包含（prepare 不假设 monorepo checkout 存在）
3. cordis 注册一律经 ctx（可逆）；禁止裸 addListener/setInterval
4. Python 工具层零业务逻辑：校验 → 调 research.* → JSON 化 → 截断 ≤6000 字符
5. 颜色/主题只写在 `dsh-alphacopilot-web` CSS 变量与 chart-plot `theme.ts` 两处
6. 不引入 quant 实盘/live/channels/qveris/scheduled 相关任何代码
7. LLM 输出合规底线：不荐股、不预测涨跌、不给买卖时机（prompt 片段已固化）

## 命令

```bash
pnpm -r build          # 所有 TS 包
pnpm -r test           # vitest
cd backend && pytest   # Python（research 层）
ruff check . && pyright # lint/typecheck（配置就绪后生效）
```
