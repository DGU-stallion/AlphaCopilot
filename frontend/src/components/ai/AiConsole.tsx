// AI 助手。两种形态，用同一个对话内核：
//
//   embedded  —— 嵌在布局右侧的常驻栏里（M2-5 之后的默认形态）。
//                位置固定、宽度由布局控制、没有浮标、不可拖拽。
//   floating  —— 右下角浮标 + **可拖动/缩放/吸附**的浮层（ROUND3 C2）。
//
// ROUND3 的取舍变了：常驻右侧栏被取消，改为浮层。原因不是我们反复，而是
// 用户在两轮反馈里说清了顺序 —— 先要「折叠后完全退出布局」（C1，因为 44px
// 竖条会永久吃掉一列宽度 → 宽表格出横向滚动），再要「浮窗可拖动/resize/吸附」（C2）。
// 右侧常驻栏与这两条不相容：它要么占宽度，要么就不是浮窗。
//
// 浮层的位置/尺寸记忆、吸附、窄屏退化全在 AgentWindow 里（单测在
// components/agent/__tests__/AgentWindow.test.tsx），这里只管对话内容。
//
// 页面感知快照作对话上下文（lib/ai-page）：embedded 与 floating 都一样。

import { useCallback, useEffect, useState } from "react";
import { Sparkles, History, Trash2 } from "lucide-react";
import { useCurrentAiPage } from "@/lib/ai-page";
import { useAiChat } from "@/hooks/useAiChat";
import { AiMessages, AiComposer } from "@/components/ai/AiMessages";
import { AgentWindow } from "@/components/agent/AgentWindow";
import { AgentSessionList } from "@/components/agent/AgentSessionList";
import { agentApi, type SessionSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

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
  // C4：历史会话。null = 跟着「当前页的对话」走（默认行为）；
  // 非 null = 用户主动打开了某条历史会话，消息从库里读。
  const [activeSid, setActiveSid] = useState<string | null>(null);
  const [showList, setShowList] = useState(false);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  // 「查不到」必须与「确实没有」分开：把一次失败的请求降级成空数组，
  // 界面就会说「还没有会话」—— 那是在撒谎（实测踩过）。
  const [sessionsErr, setSessionsErr] = useState<string | null>(null);
  const chat = useAiChat(page?.key ?? "global", { sessionId: activeSid });

  const { abort } = chat;

  // 面板开着时 Esc 收起（并中止在跑的请求）
  useEffect(() => {
    if (!open || embedded) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      // 先关会话列表再关窗：一次 Esc 直接从「历史」跳到关闭会让人丢失位置感。
      if (showList) { setShowList(false); return; }
      abort();
      setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, embedded, abort, showList]);

  // 打开「历史」时才拉会话列表（不在挂载时拉：不打无关的请求）。
  const refreshSessions = useCallback(() => {
    agentApi
      .sessions()
      .then((rows) => { setSessions(rows); setSessionsErr(null); })
      .catch((e) => {
        setSessions([]);
        setSessionsErr(e instanceof Error ? e.message : String(e));
      });
  }, []);
  useEffect(() => {
    if (showList && !embedded) refreshSessions();
  }, [showList, embedded, refreshSessions]);

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
              <span data-agent-runtime className="hidden items-center gap-1.5 rounded-[2px] border border-border px-1.5 py-0.5 text-[11px] text-muted-foreground sm:inline-flex">
                <span className="h-1.5 w-1.5 rounded-full bg-[hsl(var(--success))]" />
                agnes · 本地
              </span>
            </span>
          )}
          <span className={cn("block truncate text-[11px] text-muted-foreground", !embedded && "mt-0.5")}>
            {activeSid
              ? "历史会话"
              : page ? `就「${page.title}」这一页聊` : "（这一页暂无可聊内容，可问通用问题）"}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {chat.msgs.length > 0 && (
            <button onClick={chat.clear} title="新对话（清空当前）" aria-label="新对话"
              className="text-muted-foreground hover:text-foreground">
              <Trash2 className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {showList ? (
        <AgentSessionList
          sessions={sessions}
          activeId={activeSid}
          error={sessionsErr}
          onPick={(sid) => { setActiveSid(sid); setShowList(false); }}
          onNew={() => { setActiveSid(null); chat.clear(); setShowList(false); refreshSessions(); }}
          onDelete={(sid) => {
            // 删的是「历史会话」而不是产品数据（硬规则 2：会话是 agent 的内部记忆）。
            // 因此这里直接删；删完刷新列表，若删的是当前打开的那条就回到默认对话。
            agentApi
              .deleteSession(sid)
              .then(() => {
                if (activeSid === sid) setActiveSid(null);
                refreshSessions();
              })
              .catch(() => refreshSessions());
          }}
        />
      ) : (
      <AiMessages
        msgs={chat.msgs}
        loading={chat.loading}
        err={chat.err}
        notice="问我关于本页数据的问题。我基于当前页面的确定性数据为你解释，只做客观分析，不构成投资建议。"
        suggestions={page?.suggestions}
        onPick={(x) => void chat.submit(x, decorate)}
      />
      )}
      <AiComposer
        placeholder={
          chat.historyLoading ? "正在读历史…" : chat.loading ? "回复生成中…" : "就本页内容提问…"
        }
        // 只挡「正在回答」：读历史时仍可输入（否则用户会以为输入框坏了）。
        disabled={chat.loading}
        onSend={(t) => void chat.submit(t, decorate)}
      />
    </>
  );

  // ---------- 嵌入模式：填满父容器 ----------
  if (embedded) {
    return (
      <div className="flex h-full min-h-0 flex-col" data-agent="embedded" data-agent-console="true">
        {body}
      </div>
    );
  }

  // ---------- 浮层模式（C2：AgentWindow 负责拖动/缩放/吸附/记忆位置） ----------
  return (
    <>
      {!open && (
        <button
          onClick={() => setOpen(true)}
          aria-label="打开 AI 助手"
          title="AI 助手"
          data-region="agent-fab"
          className="fixed bottom-5 right-5 z-40 inline-flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-foreground ring-1 ring-primary/40 transition-transform hover:scale-105"
        >
          <Sparkles className="h-5 w-5" />
        </button>
      )}

      {open && (
        <AgentWindow
          title="助手"
          onClose={() => { abort(); setOpen(false); }}
          headerExtra={
            <button
              onClick={() => setShowList((v) => !v)}
              aria-label="历史会话"
              title="历史会话"
              aria-pressed={showList}
              className={cn(
                "rounded-[4px] p-1 transition-colors hover:bg-[hsl(var(--muted))]",
                showList ? "text-primary" : "text-muted-foreground hover:text-foreground",
              )}
            >
              <History className="h-4 w-4" />
            </button>
          }
        >
          <div className="flex h-full min-h-0 flex-col" data-agent="floating" data-agent-console="true">
            {body}
          </div>
        </AgentWindow>
      )}
    </>
  );
}
