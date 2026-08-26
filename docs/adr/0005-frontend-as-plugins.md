# ADR-0005 — 前端即 dsh web 插件，不自建前端

**状态**：已决定
**日期**：2026-08-26

## 背景

旧前端为独立 Vite+React 应用（:5899），与后端 (:8900) 双端口。迁移 dsh 后，
agent 对话界面由 dsh web 应用原生提供；每日复盘页仍需一个展示面。
曾考虑「React 壳 + iframe/反代内嵌 dsh」方案，被否决——多端口、多前端栈、
样式割裂，违背「一套 preset 启动、单站点」的产品形态。

## 决定

1. **唯一前端 = dsh web 应用**。所有页面是它的插件面：
   - Agent 对话 → dsh 原生聊天流
   - 图表 → `dsh-alphacopilot-chart-plot` 注册的 keyed chat node renderer
   - 每日复盘 → `dsh-alphacopilot-web` 注入的自定义面板（`dsh.client`
     浏览器半体 + slot 机制；社区插件已有整页注入先例）
2. **单端口**：`dsh --profile alphacopilot` 启动的 web 服务即全部 UI 入口。
3. **样式可改性约束**（当前样式从简，后续必须能低成本改版）：
   - 我们控制的颜色/主题只允许存在于两处：
     a) `dsh-alphacopilot-web` 的 CSS 变量文件（面板视觉）
     b) `dsh-alphacopilot-chart-plot` 的 `theme.ts`（图表视觉）
   - 组件不得硬编码颜色值；改版 = 只动上述两个文件
   - dsh 自身聊天界面样式不碰（不属于我们的修改范围）

## 权衡

- **备选：iframe/反代内嵌 dsh web** → 否决（见背景），且引入跨域与样式隔离问题
- **备选：把聊天 UI 也用 React 重写进自己壳里** → 否决，重复造 dsh 已有能力
- **已知限制**：dsh web 整页面板 slot API 未在官方文档完整列出（社区先例佐证），
  故设 S4 spike 验证；失败降级为特殊聊天节点形态

## 影响

- 新 main 不含 frontend/ 目录；Vite/Tailwind 依赖全部消失
- 每日复盘的数据来源改为 REST（挂在 MCP 同进程），不再是 FastAPI
