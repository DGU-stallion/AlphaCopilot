/**
 * Agent 会话历史的 API 路径（ROUND3 C4，修 bug 后补的回归测试）。
 *
 * 真 bug：`agentApi.sessions()` 打的是 `/api/agent/sessions`，而后端路由在
 * `/api/sessions`。404 被调用方 `catch` 吞成空数组，于是界面理直气壮地显示
 * 「还没有会话」，而库里躺着 17 条。
 *
 * 这类 bug 的可怕之处在于**不报错**：它只是把一个事实（有 17 条）替换成
 * 另一个相反的事实（一条都没有），而且看起来完全正常。
 * 所以这里既断言路径，也断言「失败不会被降级成空」。
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { agentApi } from "@/lib/api";

const calls: string[] = [];

beforeEach(() => {
  calls.length = 0;
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    calls.push(String(url));
    return new Response(JSON.stringify([]), {
      status: 200, headers: { "content-type": "application/json" },
    });
  }));
});

describe("agentApi 的路径", () => {
  it("列表打 /api/sessions（不是 /api/agent/sessions）", async () => {
    await agentApi.sessions();
    expect(calls.at(-1)).toMatch(/\/api\/sessions$/);
    expect(calls.at(-1)).not.toContain("/agent/sessions");
  });

  it("消息打 /api/sessions/{id}/messages", async () => {
    await agentApi.messages("s-1");
    expect(calls.at(-1)).toMatch(/\/api\/sessions\/s-1\/messages$/);
  });

  it("删除走 DELETE /api/sessions/{id}", async () => {
    await agentApi.deleteSession("s-1").catch(() => undefined);
    expect(calls.at(-1)).toMatch(/\/api\/sessions\/s-1$/);
  });
});

describe("会话列表的失败不能被降级成「没有会话」", () => {
  it("HTTP 500 时抛出错误（调用方才有机会区分「查不到」与「确实没有」）", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      new Response(JSON.stringify({ detail: "boom" }), {
        status: 500, headers: { "content-type": "application/json" },
      })));
    await expect(agentApi.sessions()).rejects.toThrow();
  });
});
