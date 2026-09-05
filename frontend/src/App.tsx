import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { PageView } from "@/pages/PageView";

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      // 页面驱动：默认落到第一个 builtin 页（ADR-0007，对话降级为浮标 panel）
      { index: true, element: <Navigate to="/pages/daily-review" replace /> },
      { path: "pages/:slug", element: <PageView /> },
    ],
  },
]);

export function App() {
  return <RouterProvider router={router} />;
}
