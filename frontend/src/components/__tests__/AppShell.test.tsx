import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { AppShell } from "@/components/AppShell";
import { ThemeProvider } from "@/theme";

/**
 * S1（ADR-0008：agent 接入推迟至 S5）验证：
 * - 右下浮标点击 → 右侧 chat panel 占位出现；再点 → 消失。
 * - 【关键】占位期不发起任何 agent provider 调用（不 POST /api/sessions、不建 SSE）。
 */

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }
  addEventListener() {}
  close() {}
}

let sessionCalls = 0;

function renderApp() {
  return render(
    <ThemeProvider>
      <MemoryRouter initialEntries={["/pages/daily-review"]}>
        <AppShell />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe("AppShell 浮标 + chat panel 占位（S1）", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionCalls = 0;
    FakeEventSource.instances = [];
    // @ts-expect-error override for test
    global.EventSource = FakeEventSource;
    global.fetch = vi.fn(async (url: string, opts?: RequestInit) => {
      if (url === "/api/sessions" && opts?.method === "POST") {
        sessionCalls += 1;
        return new Response(JSON.stringify({ session_id: `s-${sessionCalls}` }), { status: 200 });
      }
      return new Response("[]", { status: 200 });
    }) as unknown as typeof fetch;
  });

  it("浮标点击 → 占位 panel 出现；再点 → 消失", async () => {
    renderApp();
    const fab = screen.getByLabelText("对话");

    expect(screen.queryByRole("dialog")).toBeNull();

    fireEvent.click(fab);
    const panel = await screen.findByRole("dialog");
    expect(panel.getAttribute("data-placeholder")).toBe("agent-deferred-s5");
    expect(screen.getByText("AI 助手即将上线")).toBeTruthy();

    fireEvent.click(fab);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("占位期不发起任何 agent provider 调用（无 session POST、无 SSE）", async () => {
    renderApp();
    fireEvent.click(screen.getByLabelText("对话"));
    await screen.findByRole("dialog");
    // 给潜在的异步副作用一点时间
    await new Promise((r) => setTimeout(r, 50));
    expect(sessionCalls).toBe(0);
    expect(FakeEventSource.instances.length).toBe(0);
  });
});
