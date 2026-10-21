import { useEffect, useRef, useState } from "react";
import { CornerDownLeft, Sparkles } from "lucide-react";
import { useAiChat } from "@/hooks/useAiChat";
import { useCurrentAiPage } from "@/lib/ai-page";
import { RADIUS, SIZE } from "@/theme/tokens";
import { cn } from "@/lib/utils";

/**
 * ⌘K 命令栏（M5-1）。
 *
 * 为什么需要它：助手栏在右边，要先看它、再点输入框、再打字。
 * 想快速问一句的时候，这条路径太长了。⌘K 是「随时能问」的入口。
 *
 * 与助手栏的关系：**同一个对话**（同样的 useAiChat key + 同样的页面感知），
 * 只是入口不同。不是两个 AI —— 那样用户会觉得「我在哪边说过什么」都记不住。
 *
 * 没做成「指令派发器」（输入 /backtest 就跑回测）：那是另一种产品
 * （把自然语言当命令行），而我们的定位是「问它、它解释」。
 * 真要做 Build 模式（M5-2）时再引入，那时需要的是「确认后落地」而不是命令。
 */

/** 示例问法。**必须是真能用的**，不能是占位文案 —— 用户会照着点。 */
const EXAMPLES = [
  "这三只票的 60 日滚动相关是多少",
  "今天的涨停梯队里最高几板",
  "我这个组合相对沪深300 跑赢了吗",
];

export function CommandBar() {
  const page = useCurrentAiPage();
  // 与 AiConsole 同 key：同页共用一个对话，"我刚在右边问过" 这里能看到
  const chat = useAiChat(page?.key ?? "global");
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  // ---- ⌘K / Ctrl+K 开关 ----
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();   // 否则浏览器会去搜地址栏
        // 只「打开」不「切换」：已打开时再按 ⌘K 应该保持打开并聚焦输入框，
        // 而不是关掉。（toggle 会让「想重新聚焦」的用户把栏关掉，很难理解。）
        setOpen(true);
      }
    };
    // 挂在 window 上：这是全局入口，但**故意不判断 event.target**
    // （命令栏自己就是 input，判断焦点会让「打开状态下再按 ⌘K」失效）
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Esc 关闭 + 打开时聚焦
  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.stopPropagation(); setOpen(false); }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [open]);

  const send = (q: string) => {
    const t = q.trim();
    if (!t) return;                       // 空提交会白跑一轮 agent
    // 与助手栏同样的页面上下文装饰（lib/ai-page 的快照）
    const decorated = page
      ? `【当前页面：${page.title}】\n${page.context || "（这一页的数据还没取到）"}\n\n【问题】\n${t}`
      : t;
    void chat.submit(decorated);
    setText("");
    setOpen(false);
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center bg-black/40 pt-[18vh]"
      onMouseDown={(e) => { if (e.target === e.currentTarget) setOpen(false); }}
    >
      <div
        role="dialog"
        aria-label="命令栏"
        className="w-full max-w-[620px] overflow-hidden border border-border bg-[hsl(var(--card))]"
        style={{ borderRadius: RADIUS.lg }}
      >
        <div className="flex items-start gap-2 border-b border-border px-3 py-2.5">
          <Sparkles className="mt-1 h-4 w-4 shrink-0 text-[hsl(var(--primary))]" />
          <textarea
            ref={inputRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              // Shift+Enter 留给换行；Enter 才提交
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(text);
              }
            }}
            rows={2}
            placeholder="问一句…（Enter 发送，Shift+Enter 换行，Esc 关闭）"
            className="w-full resize-none bg-transparent text-foreground outline-none placeholder:text-muted-foreground/60"
            style={{ fontSize: SIZE.md }}
          />
          <kbd className="mt-0.5 flex shrink-0 items-center gap-0.5 rounded-[2px] border border-border px-1 text-[10px] text-muted-foreground">
            <CornerDownLeft className="h-2.5 w-2.5" />
          </kbd>
        </div>

        <div className="flex flex-wrap gap-1.5 px-3 py-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              onClick={() => send(ex)}
              className={cn(
                "rounded-[2px] border border-border px-2 py-0.5 text-muted-foreground",
                "transition-colors hover:border-[hsl(var(--primary))] hover:text-foreground",
              )}
              style={{ fontSize: SIZE.xs }}
            >
              {ex}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
