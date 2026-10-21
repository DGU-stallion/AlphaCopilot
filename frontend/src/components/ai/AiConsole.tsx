// AI 助手。两种形态，用同一个对话内核：
//
//   embedded  —— 嵌在布局右侧的常驻栏里（M2-5 之后的默认形态）。
//                位置固定、宽度由布局控制、没有浮标、不可拖拽。
//   floating  —— 右下角浮标 + 可拖拽改大小的浮层（旧形态，保留给不希望
//                常驻占宽度的场景，比如全屏图表页）。
//
// 为什么从浮层改成常驻栏：浮层会压住内容、挡住表格最后一行、还得手动拖开。
// 常驻栏宽度可预期，折叠后主画布自动变宽（见 Layout.tsx）。
//
// 页面感知快照作对话上下文（lib/ai-page）：embedded 与 floating 都一样。

import { useEffect, useRef, useState } from "react";
import { Sparkles, X, Trash2, Maximize2 } from "lucide-react";
import { useCurrentAiPage } from "@/lib/ai-page";
import { useAiChat } from "@/hooks/useAiChat";
import { AiMessages, AiComposer } from "@/components/ai/AiMessages";
import { cn } from "@/lib/utils";

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

export interface AiConsoleProps {
  /**
   * 嵌入模式：填满父容器、不渲染浮标、不可拖拽改大小。
   * 由 Layout 的 Agent 栏传入。
   */
  embedded?: boolean;
}

export function AiConsole({ embedded = false }: AiConsoleProps = {}) {
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
    if (!open || embedded) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { abort(); setOpen(false); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, abort]);

  // 拖左上角改大小。监听挂 window 上（鼠标易划出把手）。
  useEffect(() => {
    if (embedded) return;   // 嵌入模式没有拖拽把手
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
  }, [embedded]);

  // 把本页确定性数据快照作上下文；空时如实说明，不让模型凭空作答。
  const decorate = (q: string) => {
    if (!page) return q;
    const body = page.context
      ? page.context
      : "（这一页的数据还没取到 / 是空的。请如实说明看不到本页数据，不要凭一般知识作答。）";
    return `【当前页面：${page.title}】\n${body}\n\n【问题】\n${q}`;
  };

  // 对话内核：两种形态共用，避免两处维护一套消息列表 / 输入框
  const body = (
    <>
      {/* 头部：标题 + 当前页面 + 清空 (+ 关闭) */}
      <div className={cn("flex items-center justify-between gap-2 border-b border-border px-3 py-2", !embedded && "py-2.5 pl-6 pr-3.5")}>
        <div className="min-w-0">
          {/* 嵌入模式：外层 Layout 已经有「助手」标题，这里不再重复一个「AI 助手」，
              只显示「就这一页聊」的上下文说明 —— 否则同一个栏里两行标题。 */}
          {!embedded && (
            <span className="flex items-center gap-2 text-[13px] font-medium">
              <Sparkles className="h-4 w-4 shrink-0 text-primary" /> AI 助手
              <span data-agent-runtime className="hidden items-center gap-1.5 rounded-[2px] border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground sm:inline-flex">
                <span className="h-1.5 w-1.5 rounded-full bg-[hsl(var(--success))]" />
                agnes · 本地
              </span>
            </span>
          )}
          <span className={cn("block truncate text-[11px] text-muted-foreground", !embedded && "mt-0.5")}>
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
          {!embedded && (
            <button onClick={() => { abort(); setOpen(false); }} aria-label="关闭"
              className="text-muted-foreground hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          )}
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
    </>
  );

  // ---------- 嵌入模式：填满父容器 ----------
  if (embedded) {
    return (
      <div className="flex h-full min-h-0 flex-col" data-agent="embedded">
        {body}
      </div>
    );
  }

  // ---------- 浮层模式 ----------
  return (
    <>
      {/* 右下角固定浮标 */}
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="打开 AI 助手"
        title="AI 助手"
        className="fixed bottom-5 right-5 z-40 inline-flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-foreground ring-1 ring-primary/40 transition-transform hover:scale-105"
      >
        <Sparkles className="h-5 w-5" />
      </button>

      {open && (
        <aside
          style={{ width: size.w, height: size.h }}
          className="fixed bottom-20 right-5 z-50 flex max-h-[calc(100vh-2rem)] max-w-[calc(100vw-2.5rem)] flex-col overflow-hidden rounded-[6px] border border-border bg-card"
        >
          {/* 左上角拖拽把手：改大小 */}
          <div
            onMouseDown={(e) => { dragRef.current = { x: e.clientX, y: e.clientY, w: size.w, h: size.h }; }}
            title="拖动调整大小"
            className="group absolute left-0 top-0 z-10 flex h-5 w-5 cursor-nwse-resize items-center justify-center"
          >
            <Maximize2 className="h-3 w-3 rotate-90 text-muted-foreground/40 transition-colors group-hover:text-primary" />
          </div>
          {body}
        </aside>
      )}
    </>
  );
}
