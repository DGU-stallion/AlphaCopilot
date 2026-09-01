/**
 * useSSE — 订阅后端 GET /api/sessions/{id}/stream 的 SSE。
 *
 * 契约（见 backend/api/app.py）：每条 SSE 形如
 *   id: <n>\nevent: <type>\ndata: <json>\n\n
 * type ∈ { assistant/chunk, assistant/message, turn/final, message/committed, ... }。
 * EventSource 会把 id 作为 lastEventId，浏览器原生在重连时带上 Last-Event-ID。
 *
 * 只做一件事：连上、把每条事件按 type 分发给 handler、断开时自动重连（EventSource 原生）。
 * 不引入鉴权/去重等（本机单人系统，KISS）。
 */

import { useCallback, useRef } from "react";

export type SSEHandler = (data: Record<string, unknown>, eventId: string) => void;
export type SSEHandlers = Record<string, SSEHandler>;

export function useSSE() {
  const sourceRef = useRef<EventSource | null>(null);

  const connect = useCallback((url: string, handlers: SSEHandlers) => {
    sourceRef.current?.close();
    const source = new EventSource(url);
    sourceRef.current = source;

    const dispatch = (type: string) => (raw: MessageEvent) => {
      let parsed: Record<string, unknown>;
      try {
        parsed = JSON.parse(raw.data);
      } catch {
        parsed = { raw: raw.data };
      }
      const handler = handlers[type] ?? handlers["message"];
      handler?.(parsed, raw.lastEventId);
    };

    // 后端会发的事件类型（session.event 归一化后 + 适配层元事件）。
    const types = [
      "assistant/chunk",
      "assistant/message",
      "turn/final",
      "turn/error",
      "message/committed",
    ];
    for (const t of types) {
      source.addEventListener(t, dispatch(t));
    }
    // 兜底：未列出的类型走 onmessage / "message" handler。
    source.onmessage = dispatch("message");
  }, []);

  const disconnect = useCallback(() => {
    sourceRef.current?.close();
    sourceRef.current = null;
  }, []);

  return { connect, disconnect };
}
