/**
 * ChatMessage 组件测试（ROUND3 C5）。
 *
 * 钉住四件事：
 *   1. markdown 结构（h2/li/code）由 parseMarkdown 渲染，**没有 dangerouslySetInnerHTML**；
 *   2. user / assistant 视觉与位置区分（data-role + 对齐）；
 *   3. thinking / tool_calls 折叠块默认收起（details 无 open），点开后可见；
 *   4. 代码块「复制」调 clipboard.writeText，失败静默；XSS 链接不落 <a>。
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { DARK } from "@/theme/tokens";
import { ChatMessage } from "@/components/agent/ChatMessage";

function openDetails(summaryText: string | RegExp): HTMLElement {
  const summary = screen.getByText(summaryText);
  expect(summary.tagName).toBe("SUMMARY");
  fireEvent.click(summary);
  return summary;
}

describe("隐藏契约：不用 dangerouslySetInnerHTML", () => {
  it("源码里不出现 dangerouslySetInnerHTML", async () => {
    // 只查「有没有真的用」，不是「文件里出现过这个词」：
    // 注释里写着「禁止 dangerouslySetInnerHTML」也是这个词 —— 朴素 includes 会
    // 把**说明纪律的注释**判成违规，逼着人删掉解释。那种测试只会被绕过，
    // 不会被执行。所以先剥掉注释再查。
    const { readFileSync } = await import("node:fs");
    const src = readFileSync("src/components/agent/ChatMessage.tsx", "utf-8")
      .replace(/\/\*[\s\S]*?\*\//g, "")   // 块注释
      .replace(/^\s*\/\/.*$/gm, "");        // 行注释
    expect(/dangerouslySetInnerHTML\s*[=:]/.test(src)).toBe(false);
  });
});

describe("角色区分", () => {
  it("user 靠右、assistant 靠左（data-role + justifyContent）", () => {
    const u = render(<ChatMessage role="user" content="帮我跑个因子" />);
    const uEl = u.container.querySelector('[data-role="user"]') as HTMLElement;
    expect(uEl).not.toBeNull();
    expect(uEl.style.justifyContent).toBe("flex-end");

    const a = render(<ChatMessage role="assistant" content="好的" />);
    const aEl = a.container.querySelector('[data-role="assistant"]') as HTMLElement;
    expect(aEl).not.toBeNull();
    expect(aEl.style.justifyContent).toBe("flex-start");
  });

  it("assistant 的强调色来自 palette（不出现 hex 字面量的前提下仍然有区分色）", () => {
    document.documentElement.className = "dark";
    const { container } = render(
      <ChatMessage role="assistant" content="回答" />,
    );
    const el = container.querySelector('[data-role="assistant"]') as HTMLElement;
    const bubble = el.querySelector('[data-bubble="true"]') as HTMLElement;
    expect(bubble.style.borderColor).toBeTruthy();
  });
});

describe("markdown 渲染", () => {
  it("标题/列表/代码块映射成 h2/li/pre，代码块带复制按钮", () => {
    const content = "## 结论\n- 甲\n- 乙\n```ts\nconst x = 1;\n```";
    render(<ChatMessage role="assistant" content={content} />);
    expect(screen.getByText("结论").tagName).toBe("H2");
    expect(screen.getByText("甲").tagName).toBe("LI");
    expect(screen.getByText("乙").tagName).toBe("LI");
    expect(screen.getByText("const x = 1;").closest("pre")).not.toBeNull();
    expect(screen.getByText("复制").tagName).toBe("BUTTON");
  });

  it("代码块的复制按钮写入代码原文（不含 lang 标记）", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    render(<ChatMessage role="assistant" content={'```python\nprint("hi")\n```'} />);
    fireEvent.click(screen.getByText("复制"));
    expect(writeText).toHaveBeenCalledWith('print("hi")');
  });

  it("clipboard 失败静默（reject 不冒泡、组件仍在）", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    Object.assign(navigator, { clipboard: { writeText } });
    render(<ChatMessage role="assistant" content={'```\nx\n```'} />);
    fireEvent.click(screen.getByText("复制"));
    await expect(writeText.mock.results[0]?.value).rejects.toThrow();
    expect(screen.getByText("x").closest("pre")).not.toBeNull();
  });

  it("正常链接渲染 <a target=_blank rel=noopener noreferrer>", () => {
    const { container } = render(
      <ChatMessage role="assistant" content="[手册](https://example.com/doc)" />,
    );
    const a = container.querySelector("a");
    expect(a?.getAttribute("href")).toBe("https://example.com/doc");
    expect(a?.getAttribute("target")).toBe("_blank");
    expect(a?.getAttribute("rel")).toContain("noopener");
  });

  it("javascript: 链接降级为纯文本（XSS，钉子）", () => {
    const { container } = render(
      <ChatMessage role="assistant" content="[点我](javascript:alert(1))" />,
    );
    expect(container.querySelector("a")).toBeNull();
  });

  it("粗体与行内代码渲染 strong / code", () => {
    render(<ChatMessage role="assistant" content="**重仓** 且 `0.05`" />);
    expect(screen.getByText("重仓").tagName).toBe("STRONG");
    expect(screen.getByText("0.05").tagName).toBe("CODE");
  });

  it("表格包在横向滚动容器里（不撑破浮窗）", () => {
    const { container } = render(
      <ChatMessage
        role="assistant"
        content={"| a | b |\n| - | - |\n| 1 | 2 |"}
      />,
    );
    expect(container.querySelector("table")).not.toBeNull();
    const wrap = container.querySelector('[data-table-scroll="true"]') as HTMLElement;
    expect(wrap).not.toBeNull();
    expect(wrap.style.overflowX).toBe("auto");
  });
});

describe("思考过程折叠块", () => {
  it("默认收起（details 无 open），标题带字数；点开后展开内容", () => {
    const thinking = "先核对成交量。" + "再算换手率。".repeat(5);
    render(
      <ChatMessage
        role="assistant"
        content="结论：正常。"
        meta={{ thinking }}
      />,
    );
    const summary = screen.getByText(/思考过程（\d+ 字）/);
    const details = summary.closest("details");
    expect(details).not.toBeNull();
    // 默认收起
    expect((details as HTMLDetailsElement).open).toBe(false);
    // 点开
    fireEvent.click(summary);
    expect((details as HTMLDetailsElement).open).toBe(true);
    // 正文渲染在折叠块里
    expect(details?.textContent).toContain("先核对成交量。");
    const n = thinking.length;
    expect(summary.textContent).toBe(`思考过程（${n} 字）`);
  });

  it("user 消息不带 meta 时不渲染折叠块", () => {
    render(<ChatMessage role="user" content="跑一下" />);
    expect(screen.queryByText(/思考过程/)).toBeNull();
    expect(screen.queryByText(/工具调用/)).toBeNull();
  });
});

describe("工具调用折叠块", () => {
  it("默认收起，展开后显示工具名 / 参数 / 结果摘要（长结果截断）", async () => {
    const result = "row_".repeat(200) + "TAIL_" + "x".repeat(50);
    render(
      <ChatMessage
        role="assistant"
        content="查完了。"
        meta={{
          tool_calls: [
            { name: "research.daily", args: '{"symbol":"600519"}', result },
            { name: "alpha.ic" },
          ],
        }}
      />,
    );
    const summary = screen.getByText("工具调用（2）");
    const details = summary.closest("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    fireEvent.click(summary);
    expect(details.open).toBe(true);
    expect(screen.getByText("research.daily").tagName).toBe("STRONG");
    expect(details.textContent).toContain('{"symbol":"600519"}');
    // 结果是摘要：含前缀与截断省略号，不整段灌入
    expect(details.textContent).toContain("row_".repeat(20).slice(0, 80));
    expect(details.textContent).toContain("…");
    expect(details.textContent).not.toContain("TAIL_");
    // 没有参数/结果的调用不出错
    expect(screen.getByText("alpha.ic").tagName).toBe("STRONG");
  });
});

describe("流式状态", () => {
  it("streaming=true 时标记 data-streaming 且渲染光标占位", () => {
    const { container } = render(
      <ChatMessage role="assistant" content="算到一半…" streaming />,
    );
    expect(container.querySelector('[data-role="assistant"]')?.getAttribute("data-streaming")).toBe("true");
    expect(container.querySelector('[data-stream-cursor="true"]')).not.toBeNull();
  });

  it("空内容 + streaming 也能渲染占位（不白屏）", () => {
    const { container } = render(<ChatMessage role="assistant" content="" streaming />);
    expect(container.querySelector('[data-skeleton="true"]')).not.toBeNull();
  });
});
