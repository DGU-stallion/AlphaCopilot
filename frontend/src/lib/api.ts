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
