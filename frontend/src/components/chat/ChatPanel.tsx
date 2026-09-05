/**
 * ChatPanel — 右侧滑出面板（S1 占位，ADR-0008：agent 接入推迟至 S5）。
 *
 * 第一版**不接任何 agent provider**，本面板仅展示占位说明，不发起会话/SSE、
 * 不触发任何 provider 调用（保证 S1–S4 全程确定性、无 LLM 调用）。
 * S5 接入 agent 时，把占位替换为真实对话组件（会话状态已在 SessionProvider 层预留）。
 */

import { Sparkles, X } from "lucide-react";

export function ChatPanel({ onClose }: { onClose: () => void }) {
  return (
    <div
      className="chat-panel glass flex flex-col rounded-lg"
      role="dialog"
      aria-label="对话面板"
      data-placeholder="agent-deferred-s5"
    >
      <div className="flex items-center justify-between border-b border-border p-3">
        <span className="text-sm font-medium text-foreground">AI 助手</span>
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭对话"
          className="flex h-8 w-8 items-center justify-center rounded-md text-foreground/70 transition-colors hover:text-primary"
        >
          <X size={18} />
        </button>
      </div>
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
        <Sparkles size={32} className="text-primary/70" />
        <div className="text-sm font-medium text-foreground">AI 助手即将上线</div>
        <p className="text-xs leading-relaxed text-muted-foreground">
          第一版聚焦确定性数据与计算。AI 分析副驾将在后续版本接入，
          届时可基于当前页面数据解释、回答研究问题、提供分析观点。
        </p>
      </div>
    </div>
  );
}
