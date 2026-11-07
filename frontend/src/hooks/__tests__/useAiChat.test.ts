// S5: useAiChat 单测 —— mock fetch 走「建会话 → 连流 → 发消息 → SSE 收 delta」链路。
// 验证：text_delta 累积进 assistant 气泡并以最终文本收尾；空回答被拒并回滚该轮；clear 清空。

import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useAiChat } from "@/hooks/useAiChat";

function sseResponse(frames: string[]): Response {
  const encoder = new TextEncoder();
  let i = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i < frames.length) { controller.enqueue(encoder.encode(frames[i])); i += 1; }
      else controller.close();
    },
  });
  return new Response(stream, { status: 200, headers: { "content-type": "text/event-stream" } });
}
function jsonResponse(obj: unknown): Response {
  return new Response(JSON.stringify(obj), { status: 200, headers: { "content-type": "application/json" } });
}

afterEach(() => vi.restoreAllMocks());

describe("useAiChat", () => {
  it("建会话→SSE 收 delta→收尾，assistant 气泡为最终文本；decorate 把上下文拼进 prompt", async () => {
    let sessionCount = 0;
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/api/sessions") && init?.method === "POST") { sessionCount += 1; return jsonResponse({ session_id: "s-1" }); }
      if (url.includes("/stream")) {
        return sseResponse([
          'event: text_delta\ndata: {"text":"白酒"}\n\n',
          'event: text_delta\ndata: {"text":"龙头"}\n\n',
          'event: message/committed\ndata: {"content":"白酒龙头。"}\n\n',
        ]);
      }
      if (url.includes("/messages") && init?.method === "POST") return jsonResponse({ ok: true });
      throw new Error(`unexpected: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useAiChat("page-x"));
    await act(async () => {
      await result.current.submit("白酒怎么样？", (q) => `【上下文 CTX】\n${q}`);
    });

    expect(result.current.msgs[0]).toMatchObject({ role: "user", content: "白酒怎么样？" });
    expect(result.current.msgs[1]).toMatchObject({ role: "assistant", content: "白酒龙头。" });
    expect(result.current.loading).toBe(false);
    expect(sessionCount).toBe(1);
    const msgCall = fetchMock.mock.calls.find(([u, i]) => String(u).includes("/messages") && (i as RequestInit)?.method === "POST");
    const body = JSON.parse((msgCall![1] as RequestInit).body as string);
    expect(body.content).toContain("上下文 CTX");
    expect(body.content).toContain("白酒怎么样？");
  });

  it("空回答被拒并回滚该轮（不留空气泡）", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/api/sessions") && init?.method === "POST") return jsonResponse({ session_id: "s-empty" });
      if (url.includes("/stream")) return sseResponse(['event: message/committed\ndata: {"content":""}\n\n']);
      if (url.includes("/messages")) return jsonResponse({ ok: true });
      throw new Error(`unexpected: ${url}`);
    }));
    const { result } = renderHook(() => useAiChat("page-empty"));
    await act(async () => { await result.current.submit("你好"); });
    await waitFor(() => expect(result.current.err).toContain("空回答"));
    // 空轮被回滚：user + 空 assistant 都不留
    expect(result.current.msgs).toHaveLength(0);
  });

  it("clear 清空对话", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/api/sessions") && init?.method === "POST") return jsonResponse({ session_id: "s-c" });
      if (url.includes("/stream")) return sseResponse(['event: message/committed\ndata: {"content":"ok"}\n\n']);
      if (url.includes("/messages")) return jsonResponse({ ok: true });
      throw new Error(`unexpected: ${url}`);
    }));
    const { result } = renderHook(() => useAiChat("page-clear"));
    await act(async () => { await result.current.submit("一"); });
    expect(result.current.msgs.length).toBe(2);
    act(() => { result.current.clear(); });
    expect(result.current.msgs).toHaveLength(0);
  });
});

/**
 * 打开已有会话（ROUND2 §13，C4）。
 *
 * 真风险：给了 sessionId 却仍然走「懒建新会话」，用户点历史会话看到一片空白，
 * 会以为「历史丢了」。所以这里必须断言**不会**发起 POST /api/sessions。
 */
describe("useAiChat 打开已有会话", () => {
  it("给 sessionId 时读库里的历史，且不新建会话", async () => {
    const posts: string[] = [];
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") posts.push(url);
      if (url.endsWith("/api/sessions/s-old/messages")) {
        return jsonResponse([
          { id: "m1", role: "user", content: "上次问的", created_at: 1 },
          { id: "m2", role: "assistant", content: "上次答的", created_at: 2,
            meta: { thinking: "先看白酒", tool_calls: [{ name: "get_quote", args: "600519" }] } },
        ]);
      }
      throw new Error(`unexpected: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useAiChat("global", { sessionId: "s-old" }));
    await waitFor(() => expect(result.current.msgs).toHaveLength(2));

    expect(result.current.msgs[0]).toMatchObject({ role: "user", content: "上次问的" });
    expect(result.current.msgs[1].meta?.thinking).toBe("先看白酒");
    // 历史消息都是已完成的，不能带 partial（否则界面显示"未答完"且会被替补逻辑误删）
    expect(result.current.msgs[1].partial).toBeUndefined();
    expect(result.current.sessionId).toBe("s-old");
    expect(posts.filter((u) => u.endsWith("/api/sessions"))).toEqual([]);
  });

  it("在已有会话里继续提问，续在同一条会话上（不新建）", async () => {
    const posts: string[] = [];
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") posts.push(url);
      if (url.endsWith("/api/sessions/s-old/messages") && init?.method !== "POST") {
        return jsonResponse([]);
      }
      if (url.includes("/s-old/stream")) {
        return sseResponse(['event: message/committed\ndata: {"content":"接着答"}\n\n']);
      }
      if (url.includes("/s-old/messages") && init?.method === "POST") return jsonResponse({ ok: true });
      throw new Error(`unexpected: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useAiChat("global", { sessionId: "s-old" }));
    await act(async () => { await result.current.submit("继续"); });
    expect(result.current.msgs.at(-1)?.content).toBe("接着答");
    expect(posts.filter((u) => u.endsWith("/api/sessions"))).toEqual([]);
  });
});
