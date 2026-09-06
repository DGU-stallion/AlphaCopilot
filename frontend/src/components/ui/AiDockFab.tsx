/**
 * 右下角全局浮标（FAB）+ 可展开的 chat 面板 —— **每一页都有**，覆盖所有页。
 *
 * S5 接入：对话走后端会话运行时（useAgentStream → /api/sessions + SSE）。
 *  - 面板顶部显示「当前页面: XXX」（从 useCurrentAiPage 读，见 lib/ai-page）；
 *  - 用户发消息显示用户气泡，助手回复经 SSE 流式逐字追加；
 *  - 页面确定性数据快照作为本轮上下文一并发给后端（合规 persona + 工具由后端 provider 承载）。
 *
 * 面板是浮层（fixed），不占页面布局；风格用现有玻璃暖橙设计系统（.glass）。
 */
import { useEffect, useRef, useState } from "react";
import { Sparkles, X, Send, MessageCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { useCurrentAiPage } from "@/lib/ai-page";
import { useAgentStream } from "@/hooks/useAgentStream";

export function AiDockFab() {
  const page = useCurrentAiPage();
  const { messages: msgs, busy, send: sendMsg } = useAgentStream();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  // 面板开着时 Esc 关掉（弹层的基本预期）
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [msgs]);

  const send = (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    void sendMsg(q, page?.context ?? "");
  };

  return (
    <>
      {/* 右下角固定浮标 */}
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="打开 AI 助手"
        title="AI 助手"
        className="fixed bottom-5 right-5 z-40 inline-flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-glow ring-1 ring-primary/40 transition-transform hover:scale-105"
      >
        <Sparkles className="h-5 w-5" />
      </button>

      {open && (
        <aside className="glass fixed bottom-20 right-5 z-50 flex h-[28rem] w-[22rem] max-w-[calc(100vw-2.5rem)] flex-col rounded-2xl">
          {/* 头部：标题 + 当前页面 + 关闭 */}
          <div className="flex items-center justify-between gap-2 border-b border-border/60 p-3.5">
            <div className="min-w-0">
              <span className="flex items-center gap-2 text-sm font-semibold text-glow">
                <Sparkles className="h-4 w-4 shrink-0 text-primary" /> AI 助手
              </span>
              <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                当前页面：{page ? page.title : "（这一页暂无可聊内容）"}
              </span>
            </div>
            <button onClick={() => setOpen(false)} aria-label="关闭" className="shrink-0 text-muted-foreground hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* 消息列表 */}
          <div ref={scrollRef} className="flex-1 space-y-3 overflow-auto p-3.5 text-sm">
            {msgs.length === 0 && (
              <div className="space-y-3">
                <div className="rounded-lg border border-primary/25 bg-primary/5 p-3 text-xs text-muted-foreground">
                  问我关于本页数据的问题。我会基于当前页面的确定性数据为你解释，只做客观分析，不构成投资建议。
                </div>
                {page?.context && (
                  <div>
                    <p className="mb-1.5 flex items-center gap-1 text-[11px] font-medium text-muted-foreground">
                      <MessageCircle className="h-3 w-3" /> 本页确定性数据快照
                    </p>
                    <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-lg bg-black/30 p-3 font-mono text-[11px] leading-relaxed text-muted-foreground">
{page.context}
                    </pre>
                  </div>
                )}
                {page?.suggestions && page.suggestions.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {page.suggestions.map((s) => (
                      <button key={s} onClick={() => send(s)}
                        className="rounded-full border border-border bg-muted/40 px-2.5 py-1 text-xs hover:border-primary/40 hover:text-primary">
                        {s}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
            {msgs.map((m, i) => (
              <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
                <div className={cn(
                  "max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 leading-relaxed",
                  m.role === "user" ? "bg-primary/20 text-foreground" : "bg-muted/40 text-foreground",
                )}>
                  {m.content || (m.role === "assistant" && busy ? "思考中…" : m.content)}
                </div>
              </div>
            ))}
          </div>

          {/* 输入框 + 发送 */}
          <div className="border-t border-border/60 p-3">
            <div className="flex items-end gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }}
                rows={1}
                disabled={busy}
                placeholder={busy ? "回复生成中…" : "就本页内容提问…"}
                className="flex-1 resize-none rounded-lg border border-border bg-black/20 px-3 py-2 text-sm outline-none focus:border-primary/50 disabled:opacity-60"
              />
              <button onClick={() => send(input)} disabled={!input.trim() || busy}
                className="rounded-lg bg-primary/15 p-2 text-primary hover:bg-primary/25 disabled:opacity-40">
                <Send className="h-4 w-4" />
              </button>
            </div>
          </div>
        </aside>
      )}
    </>
  );
}
