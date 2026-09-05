import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { JournalPage } from "@/pages/JournalPage";
import { PageView } from "@/pages/PageView";
import { PortfoliosPage } from "@/pages/PortfoliosPage";
import { ReportsPage } from "@/pages/ReportsPage";
import { StockPoolPage } from "@/pages/StockPoolPage";

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      // 页面驱动：默认落到第一个 builtin 页（ADR-0007，对话降级为浮标 panel）
      { index: true, element: <Navigate to="/pages/daily-review" replace /> },
      // 专用业务页（S3/S4，状态型 CRUD，不走 page spec）
      { path: "stock-pool", element: <StockPoolPage /> },
      { path: "journal", element: <JournalPage /> },
      { path: "reports", element: <ReportsPage /> },
      { path: "portfolios", element: <PortfoliosPage /> },
      // 参数化只读分析页（S2/S4，走 page spec + 通用渲染器）
      { path: "pages/:slug", element: <PageView /> },
    ],
  },
]);

export function App() {
  return <RouterProvider router={router} />;
}
