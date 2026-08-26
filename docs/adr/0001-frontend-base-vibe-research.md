# ADR-0001 — 前端以 Vibe-Research 为基础，整合 Vibe-Trading 的量化页面

**状态**：已决定  
**日期**：2026-07-26

## 背景

AlphaCopilot 需要整合两个有各自前端的项目：
- Vibe-Research：React 19 + Tailwind 玻璃暖橙主题，面向投研看板
- Vibe-Trading：React 19 + Tailwind，面向量化 agent 框架

两套前端风格相近（同为 React + Tailwind），但 Vibe-Research 的 UI 设计更完整，Vibe-Trading 的功能模块（Agent、Correlation、AlphaZoo、Reports）是需要引入的核心能力。

## 决定

以 Vibe-Research 的前端框架和 UI 风格为基础，将 Vibe-Trading 的量化页面（Agent、Correlation、AlphaZoo、Reports、RunDetail）迁移并适配进来。侧边栏导航按"投研 / 量化 / 我的"三组重新组织。

## 权衡

- **备选方案**：以 Vibe-Trading 前端为基础 → 否决，因为 Vibe-Trading 的 UI 偏向工具型，Vibe-Research 的玻璃暖橙主题更符合个人投研工具的使用感
- **备选方案**：两套前端独立运行 → 否决，目标是统一体验，不是拼凑两个系统

## 影响

- Vibe-Trading 的页面组件需要适配 Vibe-Research 的 CSS 变量和设计 token
- 后续新增页面统一遵循 Vibe-Research 的玻璃暖橙设计语言
