// useAgentStream —— 会话对话的 React hook（S5）。
//
// 封装后端会话运行时的中立通路：
//   POST /api/sessions          建会话（首条消息时惰性创建，整个 hook 生命周期复用）
//   GET  /api/sessions/{id}/stream   订阅 SSE（中立事件 text_delta/tool_started/tool_result/turn_end/error）
//   POST /api/sessions/{id}/messages 触发一轮 agent turn
//
// 组件只用 { messages, send, busy, error, reset }：send 后先落用户气泡 + 空助手气泡，
// SSE 的 text_delta 增量追加到助手气泡，turn_end/message committed 收尾。
// 后端 DshProvider（profile=alphacopilot-prod + agnes）承载合规 persona + skills + MCP 工具；
// 前端不碰模型 key，也不出现任何 dsh 私有词汇。

import { useCallback, useRef, useState } from "react";
import { apiUrl } from "@/lib/base";
import { authHeaders } from "@/lib/api";

export interface AgentMsg {
  role: "user" | "assistant";
  content: string;
}

export interface ToolCall {
  tool: string;
  args: Record<string, unknown>;
}

interface SseEvent {
  event: string;
  data: unknown;
}

// 按 \n\n 分帧解析 SSE 文本流；注释帧（": keepalive"/": waiting"）无 event/data，忽略。
async function* readSse(resp: Response, signal?: AbortSignal): AsyncGenerator<SseEvent> {
  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  try {
    while (true) {
      if (signal?.aborted) return;
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buf.indexOf("\n\n")) !== -1) {
        const frame = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        let event = "message";
        const dataLines: string[] = [];
        for (const line of frame.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
        }
        if (dataLines.length === 0) continue;
        let data: unknown = null;
        try {
          data = JSON.parse(dataLines.join("\n"));
        } catch {
          data = dataLines.join("\n");
        }
        yield { event, data };
      }
    }
  } finally {
    reader.cancel().catch(() => {});
  }
}

async function createSession(signal?: AbortSignal): Promise<string> {
  const resp = await fetch(apiUrl("/api/sessions"), {
    method: "POST",
    headers: { ...authHeaders() },
    signal,
  });
  if (!resp.ok) throw new Error(`建会话失败 HTTP ${resp.status}`);
  return (await resp.json()).session_id as string;
}

export interface UseAgentStream {
  messages: AgentMsg[];
  busy: boolean;
  error: string | null;
  /** 发一条消息（可带页面确定性数据快照作上下文）；流式追加助手回复。 */
  send: (text: string, context?: string) => Promise<void>;
  /** 清空对话并开新会话。 */
  reset: () => void;
}

export function useAgentStream(): UseAgentStream {
  const [messages, setMessages] = useState<AgentMsg[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sessionRef = useRef<string | null>(null);

  const reset = useCallback(() => {
    sessionRef.current = null;
    setMessages([]);
    setError(null);
  }, []);

  const send = useCallback(async (text: string, context?: string) => {
    const q = text.trim();
    if (!q || busy) return;
    setBusy(true);
    setError(null);
    setMessages((m) => [...m, { role: "user", content: q }, { role: "assistant", content: "" }]);

    const appendToAssistant = (t: string) =>
      setMessages((m) => {
        const next = [...m];
        const last = next[next.length - 1];
        if (last && last.role === "assistant") {
          next[next.length - 1] = { ...last, content: last.content + t };
        }
        return next;
      });

    try {
      const prompt = context
        ? `【当前页面数据快照】\n${context}\n\n【用户问题】\n${q}`
        : q;

      const sid = sessionRef.current ?? (sessionRef.current = await createSession());

      // 先连流（新客户端缺省 last-event-id → 后端全量补发本轮事件，不漏早期 delta），再触发 turn。
      const streamResp = await fetch(apiUrl(`/api/sessions/${sid}/stream`), {
        headers: { ...authHeaders() },
      });
      if (!streamResp.ok || !streamResp.body) {
        throw new Error(`连接会话流失败 HTTP ${streamResp.status}`);
      }
      const postResp = await fetch(apiUrl(`/api/sessions/${sid}/messages`), {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ content: prompt }),
      });
      if (!postResp.ok) throw new Error(`发送消息失败 HTTP ${postResp.status}`);

      let finalText = "";
      for await (const { event, data } of readSse(streamResp)) {
        const payload = (data && typeof data === "object" ? data : {}) as Record<string, unknown>;
        if (event === "text_delta") {
          const t = payload.text;
          if (typeof t === "string" && t) appendToAssistant(t);
        } else if (event === "error") {
          throw new Error(typeof payload.error === "string" ? payload.error : "agent 出错");
        } else if (event === "turn_end") {
          if (typeof payload.final_text === "string") finalText = payload.final_text;
        } else if (event === "message/committed") {
          if (typeof payload.content === "string" && payload.content) finalText = payload.content;
          break;
        }
      }
      // 收尾：以最终落库文本为准（与增量一致时是幂等替换）。
      if (finalText) {
        setMessages((m) => {
          const next = [...m];
          const last = next[next.length - 1];
          if (last && last.role === "assistant") next[next.length - 1] = { ...last, content: finalText };
          return next;
        });
      }
    } catch (e) {
      const detail = e instanceof Error ? e.message : String(e);
      setError(detail);
      setMessages((m) => {
        const next = [...m];
        const last = next[next.length - 1];
        const msg = `抱歉，AI 助手暂时不可用（${detail}）。请确认后端已启动后重试。`;
        if (last && last.role === "assistant" && last.content === "") {
          next[next.length - 1] = { ...last, content: msg };
        } else {
          next.push({ role: "assistant", content: msg });
        }
        return next;
      });
    } finally {
      setBusy(false);
    }
  }, [busy]);

  return { messages, busy, error, send, reset };
}
