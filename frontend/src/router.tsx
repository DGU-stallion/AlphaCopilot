import { createBrowserRouter, Navigate } from "react-router-dom";
import { Layout } from "@/components/layout/Layout";

// 投研组
import { DailyReview } from "@/pages/DailyReview";
import { Intel } from "@/pages/Intel";
import { Sectors } from "@/pages/Sectors";
import { SectorDetail } from "@/pages/SectorDetail";
import { StockData } from "@/pages/StockData";
import { Watchlist } from "@/pages/Watchlist";

// 量化组
import { Agent } from "@/pages/Agent";
import { Correlation } from "@/pages/Correlation";
import { Reports } from "@/pages/Reports";
import { RunDetail } from "@/pages/RunDetail";
import { AlphaZoo } from "@/pages/AlphaZoo";

// 我的
import { Portfolio } from "@/pages/Portfolio";
import { MyReports } from "@/pages/MyReports";
import { Notes } from "@/pages/Notes";
import { Settings } from "@/pages/Settings";

export const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: <Navigate to="/daily-review" replace /> },

      // 投研组
      { path: "/daily-review", element: <DailyReview /> },
      { path: "/intel", element: <Intel /> },
      { path: "/sectors", element: <Sectors /> },
      { path: "/sectors/:key", element: <SectorDetail /> },
      { path: "/stock-data", element: <StockData /> },
      { path: "/watchlist", element: <Watchlist /> },

      // 量化组
      { path: "/agent", element: <Agent /> },
      { path: "/correlation", element: <Correlation /> },
      { path: "/reports", element: <Reports /> },
      { path: "/reports/:id", element: <RunDetail /> },
      { path: "/alpha-zoo", element: <AlphaZoo /> },

      // 我的
      { path: "/portfolio", element: <Portfolio /> },
      { path: "/my-reports", element: <MyReports /> },
      { path: "/notes", element: <Notes /> },
      { path: "/settings", element: <Settings /> },
    ],
  },
]);
