/**
 * SessionContext — 会话状态 + SSE 生命周期提升到 AppShell 层（ADR-0007 决策 1）。
 *
 * 目的：右侧 chat panel 开/关不销毁会话。Provider 包在 AppShell 外层，
 * 独立于 panel 的挂载：session_id、消息列表、连接状态都存在这里，panel 卸载不影响。
 * panel 内的组件消费本 context，从而做到「关再开，会话不丢」。
 *
 * 只持有状态与最小生命周期（建会话 + 连/断 SSE）；事件解析形状归轨 A（ChatTimeline）。
 */

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import type { BubbleMessage } from "@/components/chat/MessageBubble";
import { useSSE } from "@/hooks/useSSE";
import { createSession } from "@/lib/api";

export type ConnectionState = "idle" | "connecting" | "ready" | "error";

export interface SessionCtx {
  sessionId: string | null;
  messages: BubbleMessage[];
  setMessages: React.Dispatch<React.SetStateAction<BubbleMessage[]>>;
  connection: ConnectionState;
  connect: ReturnType<typeof useSSE>["connect"];
  disconnect: ReturnType<typeof useSSE>["disconnect"];
}

const SessionContext = createContext<SessionCtx | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<BubbleMessage[]>([]);
  const [connection, setConnection] = useState<ConnectionState>("idle");
  const { connect, disconnect } = useSSE();
  const startedRef = useRef(false);

  useEffect(() => {
    // 建会话一次，独立于任何 panel 的挂载生命周期（严格模式二次挂载靠 ref 去重）。
    if (startedRef.current) return;
    startedRef.current = true;
    setConnection("connecting");
    createSession()
      .then((id) => {
        setSessionId(id);
        setConnection("ready");
      })
      .catch(() => setConnection("error"));
    return () => disconnect();
  }, [disconnect]);

  return (
    <SessionContext.Provider
      value={{ sessionId, messages, setMessages, connection, connect, disconnect }}
    >
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionCtx {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession 必须在 SessionProvider 内使用");
  return ctx;
}
