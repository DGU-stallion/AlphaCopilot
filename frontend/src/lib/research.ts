// Vibe-Research 系 4 页的后端客户端。对接 AlphaCopilot FastAPI（/api，vite 代理到 8900）：
//   回测 / 相关性 → POST /api/pages/{slug}/render（白名单分析函数产 ECharts option）
//   模拟组合     → /api/portfolios CRUD + rebalance + nav
//   我的研报     → /api/reports（复用 doc 表）list/add/delete
// 复用 base.ts 的 apiUrl、api.ts 的 ApiError/authHeaders，避免重复实现。
import { apiUrl } from "./base";
import { ApiError, authHeaders } from "./api";

// ---- 通用请求（与 api.ts 同风格：401 提示、连不上后端提示、payload.data 解包）----
async function req<T>(path: string, method: "GET" | "POST" | "DELETE" = "GET", body?: unknown): Promise<T> {
  const headers: Record<string, string> = { ...authHeaders() };
  const opts: RequestInit = { method };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  if (Object.keys(headers).length > 0) opts.headers = headers;
  let resp: Response;
  try {
    resp = await fetch(apiUrl(`/api${path}`), opts);
  } catch {
    throw new ApiError("连接不到后端，请先启动 AlphaCopilot 后端（默认 8900）", 0);
  }
  let payload: any = null;
  try {
    payload = await resp.json();
  } catch {
    /* 非 JSON */
  }
  if (!resp.ok) {
    throw new ApiError(payload?.detail || `HTTP ${resp.status}`, resp.status);
  }
  return (payload?.data ?? payload) as T;
}

// ---- 展示页渲染（回测 / 相关性）----
// 后端 _render_block 按 block.kind 映射：chart→{option}、metric→{metric:{items}}、table→{table}。
export interface MetricItem {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "up" | "down" | "flat" | "muted";
}
export interface RenderBlock {
  kind: "chart" | "metric" | "table" | "markdown";
  span: number;
  title?: string;
  option?: Record<string, unknown>;
  metric?: { items: MetricItem[] };
  table?: { columns: string[]; rows: unknown[][] };
  text?: string;
}
export interface RenderResult {
  blocks: RenderBlock[];
}

// values 为参数值（symbol/fast/slow/range 或 symbols/window/range）；后端按 ParamSpec 校验缺省取默认。
export const renderPage = (slug: string, values: Record<string, unknown>) =>
  req<RenderResult>(`/pages/${slug}/render`, "POST", values);

// ---- 模拟组合 ----
export interface Rebalance {
  id: string;
  portfolio_id: string;
  effective_on: string;
  weights: Record<string, number>;
  created_at: number;
}
export interface Portfolio {
  id: string;
  name: string;
  benchmark: string;
  created_at: number;
  created_on: string;
  rebalances: Rebalance[];
}
export interface NavResult {
  option: Record<string, unknown>;
}

export const listPortfolios = () => req<Portfolio[]>("/portfolios");
export const createPortfolio = (name: string, benchmark: string, created_on: string) =>
  req<{ id: string }>("/portfolios", "POST", { name, benchmark, created_on });
export const deletePortfolio = (pid: string) => req<{ ok: boolean }>(`/portfolios/${pid}`, "DELETE");
export const addRebalance = (pid: string, effective_on: string, weights: Record<string, number>) =>
  req<{ id: string }>(`/portfolios/${pid}/rebalance`, "POST", { effective_on, weights });
export const portfolioNav = (pid: string) => req<NavResult>(`/portfolios/${pid}/nav`);

// ---- 我的研报（复用 doc 表）----
export interface ResearchReport {
  id: string;
  title: string;
  source_path: string;
  created_at: number;
}
export const listReports = () => req<ResearchReport[]>("/reports");
export const addReport = (title: string, text: string, source_path = "") =>
  req<{ id: string }>("/reports", "POST", { title, text, source_path });
export const deleteReport = (did: string) => req<{ ok: boolean }>(`/reports/${did}`, "DELETE");
