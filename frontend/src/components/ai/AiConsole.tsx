// 全局 AI 助手面板（S5）—— 右下浮标点开一块**可调整大小**的顶层对话面板。
//
// 样式/交互对齐 Vibe-Research 的 AiConsole：玻璃暖橙、markdown 回答、拖拽改大小、
// 尺寸持久化。作为页面最上层组件（fixed + 高 z-index），页面感知快照作对话上下文。
//
// 与 AiConsole 的差异：Vibe 那块是从底部把内容挤上去；这里按用户要求做成右下角
// **浮层**（不挤内容），但保留"可拖拽调整大小 + 尺寸记住"的核心体验。

import { useEffect, useRef, useState } from "react";
import { Sparkles, X, Trash2, Maximize2 } from "lucide-react";
import { useCurrentAiPage } from "@/lib/ai-page";
import { useAiChat } from "@/hooks/useAiChat";
import { AiMessages, AiComposer } from "@/components/ai/AiMessages";

const MIN_W = 340;
const MIN_H = 380;
const DEFAULT_W = 460;
const DEFAULT_H = 560;
const SIZE_KEY = "ac-ai-console-size";

const readSize = (): { w: number; h: number } => {
  try {
    const raw = localStorage.getItem(SIZE_KEY);
    if (raw) {
      const s = JSON.parse(raw);
      if (Number.isFinite(s.w) && Number.isFinite(s.h) && s.w >= MIN_W && s.h >= MIN_H) return s;
    }
  } catch { /* 默认 */ }
  return { w: DEFAULT_W, h: DEFAULT_H };
};

export function AiConsole() {
  const page = useCurrentAiPage();
  const [open, setOpen] = useState(false);
  // 对话按当前页 key 分开（换页换一份），页面没登记时用固定 "global" 长期对话。
  const chat = useAiChat(page?.key ?? "global");
  const [size, setSize] = useState(readSize);
  const dragRef = useRef<{ x: number; y: number; w: number; h: number } | null>(null);
  const sizeRef = useRef(size);
  sizeRef.current = size;

  const { abort } = chat;

  // 面板开着时 Esc 收起（并中止在跑的请求）
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { abort(); setOpen(false); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, abort]);

  // 拖左上角改大小。监听挂 window 上（鼠标易划出把手）。
  useEffect(() => {
    const move = (e: MouseEvent) => {
      const d = dragRef.current;
      if (!d) return;
      // 面板锚在右下角，向左上拖 = 变大：宽随 (d.x - e.clientX) 增，高随 (d.y - e.clientY) 增。
      const w = Math.min(Math.max(d.w + (d.x - e.clientX), MIN_W), window.innerWidth - 40);
      const h = Math.min(Math.max(d.h + (d.y - e.clientY), MIN_H), window.innerHeight - 40);
      const next = { w, h };
      sizeRef.current = next;
      setSize(next);
    };
    const up = () => {
      if (!dragRef.current) return;
      dragRef.current = null;
      try { localStorage.setItem(SIZE_KEY, JSON.stringify(sizeRef.current)); } catch { /* 下次回默认 */ }
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
  }, []);

  // 把本页确定性数据快照作上下文；空时如实说明，不让模型凭空作答。
  const decorate = (q: string) => {
    if (!page) return q;
    const body = page.context
      ? page.context
      : "（这一页的数据还没取到 / 是空的。请如实说明看不到本页数据，不要凭一般知识作答。）";
    return `【当前页面：${page.title}】\n${body}\n\n【问题】\n${q}`;
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
        <aside
          style={{ width: size.w, height: size.h }}
          className="glass fixed bottom-20 right-5 z-50 flex max-h-[calc(100vh-2rem)] max-w-[calc(100vw-2.5rem)] flex-col overflow-hidden rounded-2xl border border-primary/30"
        >
          {/* 左上角拖拽把手：改大小 */}
          <div
            onMouseDown={(e) => { dragRef.current = { x: e.clientX, y: e.clientY, w: size.w, h: size.h }; }}
            title="拖动调整大小"
            className="group absolute left-0 top-0 z-10 flex h-5 w-5 cursor-nwse-resize items-center justify-center"
          >
            <Maximize2 className="h-3 w-3 rotate-90 text-muted-foreground/40 transition-colors group-hover:text-primary" />
          </div>

          {/* 头部：标题 + 当前页面 + 清空 + 关闭 */}
          <div className="flex items-center justify-between gap-2 border-b border-border/60 py-2.5 pl-6 pr-3.5">
            <div className="min-w-0">
              <span className="flex items-center gap-2 text-sm font-semibold text-glow">
                <Sparkles className="h-4 w-4 shrink-0 text-primary" /> AI 助手
                <span data-agent-runtime className="hidden items-center gap-1.5 rounded-full border border-success/20 bg-success/[0.07] px-2 py-0.5 text-[10px] font-medium text-muted-foreground sm:inline-flex">
                  <span className="h-1.5 w-1.5 rounded-full bg-success shadow-[0_0_7px_hsl(var(--success)/0.65)]" />
                  agnes · 本地运行
                </span>
              </span>
              <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                {page ? `就「${page.title}」这一页聊` : "（这一页暂无可聊内容，可问通用问题）"}
              </span>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              {chat.msgs.length > 0 && (
                <button onClick={chat.clear} title="清空对话" aria-label="清空对话"
                  className="text-muted-foreground hover:text-foreground">
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
              <button onClick={() => { abort(); setOpen(false); }} aria-label="关闭"
                className="text-muted-foreground hover:text-foreground">
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          <AiMessages
            msgs={chat.msgs}
            loading={chat.loading}
            err={chat.err}
            notice="问我关于本页数据的问题。我基于当前页面的确定性数据为你解释，只做客观分析，不构成投资建议。"
            suggestions={page?.suggestions}
            onPick={(x) => void chat.submit(x, decorate)}
          />
          <AiComposer
            placeholder={chat.loading ? "回复生成中…" : "就本页内容提问…"}
            disabled={chat.loading}
            onSend={(t) => void chat.submit(t, decorate)}
          />
        </aside>
      )}
    </>
  );
}
