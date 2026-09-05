/**
 * ChatTimeline — 对话主时间线（M1 打通）。
 *
 * 流程：挂载时建会话 → 用户发消息（乐观插入 user 气泡 + 空 assistant 气泡）→
 * 订阅 SSE → text_delta 逐字累加到 assistant 气泡（逐字出字）→
 * message/committed 定稿。SSE 由 useSSE 管理（EventSource 原生重连）。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { MessageBubble } from "@/components/chat/MessageBubble";
import type { Artifact } from "@/components/blocks/ArtifactBlock";
import { listMessages, sendMessage, streamUrl } from "@/lib/api";
import { useSession } from "@/session-context";
import { extractDeltaText } from "@/lib/chunk";

export function ChatTimeline() {
  // 会话状态来自 AppShell 层的 SessionContext（单一真源，panel 开关不丢、不重复建会话）。
  const { sessionId, messages, setMessages, connect } = useSession();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const streamingIdRef = useRef<string | null>(null);

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
  }, [setMessages]);

  const finalize = useCallback(() => {
    const sid = streamingIdRef.current;
    if (!sid) return;
    setMessages((prev) =>
      prev.map((m) => (m.id === sid ? { ...m, streaming: false } : m)),
    );
    streamingIdRef.current = null;
    setBusy(false);
  }, [setMessages]);

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
      text_delta: (data) => appendToStreaming(extractDeltaText(data)),
      turn_end: (data) => {
        const finalText = (data.final_text as string) || "";
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
      error: () => finalize(),
      "message/committed": async () => {
        const sid = streamingIdRef.current;
        if (!sid) return;
        try {
          const msgs = await listMessages(sessionId);
          const last = [...msgs].reverse().find((m) => m.role === "assistant");
          const arts = (last as { artifacts?: Artifact[] } | undefined)?.artifacts;
          if (arts && arts.length) {
            setMessages((prev) =>
              prev.map((m) => (m.id === sid ? { ...m, artifacts: arts } : m)),
            );
          }
        } catch {
          /* 忽略拉取失败，不影响文本已渲染 */
        }
      },
    });

    try {
      await sendMessage(sessionId, text);
    } catch {
      finalize();
    }
  }, [sessionId, input, busy, connect, appendToStreaming, finalize, setMessages]);

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
