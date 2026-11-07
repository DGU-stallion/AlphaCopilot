// useAiChat —— 一份对话的状态机（S5，移植自上游项目的 core/ai/useAiChat）。
//
// 处理三类"看不出来但会出错"的坑：半截回答不落进下一轮、并发提交的竞态锁、
// 换 key/关面板中止在跑的请求。对话按 key 分开；空回答不算回答。
//
// 传输：AiSend 把一轮 prompt 发给后端会话运行时，读 SSE 到本轮结束，返回最终文本。
// （流式增量由 onDelta 回调实时吐出，界面可逐字显示；最终以落库文本为准。）

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiUrl } from "@/lib/base";
import { authHeaders, type SessionMessage } from "@/lib/api";

export interface AiMsg {
  role: "user" | "assistant";
  content: string;
  /** 没收完就被中止的回答：界面照常显示已拿到的部分，但不进下一轮。 */
  partial?: boolean;
  /**
   * 思考过程 / 工具调用（可选）。从库里读历史时带上，流式的新消息暂不填。
   * 形如 `{thinking?: string; tool_calls?: [...]}`，渲染交给 ChatMessage。
   */
  meta?: { thinking?: string; tool_calls?: { name: string; args?: string; result?: string }[] };
}

export interface AiChat {
  msgs: AiMsg[];
  key: string;
  /** 当前对话对应的后端会话 id。切历史会话时由调用方传入，未建时为 null。 */
  sessionId: string | null;
  loading: boolean;
  /**
   * 正在读历史消息（与 `loading` 严格分开）。
   *
   * 为什么必须分开：`loading` 的语义是「agent 正在回答」，submit 会因它而拒绝
   * 新输入。曾经把「读历史」也塞进 `loading`，后果是打开一条历史会话后
   * 第一时间打字发送 → 被静默吞掉（`submit` 直接 return，连报错都没有）。
   * 界面看起来完全正常，只是没反应 —— 这种 bug 用户只会以为是「应用卡了」。
   */
  historyLoading: boolean;
  err: string | null;
  submit: (text: string, decorate?: (q: string) => string) => Promise<void>;
  clear: () => void;
  abort: () => void;
}

/**
 * 对话的挂载点。
 *
 * `sessionId` 非空 = **打开一条已有会话**（C4 历史切换）：直接把消息从库里读出来，
 * 后续 submit 续在同一条会话上，不新建。
 *
 * 为什么读库而不是读 Pi 的 session JSONL：硬规则 2 —— 产品真源是我们的数据库，
 * 前端永不读 agent 的会话文件。
 */
export interface AiChatOptions {
  sessionId?: string | null;
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

export function useAiChat(key: string, opts: AiChatOptions = {}): AiChat {
  const fixedSid = opts.sessionId ?? null;
  const [epoch, setEpoch] = useState(0);
  const [chat, setChat] = useState<{ key: string; msgs: AiMsg[] }>({ key, msgs: [] });
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
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

  // 固定会话：给了 sessionId 就直接用，不再懒建（否则「打开历史会话」会新建一条空的，
  // 用户看到的是空白页、以为历史丢了）。
  const fixedSidRef = useRef(fixedSid);
  fixedSidRef.current = fixedSid;

  /**
   * 历史加载的「作废令牌」。
   *
   * 真 bug（写完测试才暴露）：读历史的请求比「用户手速」慢。用户打开历史会话后
   * 立刻打字发送，历史响应随后到达，`setChat({msgs: rows})` 把刚发出的消息
   * **整段覆盖成历史内容**（历史为空时就是覆盖成空）—— 界面表现是「我发的消息
   * 消失了」，而且 agent 那条其实还在跑，答完又冒出来，非常难解释。
   *
   * 修法：任何 submit 都让令牌 +1；历史响应落地前比对令牌，不一致就整段丢弃
   * （历史没读到不致命，覆盖掉用户刚发的话才致命）。
   */
  const historyTokenRef = useRef(0);

  /**
   * 打开一条已有会话：把落库的消息读回来。
   *
   * `partial` 一律不置 —— 历史消息都是已完成的，标成 partial 会让界面显示
   * 「还没回答完」的光标，且会被 submit 的替补逻辑误删。
   */
  useEffect(() => {
    if (!fixedSid) return;
    let alive = true;
    const token = ++historyTokenRef.current;
    setChat({ key, msgs: [] });
    setHistoryLoading(true);
    setErr(null);
    (async () => {
      try {
        const resp = await fetch(apiUrl(`/api/sessions/${fixedSid}/messages`), {
          headers: { ...authHeaders() },
        });
        if (!resp.ok) throw new Error(`读取会话历史失败 HTTP ${resp.status}`);
        const rows = (await resp.json()) as SessionMessage[];
        // 期间用户已经发过消息 → 令牌变了 → 丢弃这份历史（见 historyTokenRef 注释）
        if (!alive || historyTokenRef.current !== token) return;
        setChat({
          key,
          msgs: rows.map((r) => ({
            role: r.role,
            content: r.content ?? "",
            ...(r.meta ? { meta: r.meta } : {}),
          })),
        });
      } catch (e) {
        if (alive) setErr(e instanceof Error ? e.message : "读取会话历史失败");
      } finally {
        if (alive) setHistoryLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [fixedSid, key]);

  const submit = useCallback(
    async (text: string, decorate?: (q: string) => string) => {
      const q = text.trim();
      if (!q || loading || submittingRef.current) return;
      const ac = new AbortController();
      submittingRef.current = ac;
      // 让在飞的历史请求作废：否则它落地时会把这条刚发出的消息覆盖掉。
      historyTokenRef.current += 1;
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
        const sid =
          fixedSidRef.current ?? (await ensureBackendSession(cacheKeyRef.current, ac.signal));
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

  return {
    msgs: chat.msgs,
    key: chat.key,
    sessionId: fixedSid,
    loading,
    historyLoading,
    err,
    submit,
    clear,
    abort,
  };
}
