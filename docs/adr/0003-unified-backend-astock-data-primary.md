# ADR-0003 — 后端合并为单一 FastAPI 服务，数据层以 a-stock-data 为主

**状态**：已决定  
**日期**：2026-07-26

## 背景

两个项目各有独立的 FastAPI 后端和数据层：
- Vibe-Research：`a-stock-data` 工具箱（A股/美港股，开箱即用）
- Vibe-Trading：多数据源加载器（mootdx、Tushare、yfinance 等）+ 回测数据管道

## 决定

1. **后端合并**：统一为单一 FastAPI 服务，所有 API 在同一端口
2. **数据层**：研究类数据（实时行情、财报、资讯）以 `a-stock-data` 为主；回测历史数据保留 Vibe-Trading 的数据管道，两者职责不重叠
3. **不引入**：实盘交易执行、broker 连接器、IM channel 推送

## 权衡

- **备选方案**：保持两个后端独立 → 否决，前端需要维护两套 base URL，且 Agent 调数据时需跨服务，增加复杂度
- `a-stock-data` 已在 Vibe-Research 中验证稳定，研究类场景优先可靠性；Vibe-Trading 的回测管道有完整的 fallback 链，回测场景优先覆盖度

## 影响

- 合并后端时需要解决路由前缀冲突（两个项目都有 `/api/...`）
- Vibe-Trading 的 Agent 工具调用需要适配 `a-stock-data` 的接口约定
