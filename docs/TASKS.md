# 任务清单（TASKS）

> 依据 `docs/PLAN.md`。每任务一分支一 PR：`feat/T<nn>-<slug>`，squash merge。
> 规模：S ≤半天，M 1–2 天。

| ID | 任务 | 产出 | 依赖 | DoD | 规模 | 状态 |
|----|------|------|------|-----|------|------|
| T01 | 分支手术：归档旧线、orphan 新 main、默认分支切换 | 本仓库新 main | - | 远端见 archive/pre-dsh + 新 main | M | ✅ |
| T02 | backend 裁剪：仅保留 research 数据层库代码 | 瘦身 backend/ | T01 | research 模块可 import；无 FastAPI 胶水 | S | ✅ |
| T03 | 归档 frontend/（新 main 不含） | - | T01 | 新 main 无 frontend 目录 | S | ✅ |
| T04 | monorepo 脚手架：pnpm workspace + CI 双管线（TS/Python） | CI 配置 + 5 包骨架 | T02 | 空 build 过 CI | S | ✅ |
| T05 | S1 spike：bundle 安装流程验证 | docs/spikes/s1.md | T04 | dump-config 见 hello bundle | S | ✅ |
| T06 | S2 spike：自定义图表节点渲染 | docs/spikes/s2.md + demo | T05 | mock 折线出现在聊天流 | M | ✅ |
| T07 | S3 spike：MCP server 接入（transport 定论） | docs/spikes/s3.md | T05 | agent 调通 get_quote | M | ✅ d73e3d0（stdio 定论；mootdx 冲突遗留见 s3.md） |
| T08 | dsh-alphacopilot-research 包骨架 | server.py + tools/ 空壳 + pytest 骨架 | T07 | python -m 启动、工具清单可见 | S | ✅ |
| T09 | 行情工具 ×2（quote/kline）+ 单测 | tools/quote.py | T08 | pytest 绿（mock 数据层） | S | ✅ |
| T10 | 基本面/资金面工具 ×4 | tools/{fundamental,flows}.py | T08 | 同上 | M | ✅ |
| T11 | 资讯/事件 ×2 + 截断契约统一 | tools/events.py + 契约模块 | T10 | 截断与错误契约单测绿 | S | ✅ |
| T12 |
| T13 |
| T14a | S4 spike：web 插件注入整页面板 | docs/spikes/s4.md | T05 | 静态每日复盘卡片可见 | M | ✅ |
| T15 |
| T16 | desk 合规 prompt 注册 | src/index.ts `ctx.systemPrompt.section` | T15 | compliance section order=110 可见 | S | ✅ |
| T17 | skills 迁移 + preset stub | skills/*.md ×5 + presets/*.yaml | T16 | 5 skills + stub preset 到位 | S | ✅ |
| T18a |
| T19 |
| T20 | v0.1.0 发布：README 四节 + pack 验证 + tag | git tag v0.1.0 | T19 |

## 关键路径

```
T01 → {T02,T03} → T04 → T05 → {T06,T07,T14a}
  → {T08→T09→T10→T11 ‖ T12→T13→T14} → T15 → {T16→T17→T18, T18a} → T19 → T20
```

## 工作流约定

每个任务：开分支 → 红-绿-重构 → lint+test 全绿 → squash PR
（`feat(T09): kline tool wrapper`）→ 删分支。spike 类任务允许无测试，
但必须产出结论文档（含截图/命令输出）。
