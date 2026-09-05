import { createBrowserRouter, Navigate } from "react-router-dom";
import { Layout } from "@/components/layout/Layout";
import { DailyReview } from "@/pages/DailyReview";
import { Backtest } from "@/pages/Backtest";
import { Correlation } from "@/pages/Correlation";
import { Portfolios } from "@/pages/Portfolios";
import { MyReports } from "@/pages/MyReports";
import { LimitUpStats } from "@/pages/LimitUpStats";
import { Watchlist } from "@/pages/Watchlist";
import { Journal } from "@/pages/Journal";
import { Placeholder } from "@/pages/Placeholder";

// AlphaCopilot IA（见 CONTEXT.md）。复盘看板 = 盘面数据（DailyReview）。
export const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: <Navigate to="/daily-review" replace /> },
      // 市场复盘
      { path: "/daily-review", element: <DailyReview /> },
      { path: "/backtest", element: <LimitUpStats /> },
      // 研究管理
      { path: "/watchlist", element: <Watchlist /> },
      { path: "/reports", element: <MyReports /> },
      // 量化研究
      { path: "/quant-backtest", element: <Backtest /> },
      { path: "/correlation", element: <Correlation /> },
      { path: "/portfolios", element: <Portfolios /> },
      // 个人与系统
      { path: "/journal", element: <Journal /> },
      { path: "/settings", element: <Placeholder title="接入 AI" /> },
      { path: "*", element: <Navigate to="/daily-review" replace /> },
    ],
  },
], { basename: import.meta.env.BASE_URL });
