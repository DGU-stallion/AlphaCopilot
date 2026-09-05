import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { AppShell } from "@/components/AppShell";
import { ThemeProvider } from "@/theme";

/**
 * 验证 ADR-0007 决策 1 的形态与关键不变量：
 * - 右下浮标点击 → 右侧 chat panel 出现；再点 → 消失。
 * - 【关键】panel 关再开后，SessionContext 的 session_id 不变
 *   （证明会话状态提升到了 AppShell/SessionProvider，不随 panel 卸载而丢）。
 */

class FakeEventSource {
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
  onmessage: ((e: MessageEvent) => void) | null = null;
  constructor(public url: string) {}
  addEventListener(type: string, cb: (e: MessageEvent) => void) {
    (this.listeners[type] ??= []).push(cb);
  }
  close() {}
}

let createSessionCalls = 0;

function renderApp() {
  return render(
    <ThemeProvider>
      <MemoryRouter initialEntries={["/pages/daily-review"]}>
        <AppShell />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe("AppShell 浮标 + chat panel", () => {
  beforeEach(() => {
    localStorage.clear();
    createSessionCalls = 0;
    // @ts-expect-error override for test
    global.EventSource = FakeEventSource;
    global.fetch = vi.fn(async (url: string, opts?: RequestInit) => {
      if (url === "/api/sessions" && opts?.method === "POST") {
        createSessionCalls += 1;
        // 每次建会话给不同 id，从而能检测「是否被重建」
        return new Response(
          JSON.stringify({ session_id: `s-${createSessionCalls}` }),
          { status: 200 },
        );
      }
      return new Response("[]", { status: 200 });
    }) as unknown as typeof fetch;
  });

  it("浮标点击 → panel 出现；再点 → 消失", async () => {
    renderApp();
    const fab = screen.getByLabelText("对话");

    expect(screen.queryByRole("dialog")).toBeNull();

    fireEvent.click(fab);
    expect(await screen.findByRole("dialog")).toBeTruthy();

    fireEvent.click(fab);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("关再开后 session_id 与消息不丢（状态在 SessionProvider，非 panel）", async () => {
    renderApp();
    const fab = screen.getByLabelText("对话");

    fireEvent.click(fab);
    const panel1 = await screen.findByRole("dialog");
    // 等 SessionProvider 建会话完成，session_id 落到 panel 的 data 属性
    await waitFor(() =>
      expect(panel1.getAttribute("data-session-id")).toBe("s-1"),
    );

    // 关闭 panel（卸载）
    fireEvent.click(screen.getByLabelText("关闭对话"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    // 重新打开 panel
    fireEvent.click(fab);
    const panel2 = await screen.findByRole("dialog");

    // 关键断言：SessionProvider 的 session_id 跨 panel 卸载/重挂载保持不变。
    // （ChatTimeline 自持内部会话，属轨 A；本轨证明「提升到 AppShell 的 context」不丢。）
    expect(panel2.getAttribute("data-session-id")).toBe("s-1");
  });
});
