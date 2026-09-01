import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { ChatTimeline } from "@/components/chat/ChatTimeline";

/**
 * 用假的 EventSource 驱动逐字流，验证 M1 行为：发一句话 → assistant 气泡逐字累加。
 * 不依赖真实后端；只测前端「chunk 累加 → 定稿」的数据通路。
 */

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
  onmessage: ((e: MessageEvent) => void) | null = null;
  url: string;
  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, cb: (e: MessageEvent) => void) {
    (this.listeners[type] ??= []).push(cb);
  }
  close() {}
  emit(type: string, data: unknown, id = "1") {
    const ev = { data: JSON.stringify(data), lastEventId: id } as MessageEvent;
    (this.listeners[type] ?? []).forEach((cb) => cb(ev));
  }
}

function deltaEvent(text: string) {
  return { type: "assistant/chunk", data: { chunk: { type: "text-delta", text } } };
}

describe("ChatTimeline (M1 逐字流)", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    // @ts-expect-error override for test
    global.EventSource = FakeEventSource;
    global.fetch = vi.fn(async (url: string, opts?: RequestInit) => {
      if (url === "/api/sessions" && opts?.method === "POST") {
        return new Response(JSON.stringify({ session_id: "s-test" }), { status: 200 });
      }
      if (url.endsWith("/messages") && opts?.method === "POST") {
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      }
      return new Response("[]", { status: 200 });
    }) as unknown as typeof fetch;
  });

  it("发一句话，assistant 气泡逐字累加并定稿", async () => {
    render(<ChatTimeline />);

    // 等会话建立（输入框从「连接中」变为可用）
    const input = (await screen.findByPlaceholderText("输入消息…")) as HTMLInputElement;

    fireEvent.change(input, { target: { value: "白酒板块怎么样？" } });
    fireEvent.click(screen.getByText("发送"));

    // 用户气泡出现
    await screen.findByText("白酒板块怎么样？");

    // 等 EventSource 建立
    await waitFor(() => expect(FakeEventSource.instances.length).toBe(1));
    const es = FakeEventSource.instances[0];
    expect(es.url).toBe("/api/sessions/s-test/stream");

    // 逐字推："茅"、"台"、"是"、"龙"、"头"
    for (const ch of ["茅", "台", "是", "龙", "头"]) {
      es.emit("assistant/chunk", deltaEvent(ch));
    }
    await screen.findByText("茅台是龙头");

    // 定稿
    es.emit("turn/final", { final_response: "茅台是龙头" });
    await waitFor(() => {
      const bubbles = screen.getAllByText("茅台是龙头");
      expect(bubbles.length).toBeGreaterThan(0);
    });
  });
});
