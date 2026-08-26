# dsh-alphacopilot-research

AlphaCopilot 研究数据 MCP 服务（Python）。将 `backend/research/` 的 65 个纯数据
函数封装为 Model Context Protocol 工具，供 dsh agent 调用；同一进程挂载 REST
接口，供 `dsh-alphacopilot-web` 的每日复盘面板取数。

**形态**：stdio MCP server（由 dsh-alphacopilot-research-bridge 注册为受信任子进程）。

**状态**：骨架。实现见 TASKS T08–T11。

## 工具面（首批 8 个）

| 工具 | 数据函数 |
|---|---|
| get_quote | research.astock.tencent_quote |
| get_kline | research.astock.kline |
| get_valuation | research.astock.full_valuation |
| get_margin | research.astock.margin_trading |
| get_fund_flow | research.astock.stock_fund_flow_120d |
| get_news | research.astock.stock_news |
| get_announcements | research.astock.announcements |
| get_radar | research.newsradar |

## 运行

```bash
pip install -e ./packages/dsh-alphacopilot-research
python -m alphacopilot_research.server   # stdio；REST 挂载见后续任务
```
