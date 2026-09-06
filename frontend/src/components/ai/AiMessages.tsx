// 对话气泡区 + 输入条（S5，移植自 Vibe-Research core/ai/AiMessages）。
// 回答按 markdown 渲染（模型答的是带 **加粗**/列表/表格的正文），提问按纯文本。

import { useEffect, useRef } from "react";
import { AlertCircle, Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import type { AiMsg } from "@/hooks/useAiChat";

export interface AiMessagesProps {
  msgs: AiMsg[];
  loading: boolean;
  err: string | null;
  notice?: string;
  suggestions?: string[];
  onPick?: (s: string) => void;
}

export function AiMessages({ msgs, loading, err, notice, suggestions = [], onPick }: AiMessagesProps) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight, behavior: "smooth" });
  }, [msgs, loading]);

  return (
    <div ref={ref} className="flex-1 space-y-3 overflow-auto p-4 text-sm">
      {msgs.length === 0 && notice && (
        <div className="rounded-lg border border-primary/25 bg-primary/5 p-3 text-xs text-muted-foreground">
          {notice}
        </div>
      )}
      {msgs.map((m, i) => (
        <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
          <div className={cn(
            "max-w-[85%] rounded-2xl px-3.5 py-2 leading-relaxed",
            m.role === "user" ? "bg-primary/20 text-foreground" : "bg-muted/40 text-foreground",
          )}>
            {m.role === "assistant" ? (
              m.content ? (
                <div className="prose prose-sm dark:prose-invert max-w-none break-words text-foreground">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                </div>
              ) : (
                <span className="inline-flex items-center gap-1.5 text-muted-foreground">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> 思考中…
                </span>
              )
            ) : (
              <p className="whitespace-pre-wrap break-words">{m.content}</p>
            )}
          </div>
        </div>
      ))}
      {err && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-2 text-xs text-destructive">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" /> {err}
        </div>
      )}
      {msgs.length === 0 && suggestions.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pt-1">
          {suggestions.map((s) => (
            <button key={s} type="button" onClick={() => onPick?.(s)}
              className="rounded-full border border-border bg-muted/35 px-2.5 py-1 text-xs transition-colors hover:border-primary/40 hover:bg-primary/[0.06] hover:text-primary">
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function AiComposer({
  placeholder, disabled, onSend,
}: {
  placeholder: string;
  disabled: boolean;
  onSend: (text: string) => void;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const fire = () => {
    const v = ref.current?.value ?? "";
    if (!v.trim() || disabled) return;
    onSend(v);
    if (ref.current) ref.current.value = "";
  };
  return (
    <div className="border-t border-border/60 p-3">
      <div className="flex items-end gap-2">
        <textarea
          ref={ref}
          onKeyDown={(e) => {
            // 中文输入法选字期间的 Enter 是确认候选词，不是发送。
            if (e.nativeEvent.isComposing) return;
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); fire(); }
          }}
          rows={1}
          disabled={disabled}
          placeholder={placeholder}
          className="min-w-0 flex-1 resize-none rounded-lg border border-border bg-background/55 px-3 py-2 text-sm outline-none transition-colors focus:border-primary/50 focus:bg-background/75 disabled:opacity-60"
        />
        <button type="button" onClick={fire} disabled={disabled}
          className="shrink-0 rounded-lg bg-primary/15 px-3.5 py-2 text-primary hover:bg-primary/25 disabled:opacity-40">
          发送
        </button>
      </div>
    </div>
  );
}
