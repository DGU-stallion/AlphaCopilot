import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { Toaster } from "sonner";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { router } from "./router";
import { primeCliAvailability } from "./lib/ai-models";
import { authHeaders } from "./lib/api";
import "./index.css";

// AI CLI 探测占位（S5 上线）：primeCliAvailability 目前是 no-op，不阻塞首屏。
void primeCliAvailability(authHeaders());

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <RouterProvider router={router} />
      <Toaster position="bottom-right" theme="dark" richColors closeButton duration={3500} />
    </ErrorBoundary>
  </StrictMode>
);
