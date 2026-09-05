/**
 * ChatPanel — 右侧滑出的对话面板（ADR-0007 决策 1，对话降级为辅助）。
 *
 * 消费 SessionContext（会话状态在 AppShell 层，不随 panel 卸载而丢）。
 * 内部复用 ChatTimeline（按其现状 props 传入，事件形状归轨 A，本文件不碰）。
 */

import { X } from "lucide-react";
import { ChatTimeline } from "@/components/chat/ChatTimeline";
import { useSession } from "@/session-context";

export function ChatPanel({ onClose }: { onClose: () => void }) {
  // 消费 context：证明会话状态提升到了 AppShell 层（panel 开关不销毁会话）。
  const { sessionId, messages } = useSession();

  return (
    <div
      className="chat-panel glass flex flex-col rounded-lg"
      role="dialog"
      aria-label="对话面板"
      data-session-id={sessionId ?? ""}
      data-message-count={messages.length}
    >
      <div className="flex items-center justify-between border-b border-border p-3">
        <span className="text-sm font-medium text-foreground">对话</span>
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭对话"
          className="flex h-8 w-8 items-center justify-center rounded-md text-foreground/70 transition-colors hover:text-primary"
        >
          <X size={18} />
        </button>
      </div>
      <div className="min-h-0 flex-1">
        <ChatTimeline />
      </div>
    </div>
  );
}
