/**
 * ⌘K 命令栏（M5-1）。
 *
 * 它是「AI native」的入口：不用先点开助手、不用切页，输入一句话就能开始。
 * 但正因为它是入口，几条行为错了会很烦：
 *
 *   1. ⌘K / Ctrl+K 必须能开，Esc 必须能关（Mac 与 Windows 都要）
 *   2. 打开时不能抢走页面其他快捷键（比如输入框里的 ⌘K）
 *   3. 不能只在某个页面能用（它是全局的）
 *   4. 提交后要真的把问题交给对话，而不是自己拼一段文案
 *
 * 这里测行为，不测样式。
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const submitMock = vi.fn();

vi.mock("@/hooks/useAiChat", () => ({
  useAiChat: () => ({
    msgs: [],
    loading: false,
    err: null,
    submit: submitMock,
    abort: vi.fn(),
    clear: vi.fn(),
  }),
}));

import { CommandBar } from "@/components/ai/CommandBar";

function press(key: string, opts: Record<string, unknown> = {}) {
  fireEvent.keyDown(window, { key, ...opts });
}

describe("开关", () => {
  beforeEach(() => {
    submitMock.mockClear();
  });

  it("⌘K 打开", async () => {
    render(<CommandBar />);
    expect(screen.queryByRole("dialog")).toBeNull();
    press("k", { metaKey: true });
    await waitFor(() => expect(screen.getByRole("dialog")).toBeTruthy());
  });

  it("Ctrl+K 也能打开（非 Mac）", async () => {
    render(<CommandBar />);
    press("k", { ctrlKey: true });
    await waitFor(() => expect(screen.getByRole("dialog")).toBeTruthy());
  });

  it("Esc 关闭", async () => {
    render(<CommandBar />);
    press("k", { metaKey: true });
    await waitFor(() => expect(screen.getByRole("dialog")).toBeTruthy());
    press("Escape");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("在输入框里按 ⌘K 时也打开（它本来就是输入框）", async () => {
    // 这条守的是「不要因为 focus 在 input 上就忽略快捷键」——
    // 命令栏本身就是一个 input，如果加了「焦点在输入框则忽略」的判断，
    // 在命令栏已打开时再按 ⌘K 会失效（用户会以为卡住了）。
    render(<CommandBar />);
    press("k", { metaKey: true });
    const input = await screen.findByRole("textbox");
    fireEvent.keyDown(input, { key: "k", metaKey: true });
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("不按修饰键的 k 不触发（否则打字就弹窗）", async () => {
    render(<CommandBar />);
    press("k");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});

describe("提交", () => {
  beforeEach(() => submitMock.mockClear());

  it("输入内容 + Enter → 交给对话，并关闭", async () => {
    render(<CommandBar />);
    press("k", { metaKey: true });
    const input = await screen.findByRole("textbox");
    fireEvent.change(input, { target: { value: "把这三只票做 60 日滚动相关" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(submitMock).toHaveBeenCalledTimes(1));
    expect(submitMock.mock.calls[0][0]).toBe("把这三只票做 60 日滚动相关");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("空内容不提交（避免空转一轮）", async () => {
    render(<CommandBar />);
    press("k", { metaKey: true });
    const input = await screen.findByRole("textbox");
    fireEvent.keyDown(input, { key: "Enter" });
    expect(submitMock).not.toHaveBeenCalled();
  });

  it("只有空白字符也不提交", async () => {
    render(<CommandBar />);
    press("k", { metaKey: true });
    const input = await screen.findByRole("textbox");
    fireEvent.change(input, { target: { value: "   \n  " } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(submitMock).not.toHaveBeenCalled();
  });

  it("Shift+Enter 不提交（留给换行）", async () => {
    render(<CommandBar />);
    press("k", { metaKey: true });
    const input = await screen.findByRole("textbox");
    fireEvent.change(input, { target: { value: "多行" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    expect(submitMock).not.toHaveBeenCalled();
  });

  it("提交后清空输入（下次打开不该看到上次的内容）", async () => {
    render(<CommandBar />);
    press("k", { metaKey: true });
    let input = await screen.findByRole("textbox") as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "第一句" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    press("k", { metaKey: true });
    input = await screen.findByRole("textbox") as HTMLTextAreaElement;
    expect(input.value).toBe("");
  });
});

describe("示例提示", () => {
  beforeEach(() => submitMock.mockClear());

  it("展示几个可点的示例（降低「不知道能问什么」的门槛）", async () => {
    render(<CommandBar />);
    press("k", { metaKey: true });
    await screen.findByRole("dialog");
    // 示例必须是真的能用的问法，不是占位文案
    expect(screen.getByText(/滚动相关/)).toBeTruthy();
  });

  it("点示例即提交", async () => {
    submitMock.mockClear();
    render(<CommandBar />);
    press("k", { metaKey: true });
    const chip = await screen.findByText(/滚动相关/);
    fireEvent.click(chip);
    await waitFor(() => expect(submitMock).toHaveBeenCalledTimes(1));
  });
});
