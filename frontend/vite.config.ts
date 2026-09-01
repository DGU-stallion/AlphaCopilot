import react from "@vitejs/plugin-react";
import path from "path";
import { defineConfig, loadEnv } from "vite";

// 后端接口走 /api 前缀，代理到本地 FastAPI（默认 127.0.0.1:8900）。
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_API_URL || "http://127.0.0.1:8900";
  return {
    plugins: [react()],
    resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
    server: {
      port: 5899,
      proxy: { "/api": { target: apiTarget, changeOrigin: true } },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            "vendor-react": ["react", "react-dom", "react-router-dom"],
            "vendor-charts": ["echarts"],
          },
        },
      },
    },
  };
});
