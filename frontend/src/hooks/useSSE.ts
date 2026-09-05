/**
 * useSSE — 订阅后端 GET /api/sessions/{id}/stream 的 SSE。
 *
 * 契约（见 backend/agent/provider.py）：每条 SSE 形如
 *   id: <n>\nevent: <kind>\ndata: <json>\n\n
 * kind ∈ { text_delta, tool_started, tool_result, turn_end, error,
 *          message/committed, ... }（provider 归一化后的中立事件 + 编排层元事件）。
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

    // 后端会发的事件类型（provider 归一化后的中立 kind + 编排层元事件）。
    const types = [
      "text_delta",
      "tool_started",
      "tool_result",
      "turn_end",
      "error",
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
