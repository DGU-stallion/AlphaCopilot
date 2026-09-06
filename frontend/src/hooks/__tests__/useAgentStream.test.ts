// S5: useAgentStream hook 单测 —— mock fetch 走「建会话 → 连流 → 发消息 → SSE 收 delta」链路。
// 验证：text_delta 增量累积进 assistant 气泡；turn_end/message committed 收尾以最终文本为准；
// error 事件把错误落进气泡 + error 态；会话复用（第二次 send 不再新建 session）。

import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useAgentStream } from "@/hooks/useAgentStream";

function sseResponse(frames: string[]): Response {
  const encoder = new TextEncoder();
  let i = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i < frames.length) {
        controller.enqueue(encoder.encode(frames[i]));
        i += 1;
      } else {
        controller.close();
      }
    },
  });
  return new Response(stream, { status: 200, headers: { "content-type": "text/event-stream" } });
}

function jsonResponse(obj: unknown): Response {
  return new Response(JSON.stringify(obj), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

afterEach(() => vi.restoreAllMocks());

describe("useAgentStream", () => {
  it("建会话 → 连流 → 发消息，text_delta 累积进 assistant 气泡，收尾以最终文本为准", async () => {
    const calls: string[] = [];
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (url.endsWith("/api/sessions") && init?.method === "POST") return jsonResponse({ session_id: "s-1" });
      if (url.includes("/stream")) {
        return sseResponse([
          'event: text_delta\ndata: {"text":"白酒"}\n\n',
          'event: text_delta\ndata: {"text":"板块"}\n\n',
          'event: turn_end\ndata: {"final_text":"白酒板块是消费龙头。","finish_reason":"completed"}\n\n',
          'event: message/committed\ndata: {"content":"白酒板块是消费龙头。"}\n\n',
        ]);
      }
      if (url.includes("/messages") && init?.method === "POST") return jsonResponse({ ok: true });
      throw new Error(`unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useAgentStream());
    await act(async () => {
      await result.current.send("白酒板块怎么样？", "指数: 3000");
    });

    expect(result.current.messages[0]).toEqual({ role: "user", content: "白酒板块怎么样？" });
    expect(result.current.messages[1]).toEqual({ role: "assistant", content: "白酒板块是消费龙头。" });
    expect(result.current.busy).toBe(false);
    expect(result.current.error).toBeNull();
    // 链路顺序 + 页面快照进 prompt
    expect(calls[0]).toBe("POST /api/sessions");
    const msgCall = fetchMock.mock.calls.find(
      ([u, i]) => String(u).includes("/messages") && (i as RequestInit)?.method === "POST",
    );
    const body = JSON.parse((msgCall![1] as RequestInit).body as string);
    expect(body.content).toContain("指数: 3000");
    expect(body.content).toContain("白酒板块怎么样？");
  });

  it("error 事件把错误落进 error 态并给出提示气泡", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/api/sessions") && init?.method === "POST") return jsonResponse({ session_id: "s-err" });
      if (url.includes("/stream")) return sseResponse(['event: error\ndata: {"error":"上游模型 500"}\n\n']);
      if (url.includes("/messages")) return jsonResponse({ ok: true });
      throw new Error(`unexpected: ${url}`);
    }));

    const { result } = renderHook(() => useAgentStream());
    await act(async () => {
      await result.current.send("你好");
    });
    await waitFor(() => expect(result.current.error).toContain("上游模型 500"));
    expect(result.current.messages[1].content).toContain("上游模型 500");
  });

  it("会话复用：第二次 send 不再新建 session", async () => {
    let created = 0;
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/api/sessions") && init?.method === "POST") { created += 1; return jsonResponse({ session_id: "s-reuse" }); }
      if (url.includes("/stream")) return sseResponse(['event: message/committed\ndata: {"content":"ok"}\n\n']);
      if (url.includes("/messages")) return jsonResponse({ ok: true });
      throw new Error(`unexpected: ${url}`);
    }));

    const { result } = renderHook(() => useAgentStream());
    await act(async () => { await result.current.send("一"); });
    await act(async () => { await result.current.send("二"); });
    expect(created).toBe(1);
  });
});
