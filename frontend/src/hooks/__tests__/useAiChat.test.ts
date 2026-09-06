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
