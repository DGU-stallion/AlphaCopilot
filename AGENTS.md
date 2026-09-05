# AGENTS.md — AlphaCopilot

产品定位见 `docs/adr/0008-deterministic-first-fixed-pages.md`（确定性计算为主、
AI 只解释、固定业务页面）。历史决策 ADR-0002/0004/0005/0006/0007 保留作轨迹。
第一版策略：缝合 `AlphaTrading/` 下 vibe-astock、Vibe-Research 现成能力，能复用就不重写。

## 结构速记

- `backend/research/*.py`：数据层，纯函数，**禁加框架依赖**
- `backend/alpha/*`：业务层库（data · chart · factor · backtest · report）
- `backend/api/*`：FastAPI；`backend/agent/*`：dsh SDK 适配层（唯一耦合点）
- `backend/mcp/*`：我们的 MCP server（run_python / publish_* / create_page / search_docs）
- `frontend/`：React SPA；`workspace/`：agent 可写区（sandbox 根）
- `docs/PLAN.md` 第一节是北极星；`docs/TASKS.md` 任务状态（改代码前先看，完工后更新）

## 硬规则

1. 一切开发走任务流：分支 `feat/T<nn>-<slug>` → squash PR，标题带任务号；号从 T21 起
2. **前端永不读取 dsh 的 session JSONL**；产品真源在我们自己的数据库
3. **agent 不直接写数据库**：只写 workspace 文件 + 调副作用 MCP 工具，业务层校验后落库
4. **重活不进 agent 的 turn**：长任务走 job 队列，agent 只「写代码 → 提交 job → 读结果」
5. MCP 工具层零业务逻辑：校验 → 调 `alpha.*` → JSON 化 → 截断 ≤6000 字符
6. **固定业务页**：前端为缝合的固定页组件（非旧 page-spec 动态渲染）；
   回测/相关性仍走 `/api/pages/{slug}/render`，新增市场类页直连专用 REST 端点
7. 颜色/主题只写在 `frontend/src/index.css` 的 token 与 `lib/chart-theme.ts` 两处
8. 图表默认产 ECharts option JSON（可交互）；PNG 仅用于 helper 表达不了的图形
9. **不给 agent bash**（SDK 闭包无 `bash-sandbox`，`bash-local` 不隔离）；
   代码执行只经我们的 `run_python`（Seatbelt profile）
10. 不引入实盘/live/channels/qveris/scheduled 相关任何代码
11. LLM 输出合规底线：不荐股、不预测涨跌、不给买卖时机（prompt 片段已固化）

## 命令

```bash
cd backend && pytest          # Python 测试
ruff check . && pyright       # lint / typecheck
cd frontend && pnpm build && pnpm test
```
