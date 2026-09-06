// useAiChat —— 一份对话的状态机（S5，移植自 Vibe-Research 的 core/ai/useAiChat）。
//
// 处理三类"看不出来但会出错"的坑：半截回答不落进下一轮、并发提交的竞态锁、
// 换 key/关面板中止在跑的请求。对话按 key 分开；空回答不算回答。
//
// 传输：AiSend 把一轮 prompt 发给后端会话运行时，读 SSE 到本轮结束，返回最终文本。
// （流式增量由 onDelta 回调实时吐出，界面可逐字显示；最终以落库文本为准。）

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiUrl } from "@/lib/base";
import { authHeaders } from "@/lib/api";

export interface AiMsg {
  role: "user" | "assistant";
  content: string;
  /** 没收完就被中止的回答：界面照常显示已拿到的部分，但不进下一轮。 */
  partial?: boolean;
}

export interface AiChat {
  msgs: AiMsg[];
  key: string;
  loading: boolean;
  err: string | null;
  submit: (text: string, decorate?: (q: string) => string) => Promise<void>;
  clear: () => void;
  abort: () => void;
}

// 对话 key → 后端 session：每个 chat（key#epoch）惰性建一个后端会话并缓存复用（见 _sessionCache）。

interface SseEvent { event: string; data: unknown; }

async function* readSse(resp: Response, signal: AbortSignal): AsyncGenerator<SseEvent> {
  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  try {
    while (true) {
      if (signal.aborted) return;
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buf.indexOf("\n\n")) !== -1) {
        const frame = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        let event = "message";
        const dataLines: string[] = [];
        for (const line of frame.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
        }
        if (dataLines.length === 0) continue;
        let data: unknown = null;
        try { data = JSON.parse(dataLines.join("\n")); } catch { data = dataLines.join("\n"); }
        yield { event, data };
      }
    }
  } finally {
    reader.cancel().catch(() => {});
  }
}

/**
 * 一轮对话：建/复用后端会话（session id 由 key+epoch 决定）→ 连 SSE → 发消息 →
 * text_delta 经 onDelta 实时吐出 → turn_end/message committed 收尾，返回最终文本。
 */
async function runTurn(
  sessionId: string,
  prompt: string,
  signal: AbortSignal,
  onDelta: (t: string) => void,
): Promise<string> {
  // 用固定 session id：后端 get_session 找不到就先建。这里直接建一个带该 id 的会话不可行
  // （后端 create_session 自生成 id），故改为：每个 chat 用后端自生成 id，缓存在闭包外。
  const streamResp = await fetch(apiUrl(`/api/sessions/${sessionId}/stream`), {
    headers: { ...authHeaders() },
    signal,
  });
  if (!streamResp.ok || !streamResp.body) throw new Error(`连接会话流失败 HTTP ${streamResp.status}`);
  const postResp = await fetch(apiUrl(`/api/sessions/${sessionId}/messages`), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ content: prompt }),
    signal,
  });
  if (!postResp.ok) throw new Error(`发送消息失败 HTTP ${postResp.status}`);

  const parts: string[] = [];
  let finalText = "";
  for await (const { event, data } of readSse(streamResp, signal)) {
    const p = (data && typeof data === "object" ? data : {}) as Record<string, unknown>;
    if (event === "text_delta") {
      const t = p.text;
      if (typeof t === "string" && t) { parts.push(t); onDelta(t); }
    } else if (event === "error") {
      throw new Error(typeof p.error === "string" ? p.error : "agent 出错");
    } else if (event === "turn_end") {
      if (typeof p.final_text === "string") finalText = p.final_text;
    } else if (event === "message/committed") {
      if (typeof p.content === "string" && p.content) finalText = p.content;
      break;
    }
  }
  return finalText || parts.join("");
}

// 每个 chat key 对应一个后端 session id（惰性建、整生命周期复用；clear 时经 epoch 换新）。
const _sessionCache = new Map<string, string>();

async function ensureBackendSession(cacheKey: string, signal: AbortSignal): Promise<string> {
  const cached = _sessionCache.get(cacheKey);
  if (cached) return cached;
  const resp = await fetch(apiUrl("/api/sessions"), { method: "POST", headers: { ...authHeaders() }, signal });
  if (!resp.ok) throw new Error(`建会话失败 HTTP ${resp.status}`);
  const sid = (await resp.json()).session_id as string;
  _sessionCache.set(cacheKey, sid);
  return sid;
}

export function useAiChat(key: string): AiChat {
  const [epoch, setEpoch] = useState(0);
  const [chat, setChat] = useState<{ key: string; msgs: AiMsg[] }>({ key, msgs: [] });
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const submittingRef = useRef<AbortController | null>(null);
  const keyRef = useRef(key);
  keyRef.current = key;

  const setMsgs = useCallback(
    (updater: AiMsg[] | ((prev: AiMsg[]) => AiMsg[])) =>
      setChat((c) => ({ key: c.key, msgs: typeof updater === "function" ? updater(c.msgs) : updater })),
    [],
  );

  // 换 key = 换一份对话：中止在跑的请求，清空当前显示（各 chat 的后端会话在 _sessionCache 里独立）。
  useEffect(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    submittingRef.current = null;
    setLoading(false);
    setErr(null);
    setChat({ key, msgs: [] });
  }, [key]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const abort = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    submittingRef.current = null;
    setLoading(false);
  }, []);

  const clear = useCallback(() => {
    abort();
    setErr(null);
    setMsgs([]);
    // 后端也换一条线程：清掉缓存的 session id + epoch+1，下次 submit 建新会话。
    _sessionCache.delete(`${keyRef.current}#${epoch}`);
    setEpoch((e) => e + 1);
  }, [abort, setMsgs, epoch]);

  const cacheKey = useMemo(() => `${key}#${epoch}`, [key, epoch]);
  const cacheKeyRef = useRef(cacheKey);
  cacheKeyRef.current = cacheKey;

  const submit = useCallback(
    async (text: string, decorate?: (q: string) => string) => {
      const q = text.trim();
      if (!q || loading || submittingRef.current) return;
      const ac = new AbortController();
      submittingRef.current = ac;
      setErr(null);
      setMsgs((m) => [...m, { role: "user", content: q }, { role: "assistant", content: "", partial: true }]);
      setLoading(true);

      const patchLast = (fn: (m: AiMsg) => AiMsg) =>
        setMsgs((m) => m.map((msg, i) => (i === m.length - 1 && msg.role === "assistant" ? fn(msg) : msg)));

      abortRef.current?.abort();
      abortRef.current = ac;
      const startedKey = keyRef.current;
      const alive = () => abortRef.current === ac && !ac.signal.aborted;

      try {
        const sid = await ensureBackendSession(cacheKeyRef.current, ac.signal);
        const reply = await runTurn(sid, decorate ? decorate(q) : q, ac.signal, (t) => {
          // 实时增量：只在本请求仍是当前请求时追加（避免迟到增量写进别的对话）。
          if (alive()) patchLast((m) => ({ ...m, content: m.content + t }));
        });
        if (alive()) {
          if (!reply.trim()) throw new Error("模型没有返回内容（空回答）");
          patchLast((m) => {
            const { partial: _drop, ...rest } = m;
            return { ...rest, content: reply };
          });
        }
      } catch (e) {
        const superseded = abortRef.current !== null && abortRef.current !== ac;
        if (!superseded && keyRef.current === startedKey) {
          setMsgs((m) => {
            const last = m[m.length - 1];
            if (!last || last.role !== "assistant" || last.content) return m;
            return m.slice(0, m[m.length - 2]?.role === "user" ? -2 : -1);
          });
          if (!ac.signal.aborted) setErr(e instanceof Error ? e.message : "对话失败");
        }
      } finally {
        if (submittingRef.current === ac) submittingRef.current = null;
        if (abortRef.current === ac) {
          abortRef.current = null;
          setLoading(false);
        }
      }
    },
    [loading, setMsgs],
  );

  return { msgs: chat.msgs, key: chat.key, loading, err, submit, clear, abort };
}
