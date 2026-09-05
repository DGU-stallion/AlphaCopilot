import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { AiPageProvider } from "@/lib/ai-page-context";
import { StockPoolPage } from "@/pages/StockPoolPage";

/** 股票池 CRUD：列出 → 加入 → 移除，全部走 /api/stock-pool（mock fetch）。 */

let pool: { id: string; code: string; name: string; note: string; tags: string }[] = [];

function renderPage() {
  return render(
    <AiPageProvider>
      <MemoryRouter>
        <StockPoolPage />
      </MemoryRouter>
    </AiPageProvider>,
  );
}

describe("StockPoolPage CRUD", () => {
  beforeEach(() => {
    pool = [];
    global.fetch = vi.fn(async (url: string, opts?: RequestInit) => {
      if (url === "/api/stock-pool" && (!opts || opts.method === undefined || opts.method === "GET")) {
        return new Response(JSON.stringify(pool), { status: 200 });
      }
      if (url === "/api/stock-pool" && opts?.method === "POST") {
        const body = JSON.parse(opts.body as string);
        pool = [{ id: "sp-1", code: body.code, name: body.name ?? "", note: "", tags: body.tags ?? "" }];
        return new Response(JSON.stringify({ id: "sp-1", code: body.code }), { status: 200 });
      }
      if (url.startsWith("/api/stock-pool/") && opts?.method === "DELETE") {
        pool = [];
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      }
      return new Response("[]", { status: 200 });
    }) as unknown as typeof fetch;
  });

  it("加入标的后列表出现，移除后消失", async () => {
    renderPage();
    // 初始为空
    await screen.findByText("股票池为空，先加入标的。");

    fireEvent.change(screen.getByLabelText("代码"), { target: { value: "600519" } });
    fireEvent.change(screen.getByLabelText("名称"), { target: { value: "贵州茅台" } });
    fireEvent.click(screen.getByText("加入"));

    // 列表出现该标的
    await screen.findByText("600519");
    expect(screen.getByText("贵州茅台")).toBeTruthy();

    // 移除
    fireEvent.click(screen.getByLabelText("移除 600519"));
    await waitFor(() => expect(screen.queryByText("600519")).toBeNull());
  });
});
