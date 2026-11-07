import { createBrowserRouter, Navigate } from "react-router-dom";
import { Layout } from "@/components/layout/Layout";
import { DailyReview } from "@/pages/DailyReview";
import { MacroDashboard } from "@/pages/MacroDashboard";
import { Portfolios } from "@/pages/Portfolios";
import { MyReports } from "@/pages/MyReports";
import { Watchlist } from "@/pages/Watchlist";
import { Journal } from "@/pages/Journal";
import { Settings } from "@/pages/Settings";
import { Runs } from "@/pages/Runs";
import { PageView } from "@/pages/PageView";

// AlphaCopilot IA（见 CONTEXT.md）。复盘看板 = 盘面数据（DailyReview）。
//
// ROUND2-B1/B2：Build 与 研究线 两页已删。用户决策「收敛成一个实验区，只留 Runs」。
//
// ADR-0016：`/p/:slug` 是**通用渲染路由** —— 页面由 spec（数据库里的数据）描述，
// 不再每个页面写一个 TSX。这是当初 Build 缺的那一环（发布只写库、前端读不到），
// 也是 agent 能自己扩展产品能力的入口。
export const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: <Navigate to="/daily-review" replace /> },
      // 市场复盘
      { path: "/macro", element: <MacroDashboard /> },
      { path: "/daily-review", element: <DailyReview /> },
      // 研究管理
      { path: "/watchlist", element: <Watchlist /> },
      { path: "/reports", element: <MyReports /> },
      // 量化研究
      // ADR-0016：回测/相关性已迁到 spec 渲染（/p/:slug）。
      // 旧路径保留为重定向 —— 书签、外部链、浏览器历史里还有它们，
      // 直接 404 会让人以为页面被删了。
      { path: "/quant-backtest", element: <Navigate to="/p/backtest" replace /> },
      { path: "/correlation", element: <Navigate to="/p/correlation" replace /> },
      { path: "/portfolios", element: <Portfolios /> },
      // 个人与系统
      { path: "/journal", element: <Journal /> },
      { path: "/settings", element: <Settings /> },
      { path: "/runs", element: <Runs /> },
      // 通用页面渲染（ADR-0016）：内置页目前仍走各自手写页，
      // 新增/agent 产出的页面统一走这里。
      { path: "/p/:slug", element: <PageView /> },
      { path: "*", element: <Navigate to="/daily-review" replace /> },
    ],
  },
], { basename: import.meta.env.BASE_URL });
