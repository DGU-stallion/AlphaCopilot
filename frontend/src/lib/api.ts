/** 会话 API 客户端 —— 打到 /api（vite 代理到 FastAPI）。 */

export interface Message {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  seq: number;
}

export async function createSession(): Promise<string> {
  const r = await fetch("/api/sessions", { method: "POST" });
  if (!r.ok) throw new Error(`createSession ${r.status}`);
  return (await r.json()).session_id;
}

export async function listMessages(sid: string): Promise<Message[]> {
  const r = await fetch(`/api/sessions/${sid}/messages`);
  if (!r.ok) throw new Error(`listMessages ${r.status}`);
  return r.json();
}

export async function sendMessage(sid: string, content: string): Promise<void> {
  const r = await fetch(`/api/sessions/${sid}/messages`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!r.ok) throw new Error(`sendMessage ${r.status}`);
}

export function streamUrl(sid: string): string {
  return `/api/sessions/${sid}/stream`;
}

// ── 展示页（ADR-0007：页面数据驱动）───────────────────────────────────────

export interface PageParam {
  name: string;
  type: "symbol_list" | "int" | "float" | "date_range" | "enum" | "str";
  label: string;
  default?: unknown;
  min?: number;
  max?: number;
  max_len?: number;
  choices?: string[];
}

export interface PageSpec {
  slug: string;
  title: string;
  kind?: string;
  layout?: string;
  params: PageParam[];
}

// 后端 GET /api/pages/{slug} 返回整行 {id,slug,title,kind,status,spec:{...}}，
// 真正的 params/blocks 在内层 spec。这里解包为前端用的 PageSpec。
interface PageRow {
  slug: string;
  title: string;
  kind?: string;
  spec: { params?: PageParam[]; layout?: string; title?: string };
}

export interface PageListItem {
  slug: string;
  title: string;
  kind?: string;
}

export interface PageBlock {
  kind: "chart" | "markdown" | "table" | "metric" | string;
  span?: number;
  title?: string;
  option?: Record<string, unknown>;
  text?: string;
  table?: { columns?: string[]; rows?: (string | number)[][] };
  metric?: {
    items?: {
      label: string;
      value: string | number;
      hint?: string;
      tone?: "up" | "down" | "flat" | "muted";
    }[];
  };
}

export async function listPages(): Promise<PageListItem[]> {
  const r = await fetch("/api/pages");
  if (!r.ok) throw new Error(`listPages ${r.status}`);
  return r.json();
}

export async function getPage(slug: string): Promise<PageSpec> {
  const r = await fetch(`/api/pages/${slug}`);
  if (!r.ok) throw new Error(`getPage ${r.status}`);
  const row: PageRow = await r.json();
  return {
    slug: row.slug,
    title: row.title,
    kind: row.kind,
    layout: row.spec?.layout,
    params: row.spec?.params ?? [],
  };
}

export async function renderPage(
  slug: string,
  params: Record<string, unknown>,
): Promise<PageBlock[]> {
  const r = await fetch(`/api/pages/${slug}/render`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!r.ok) throw new Error(`renderPage ${r.status}`);
  return (await r.json()).blocks;
}
