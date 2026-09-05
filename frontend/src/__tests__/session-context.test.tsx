import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { useState } from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { SessionProvider, useSession } from "@/session-context";

/**
 * 直接测被提升到 AppShell 层的 SessionContext：
 * 消费组件挂载/卸载/再挂载后，session_id 与消息列表保持不变，
 * 证明状态存在于 Provider 而非消费组件（关键不变量）。
 */

class FakeEventSource {
  constructor(public url: string) {}
  addEventListener() {}
  close() {}
}

/** 可挂载/卸载的消费者：读 session_id、消息数，并能种入一条消息。 */
function Consumer() {
  const { sessionId, messages, setMessages } = useSession();
  return (
    <div>
      <span data-testid="sid">{sessionId ?? ""}</span>
      <span data-testid="count">{messages.length}</span>
      <button
        onClick={() =>
          setMessages((prev) => [
            ...prev,
            { id: "m1", role: "user", content: "hi" },
          ])
        }
      >
        seed
      </button>
    </div>
  );
}

function Harness() {
  const [mounted, setMounted] = useState(true);
  return (
    <SessionProvider>
      <button onClick={() => setMounted(!mounted)}>toggle</button>
      {mounted && <Consumer />}
    </SessionProvider>
  );
}

describe("SessionContext 会话不丢", () => {
  beforeEach(() => {
    // @ts-expect-error override for test
    global.EventSource = FakeEventSource;
    global.fetch = vi.fn(async (url: string, opts?: RequestInit) => {
      if (url === "/api/sessions" && opts?.method === "POST") {
        return new Response(JSON.stringify({ session_id: "s-fixed" }), {
          status: 200,
        });
      }
      return new Response("[]", { status: 200 });
    }) as unknown as typeof fetch;
  });

  it("消费者卸载再挂载后 session_id 与消息不变", async () => {
    render(<Harness />);
    await waitFor(() =>
      expect(screen.getByTestId("sid").textContent).toBe("s-fixed"),
    );

    // 种入一条消息
    fireEvent.click(screen.getByText("seed"));
    expect(screen.getByTestId("count").textContent).toBe("1");

    // 卸载消费者（模拟 panel 关闭）
    fireEvent.click(screen.getByText("toggle"));
    expect(screen.queryByTestId("sid")).toBeNull();

    // 重新挂载消费者（模拟 panel 再开）
    fireEvent.click(screen.getByText("toggle"));

    // 关键：session_id 与消息数保持不变
    expect(screen.getByTestId("sid").textContent).toBe("s-fixed");
    expect(screen.getByTestId("count").textContent).toBe("1");
  });
});
