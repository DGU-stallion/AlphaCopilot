import { createBrowserRouter, Navigate } from "react-router-dom";
import { Layout } from "@/components/layout/Layout";
import { DailyReview } from "@/pages/DailyReview";
import { MacroDashboard } from "@/pages/MacroDashboard";
import { Backtest } from "@/pages/Backtest";
import { Correlation } from "@/pages/Correlation";
import { Portfolios } from "@/pages/Portfolios";
import { MyReports } from "@/pages/MyReports";
import { Watchlist } from "@/pages/Watchlist";
import { Journal } from "@/pages/Journal";
import { Settings } from "@/pages/Settings";
import { Runs } from "@/pages/Runs";

// AlphaCopilot IA（见 CONTEXT.md）。复盘看板 = 盘面数据（DailyReview）。
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
      { path: "/quant-backtest", element: <Backtest /> },
      { path: "/correlation", element: <Correlation /> },
      { path: "/portfolios", element: <Portfolios /> },
      // 个人与系统
      { path: "/journal", element: <Journal /> },
      { path: "/settings", element: <Settings /> },
      { path: "/runs", element: <Runs /> },
      { path: "*", element: <Navigate to="/daily-review" replace /> },
    ],
  },
  // 🔵 原型路由：**故意放在 Layout 之外** —— 旧外壳的玻璃/暖橙正是要换掉的东西，
  // 拿它当背景板会让评审误判「新风格还是丑」。看完即删。
], { basename: import.meta.env.BASE_URL });
