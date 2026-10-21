import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { Toaster } from "sonner";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { router } from "./router";
// 自托管字体（ADR-0014 §4）：Inter Variable 作 UI 文本，JetBrains Mono 作数字。
// 不走 CDN —— 离线可用、无第三方请求。
import "@fontsource-variable/inter";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "@fontsource/jetbrains-mono/700.css";
import "./index.css";
import { initCaliber } from "./theme/usePalette";

// 在首次渲染前把口径应用到 <html>：放在 render 之后会导致
// 首帧按默认口径上色、下一帧才跳变（可见的闪色）。
initCaliber();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <RouterProvider router={router} />
      <Toaster position="bottom-right" theme="dark" richColors closeButton duration={3500} />
    </ErrorBoundary>
  </StrictMode>
);
