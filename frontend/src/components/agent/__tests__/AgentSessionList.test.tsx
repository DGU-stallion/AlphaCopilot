/**
 * AgentSessionList（ROUND3 C4）。
 *
 * 会话列表的最小职责是「让人挑得出来」：
 *
 *   · 标题为空的会话要显示「未命名会话」—— 空标题渲染成一行空白，
 *     列表看上去像坏了
 *   · 要显示 message_count：只有标题和时间的话，「聊了 30 轮的」
 *     和「误点开一次空着的」长得一样
 *   · 时间用相对时间（3 分钟前）：看列表时关心的是「新不新」，
 *     不是「10月21日 14:32」
 *   · 删除按钮不能顺带切换会话（点到删除却把对话切走了，是真实会踩的坑）
 */
import { fireEvent, render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SessionSummary } from "@/lib/api";
import { AgentSessionList } from "@/components/agent/AgentSessionList";

const NOW = Date.UTC(2026, 9, 22, 12, 0, 0);
const nowSec = NOW / 1000;

function s(p: Partial<SessionSummary> & { id: string }): SessionSummary {
  return {
    title: "会话",
    runtime_session_id: null,
    created_at: nowSec,
    message_count: 0,
    ...p,
  };
}

const SESSIONS: SessionSummary[] = [
  s({ id: "s1", title: "今天的涨停梯队", created_at: nowSec - 120, message_count: 12 }),
  s({ id: "s2", title: "", created_at: nowSec - 3600 * 5, message_count: 3 }),
  s({ id: "s3", title: "老会话", created_at: nowSec - 86400 * 3, message_count: 1 }),
];

function setup(props: Partial<ComponentProps<typeof AgentSessionList>> = {}) {
  const onPick = vi.fn();
  const onDelete = vi.fn();
  const onNew = vi.fn();
  const utils = render(
    <AgentSessionList
      sessions={SESSIONS}
      activeId="s1"
      onPick={onPick}
      onDelete={onDelete}
      onNew={onNew}
      {...props}
    />,
  );
  return { ...utils, onPick, onDelete, onNew };
}

beforeEach(() => {
  // 相对时间依赖「现在」，钉住它才能断言「2 分钟前」
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
  document.documentElement.className = "dark";
});

afterEach(() => {
  vi.useRealTimers();
});

describe("渲染每一项", () => {
  it("标题 / 空标题兜底 / 条数 / 相对时间", () => {
    setup();
    expect(screen.getByText("今天的涨停梯队")).toBeTruthy();
    expect(screen.getByText("未命名会话")).toBeTruthy();
    expect(screen.getByText("12 条")).toBeTruthy();
    expect(screen.getByText("3 条")).toBeTruthy();
    expect(screen.getByText("2 分钟前")).toBeTruthy();
    expect(screen.getByText("5 小时前")).toBeTruthy();
    expect(screen.getByText("3 天前")).toBeTruthy();
  });

  it("会话数正确（不多不少）", () => {
    setup();
    expect(document.querySelectorAll("[data-session-id]").length).toBe(3);
  });

  it("当前会话高亮（aria-current），其余不高亮", () => {
    setup();
    const items = [...document.querySelectorAll("[data-session-id]")] as HTMLElement[];
    const active = items.find((el) => el.dataset.sessionId === "s1")!;
    const other = items.find((el) => el.dataset.sessionId === "s2")!;
    expect(active.getAttribute("aria-current")).toBe("true");
    expect(other.getAttribute("aria-current")).not.toBe("true");
    expect(active.className).not.toBe(other.className);
  });

  it("没有 activeId 时没有任何一项高亮", () => {
    setup({ activeId: null });
    const current = document.querySelectorAll('[aria-current="true"]');
    expect(current.length).toBe(0);
  });
});

describe("交互", () => {
  it("点某一项调用 onPick(sid)", () => {
    const { onPick } = setup();
    fireEvent.click(screen.getByText("今天的涨停梯队"));
    expect(onPick).toHaveBeenCalledWith("s1");
  });

  it("点删除只调用 onDelete，不顺带切换会话", () => {
    const { onPick, onDelete } = setup();
    fireEvent.click(screen.getByLabelText("删除会话 今天的涨停梯队"));
    expect(onDelete).toHaveBeenCalledWith("s1");
    expect(onPick).not.toHaveBeenCalled();
  });

  it("空标题的删除按钮也有可读的名字", () => {
    setup();
    expect(screen.getByLabelText("删除会话 未命名会话")).toBeTruthy();
  });

  it("「新对话」调用 onNew，且空列表时也在", () => {
    const { onNew } = setup({ sessions: [] });
    fireEvent.click(screen.getByText("新对话"));
    expect(onNew).toHaveBeenCalledTimes(1);
  });
});

describe("空列表", () => {
  it("给一句话，不白屏；也没有残留的列表项", () => {
    setup({ sessions: [], activeId: null });
    expect(document.querySelectorAll("[data-session-id]").length).toBe(0);
    expect(screen.getByText(/还没有会话/)).toBeTruthy();
  });
});

describe("时间显示不撒谎", () => {
  it("一分钟以内显示「刚刚」", () => {
    setup({ sessions: [s({ id: "x", created_at: nowSec - 10 })] });
    expect(screen.getByText("刚刚")).toBeTruthy();
  });

  it("跨年/久远的显示日期而不是「400 天前」", () => {
    setup({ sessions: [s({ id: "old", created_at: Date.UTC(2024, 0, 3, 2, 0, 0) / 1000 })] });
    // 只断言「带年份」这个事实，具体格式不锁死（本地化会变）
    expect(screen.getByText(/2024/)).toBeTruthy();
  });
});

/**
 * 「查不到」≠「确实没有」（ROUND3 C4 修 bug 后补）。
 *
 * 真 bug：列表接口路径写错 → 404 → 调用方 catch 成空数组 →
 * 界面显示「还没有会话」，而库里有 17 条。不报错、不崩，只是把
 * 一个事实换成了相反的事实。所以这里钉住：有 error 时绝不能出现
 * 「还没有会话」这句话。
 */
describe("读取失败时的表现", () => {
  it("有 error 时显示失败原因，**不显示**「还没有会话」", () => {
    const { container } = render(
      <AgentSessionList
        sessions={[]}
        activeId={null}
        onPick={() => {}}
        onDelete={() => {}}
        onNew={() => {}}
        error="读取会话历史失败 HTTP 404"
      />,
    );
    expect(container.textContent).toContain("读取会话列表失败");
    expect(container.textContent).toContain("404");
    expect(container.textContent).not.toContain("还没有会话");
    expect(container.querySelector('[data-session-error="true"]')).not.toBeNull();
  });

  it("没有 error 且确实为空时，才说「还没有会话」", () => {
    const { container } = render(
      <AgentSessionList
        sessions={[]}
        activeId={null}
        onPick={() => {}}
        onDelete={() => {}}
        onNew={() => {}}
      />,
    );
    expect(container.textContent).toContain("还没有会话");
  });
});
