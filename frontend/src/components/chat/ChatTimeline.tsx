/**
 * ChatTimeline — 对话主时间线（M1 打通）。
 *
 * 流程：挂载时建会话 → 用户发消息（乐观插入 user 气泡 + 空 assistant 气泡）→
 * 订阅 SSE → assistant/chunk 逐字累加到 assistant 气泡（逐字出字）→
 * message/committed 定稿。SSE 由 useSSE 管理（EventSource 原生重连）。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { MessageBubble, type BubbleMessage } from "@/components/chat/MessageBubble";
import { useSSE } from "@/hooks/useSSE";
import { createSession, sendMessage, streamUrl } from "@/lib/api";
import { extractChunkText } from "@/lib/chunk";

export function ChatTimeline() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<BubbleMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const { connect, disconnect } = useSSE();
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const streamingIdRef = useRef<string | null>(null);

  useEffect(() => {
    createSession().then(setSessionId).catch(() => setSessionId(null));
    return () => disconnect();
  }, [disconnect]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && typeof el.scrollTo === "function") {
      el.scrollTo({ top: el.scrollHeight });
    }
  }, [messages]);

  const appendToStreaming = useCallback((delta: string) => {
    const sid = streamingIdRef.current;
    if (!sid || !delta) return;
    setMessages((prev) =>
      prev.map((m) => (m.id === sid ? { ...m, content: m.content + delta } : m)),
    );
  }, []);

  const finalize = useCallback(() => {
    const sid = streamingIdRef.current;
    if (!sid) return;
    setMessages((prev) =>
      prev.map((m) => (m.id === sid ? { ...m, streaming: false } : m)),
    );
    streamingIdRef.current = null;
    setBusy(false);
  }, []);

  const onSend = useCallback(async () => {
    if (!sessionId || !input.trim() || busy) return;
    const text = input.trim();
    setInput("");
    setBusy(true);

    const assistantId = `local-a-${Date.now()}`;
    streamingIdRef.current = assistantId;
    setMessages((prev) => [
      ...prev,
      { id: `local-u-${Date.now()}`, role: "user", content: text },
      { id: assistantId, role: "assistant", content: "", streaming: true },
    ]);

    // 先订阅 SSE，再发消息（发消息会触发后台 turn；全量补发保证不漏早期事件）。
    connect(streamUrl(sessionId), {
      "assistant/chunk": (data) => appendToStreaming(extractChunkText(data)),
      "turn/final": (data) => {
        const finalText = (data.final_response as string) || "";
        // 若逐字累加为空（极端情况），用 final 兜底填充。
        const sid = streamingIdRef.current;
        if (sid && finalText) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === sid && m.content === "" ? { ...m, content: finalText } : m,
            ),
          );
        }
        finalize();
      },
      "turn/error": () => finalize(),
    });

    try {
      await sendMessage(sessionId, text);
    } catch {
      finalize();
    }
  }, [sessionId, input, busy, connect, appendToStreaming, finalize]);

  return (
    <div className="glass flex h-full flex-col rounded-lg">
      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            说点什么，开始对话
          </div>
        )}
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
      </div>
      <div className="flex gap-2 border-t border-border p-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSend();
            }
          }}
          placeholder={sessionId ? "输入消息…" : "连接中…"}
          disabled={!sessionId}
          className="flex-1 rounded-md bg-muted/40 px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus:ring-1 focus:ring-primary"
        />
        <button
          type="button"
          onClick={onSend}
          disabled={!sessionId || busy || !input.trim()}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-40"
        >
          发送
        </button>
      </div>
    </div>
  );
}
