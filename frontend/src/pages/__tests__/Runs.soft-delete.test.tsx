/**
 * B3：Runs 页的「软删 + 撤销」与「行内备注」。
 *
 * 验证的是真实交互后果，不是组件渲染壳子：
 *   1. 点删除 → 列表该行消失 + 出现带「撤销」的提示条（role="status"），
 *      **没有 window.confirm** —— 确认弹窗防不了「确认完才发现想错了」（硬规则 14）
 *   2. 点撤销 → restoreRun 被调、行回来
 *   3. 备注：点单元格变输入框 → 失焦保存 → setRunNote 被调
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const deleteRun = vi.fn();
const restoreRun = vi.fn();
const setRunNote = vi.fn();

vi.mock("@/lib/api", () => ({
  runsApi: {
    runs: vi.fn(),
    run: vi.fn(),
    runDiff: vi.fn(),
    views: vi.fn(),
    createView: vi.fn(),
    pinView: vi.fn(),
    deleteView: vi.fn(),
    notes: vi.fn(),
    createNote: vi.fn(),
    noteThread: vi.fn(),
    rerun: vi.fn(),
    deleteRun: (rid: string) => deleteRun(rid),
    restoreRun: (rid: string) => restoreRun(rid),
    setRunNote: (rid: string, note: string) => setRunNote(rid, note),
  },
}));

vi.mock("@/lib/ai-page", () => ({ useAiPage: vi.fn() }));
vi.mock("@/lib/data-asof", () => ({ useDataAsOfAuto: vi.fn() }));

import { runsApi } from "@/lib/api";
import { _resetCache } from "@/lib/cache";
import { Runs } from "../Runs";

const RUN = {
  id: "run-1",
  kind: "backtest",
  params: { fast: 20, slow: 60 },
  code_hash: "abc123",
  data_as_of: "2026-10-21",
  metrics: { total_return: 0.12, sharpe: 1.5 },
  artifact_ids: ["equity"],
  inputs: {},
  note: "",
  created_at: Math.floor(Date.now() / 1000),
};

/** 可变的列表数据：删除后由用例自己改，模拟服务端的软删后列表。 */
let runRows: typeof RUN[];

function rowOf(id: string): HTMLElement {
  // 行的文本以代码指纹开头，用行容器定位
  const btn = screen.getByTitle(`删除 Run ${id}`);
  return btn.closest("tr") as HTMLElement;
}

beforeEach(() => {
  runRows = [{ ...RUN }];
  vi.clearAllMocks();
  _resetCache();
  (runsApi as unknown as Record<string, unknown>).runs = vi.fn(() =>
    Promise.resolve(runRows),
  );
  // Runs 页 unconditional 拉 views（第二个 tab）—— 不给 resolved promise 会进 catch 分支
  (runsApi as unknown as Record<string, unknown>).views = vi.fn(() => Promise.resolve([]));
});

describe("Run 软删 + 撤销", () => {
  it("点删除：行消失 + 出现 role=status 的撤销提示条", async () => {
    deleteRun.mockImplementation(async () => {
      runRows = runRows.filter((r) => r.id !== "run-1"); // 模拟服务端：软删后列表不再含它
      return { ok: true, id: "run-1", soft: true };
    });
    restoreRun.mockResolvedValue({ ok: true, id: "run-1" });

    render(<Runs />);
    await waitFor(() => expect(screen.getByTitle("删除 Run run-1")).toBeTruthy());

    fireEvent.click(screen.getByTitle("删除 Run run-1"));

    await waitFor(() => expect(deleteRun).toHaveBeenCalledWith("run-1"));
    // 软删后刷新列表 —— 行不再出现
    await waitFor(() => expect(screen.queryByTitle("删除 Run run-1")).toBeNull());
    // 提示条在文档里，且可被屏幕阅读器（以及断言）找到
    const toast = await waitFor(() => {
      const t = document.querySelector('[role="status"]') as HTMLElement | null;
      expect(t).toBeTruthy();
      return t!;
    });
    expect(toast.textContent).toContain("已删除");
    expect(toast.textContent).toContain("撤销");
  });

  it("删除**不弹 window.confirm**（撤销才有恢复能力，确认框没有）", async () => {
    deleteRun.mockResolvedValue({ ok: true, id: "run-1", soft: true });
    render(<Runs />);
    await waitFor(() => expect(screen.getByTitle("删除 Run run-1")).toBeTruthy());
    const spy = vi.spyOn(window, "confirm");
    fireEvent.click(screen.getByTitle("删除 Run run-1"));
    await waitFor(() => expect(deleteRun).toHaveBeenCalled());
    expect(spy).not.toHaveBeenCalled();
  });

  it("点撤销：恢复被删的 Run，行回到列表", async () => {
    deleteRun.mockImplementation(async () => {
      runRows = runRows.filter((r) => r.id !== "run-1");
      return { ok: true, id: "run-1", soft: true };
    });
    restoreRun.mockImplementation(async () => {
      runRows = [{ ...RUN }];
      return { ok: true, id: "run-1" };
    });

    render(<Runs />);
    await waitFor(() => expect(screen.getByTitle("删除 Run run-1")).toBeTruthy());
    fireEvent.click(screen.getByTitle("删除 Run run-1"));
    await waitFor(() => expect(screen.queryByTitle("删除 Run run-1")).toBeNull());

    fireEvent.click(screen.getByText("撤销"));
    await waitFor(() => expect(restoreRun).toHaveBeenCalledWith("run-1"));
    // 撤销后刷新：行回来，提示条也收起
    await waitFor(() => expect(screen.getByTitle("删除 Run run-1")).toBeTruthy());
    await waitFor(() => expect(document.querySelector('[role="status"]')).toBeNull());
  });
});

describe("Run 行内备注", () => {
  it("点备注格变输入框，失焦保存", async () => {
    setRunNote.mockResolvedValue({ ok: true });
    render(<Runs />);
    await waitFor(() => expect(screen.getByTitle("删除 Run run-1")).toBeTruthy());

    fireEvent.click(screen.getByTitle("写备注"));
    const input = await waitFor(() =>
      screen.getByLabelText("Run 备注") as HTMLInputElement,
    );
    fireEvent.change(input, { target: { value: "想验证 fast=20 是否过拟合" } });
    fireEvent.blur(input);

    await waitFor(() =>
      expect(setRunNote).toHaveBeenCalledWith("run-1", "想验证 fast=20 是否过拟合"),
    );
    // 输入框收起，备注文本显示出来
    await waitFor(() => expect(screen.queryByLabelText("Run 备注")).toBeNull());
    await waitFor(() =>
      expect(screen.getByText("想验证 fast=20 是否过拟合")).toBeTruthy(),
    );
  });

  it("备注为空时失焦不保存（点了没改不该发一次空写）", async () => {
    setRunNote.mockResolvedValue({ ok: true });
    render(<Runs />);
    await waitFor(() => expect(screen.getByTitle("删除 Run run-1")).toBeTruthy());

    fireEvent.click(screen.getByTitle("写备注"));
    const input = await waitFor(() => screen.getByLabelText("Run 备注") as HTMLInputElement);
    fireEvent.blur(input);
    await waitFor(() => expect(screen.queryByLabelText("Run 备注")).toBeNull());
    expect(setRunNote).not.toHaveBeenCalled();
  });

  it("已有备注的 Run 显示备注内容，可再编辑", async () => {
    runRows = [{ ...RUN, note: "第一版备注" }];
    setRunNote.mockResolvedValue({ ok: true });
    render(<Runs />);
    await waitFor(() => expect(screen.getByText("第一版备注")).toBeTruthy());

    fireEvent.click(screen.getByTitle("写备注"));
    const input = await waitFor(() => screen.getByLabelText("Run 备注") as HTMLInputElement);
    expect(input.value).toBe("第一版备注");
    fireEvent.change(input, { target: { value: "第二版备注" } });
    fireEvent.blur(input);
    await waitFor(() => expect(setRunNote).toHaveBeenCalledWith("run-1", "第二版备注"));
  });
});
