# AlphaCopilot

个人量化投研系统。整合 [Vibe-Research](https://github.com/simonlin1212/Vibe-Research) 与 [Vibe-Trading](https://github.com/HKUDS/Vibe-Trading)，本地单机运行。

## 功能

**投研**：每日复盘 · 资讯雷达 · 板块中心 · 个股数据 · 自选股

**量化**：自然语言 Agent 对话 · 交互式图表 · 多分析师协作 · 相关性分析 · 回测 · Alpha 因子库

**我的**：持仓 · 研报 · 研究记录

## 项目结构

```
AlphaCopilot/
├── frontend/          # Vite + React 19 + TS + Tailwind（:5899）
├── backend/           # 单一 FastAPI 服务（:8900）
│   ├── app.py         # 统一入口
│   ├── research/      # 投研数据层（基于 a-stock-data）
│   └── quant/         # 量化 agent 层（基于 Vibe-Trading）
├── a-stock-data/      # A 股数据工具箱
├── CONTEXT.md         # 领域词汇表
└── docs/adr/          # 架构决策记录
```

## 快速开始

```bash
# 后端（:8900）
cd backend
python3 -m venv .venv
.venv/bin/pip install -e .                        # 安装核心依赖
# 可选：完整数据源（akshare / mootdx / pandas）
# .venv/bin/pip install -e ".[research-full]"
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8900

# 前端（:5899）
cd frontend && npm install && npm run dev
```
