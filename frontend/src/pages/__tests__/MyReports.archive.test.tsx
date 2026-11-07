/**
 * 研报归档库（ROUND3 B4）—— 列表 / 上传 / 按 kind 预览 / 软删 + 撤销。
 *
 * 这一页最容易「看起来做完了其实没做」的地方：
 *   1. 预览器按**扩展名**猜，而不是按后端给的 `kind` → 点 PDF 得到一张碎图；
 *   2. 删除走 `window.confirm` → 确认完才想明白要留，而研报是手写的、不可再生；
 *   3. 上传按钮只把文件名塞进 state → 文件根本没发出去。
 * 所以这里测的都是行为：调了哪个 API、渲染了哪个元素、撤销有没有真的调 restore。
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({
  list: vi.fn(),
  detail: vi.fn(),
  upload: vi.fn(),
  createNote: vi.fn(),
  remove: vi.fn(),
  restore: vi.fn(),
  setMeta: vi.fn(),
  fileUrl: vi.fn((id: string) => `http://test/api/docs/${id}/file`),
}));

vi.mock("@/lib/api", () => ({ reportsApi: m }));

import { MyReports } from "../MyReports";
import type { DocRow } from "@/lib/api";

const row = (over: Partial<DocRow> & { id: string; title: string; kind: DocRow["kind"] }): DocRow => ({
  source_path: "",
  tags: "",
  file_path: "",
  bytes: 0,
  mime: "",
  created_at: 1_700_000_000,
  ...over,
});

const ROWS: DocRow[] = [
  row({ id: "d-pdf", title: "白酒研报", kind: "pdf", file_path: "d-pdf.pdf",
        source_path: "白酒研报.pdf", bytes: 2048, mime: "application/pdf", tags: "白酒" }),
  row({ id: "d-img", title: "K线截图", kind: "image", file_path: "d-img.png",
        source_path: "K线截图.png", bytes: 4096, mime: "image/png", tags: "白酒" }),
  row({ id: "d-md", title: "宏观周报", kind: "markdown", file_path: "d-md.md",
        source_path: "宏观周报.md", bytes: 512, mime: "text/markdown", tags: "宏观" }),
  row({ id: "d-note", title: "估值判断", kind: "note", tags: "宏观" }),
];

beforeEach(() => {
  vi.clearAllMocks();
  m.list.mockResolvedValue(ROWS);
  m.detail.mockResolvedValue({ ...ROWS[2], text: "# 本周宏观\n\n社融增速回升。" });
  m.upload.mockResolvedValue(ROWS[0]);
  m.createNote.mockResolvedValue(ROWS[3]);
  m.remove.mockResolvedValue({ ok: true, soft: true });
  m.restore.mockResolvedValue({ ok: true });
  m.setMeta.mockResolvedValue({ ok: true });
});

const renderPage = async () => {
  render(<MyReports />);
  await waitFor(() => expect(screen.getAllByTestId("doc-row")).toHaveLength(ROWS.length));
};

describe("归档列表", () => {
  it("挂载时拉一次列表，每条都渲染出来", async () => {
    await renderPage();
    expect(m.list).toHaveBeenCalledTimes(1);
    expect(screen.getByText("白酒研报")).toBeTruthy();
    expect(screen.getByText("估值判断")).toBeTruthy();
  });

  it("显示体量（走 <Num>，不是裸 toFixed）", async () => {
    await renderPage();
    // 2048 字节 → 2 KB
    expect(screen.getByText(/2 KB/)).toBeTruthy();
  });

  it("按标签筛选", async () => {
    await renderPage();
    fireEvent.click(screen.getByRole("button", { name: "白酒" }));
    await waitFor(() => expect(screen.getAllByTestId("doc-row")).toHaveLength(2));
  });

  it("搜索标题", async () => {
    await renderPage();
    fireEvent.change(screen.getByLabelText("搜索归档"), { target: { value: "周报" } });
    await waitFor(() => expect(screen.getAllByTestId("doc-row")).toHaveLength(1));
    expect(screen.getByText("宏观周报")).toBeTruthy();
  });
});

describe("预览按 kind 分派", () => {
  it("pdf → iframe 指向 /file", async () => {
    await renderPage();
    fireEvent.click(screen.getByText("白酒研报"));
    const frame = await screen.findByTestId("preview-pdf");
    expect(frame.getAttribute("src")).toBe("http://test/api/docs/d-pdf/file");
    expect(screen.queryByTestId("preview-image")).toBeNull();
  });

  it("image → <img> 指向 /file", async () => {
    await renderPage();
    fireEvent.click(screen.getByText("K线截图"));
    const img = await screen.findByTestId("preview-image");
    expect(img.getAttribute("src")).toBe("http://test/api/docs/d-img/file");
    expect(screen.queryByTestId("preview-pdf")).toBeNull();
  });

  it("markdown → 拉 detail 并渲染正文", async () => {
    await renderPage();
    fireEvent.click(screen.getByText("宏观周报"));
    await waitFor(() => expect(m.detail).toHaveBeenCalledWith("d-md"));
    expect(await screen.findByText("社融增速回升。")).toBeTruthy();
    expect(screen.queryByTestId("preview-pdf")).toBeNull();
  });

  it("note → 直接渲染正文，不必去要附件", async () => {
    await renderPage();
    m.detail.mockResolvedValue({ ...ROWS[3], text: "PE 分位 30%，偏低估。" });
    fireEvent.click(screen.getByText("估值判断"));
    expect(await screen.findByText("PE 分位 30%，偏低估。")).toBeTruthy();
  });
});

describe("上传", () => {
  it("选择文件 → 调 reportsApi.upload 并刷新列表", async () => {
    await renderPage();
    const file = new File(["%PDF-1.4"], "新研报.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByTestId("doc-file-input"), { target: { files: [file] } });

    await waitFor(() => expect(m.upload).toHaveBeenCalledTimes(1));
    expect(m.upload.mock.calls[0][0]).toBe(file);
    await waitFor(() => expect(m.list).toHaveBeenCalledTimes(2));
  });

  it("拖拽落文件也走同一条上传路径", async () => {
    await renderPage();
    const file = new File(["# md"], "周报.md", { type: "text/markdown" });
    fireEvent.drop(screen.getByTestId("doc-dropzone"), { dataTransfer: { files: [file] } });
    await waitFor(() => expect(m.upload).toHaveBeenCalledTimes(1));
    expect(m.upload.mock.calls[0][0]).toBe(file);
  });

  it("上传失败时显示后端给的错误文案（比如只接受 PDF / Markdown / 图片）", async () => {
    await renderPage();
    m.upload.mockRejectedValueOnce(new Error("只接受 PDF / Markdown / 图片"));
    const file = new File(["x"], "笔记.txt", { type: "text/plain" });
    fireEvent.change(screen.getByTestId("doc-file-input"), { target: { files: [file] } });
    expect(await screen.findByText(/只接受 PDF \/ Markdown \/ 图片/)).toBeTruthy();
  });

  it("写一条纯文本笔记", async () => {
    await renderPage();
    fireEvent.change(screen.getByLabelText("笔记标题"), { target: { value: "估值判断" } });
    fireEvent.change(screen.getByLabelText("笔记正文"), { target: { value: "PE 分位 30%" } });
    fireEvent.click(screen.getByRole("button", { name: "存为笔记" }));
    await waitFor(() => expect(m.createNote).toHaveBeenCalled());
    expect(m.createNote.mock.calls[0][0]).toMatchObject({ title: "估值判断", text: "PE 分位 30%" });
  });
});

describe("删除必须可撤销", () => {
  it("删除后行消失，出现 role=status 的撤销条", async () => {
    await renderPage();
    fireEvent.click(screen.getByLabelText("删除 白酒研报"));
    await waitFor(() => expect(m.remove).toHaveBeenCalledWith("d-pdf"));
    await waitFor(() => expect(screen.getAllByTestId("doc-row")).toHaveLength(3));

    const status = screen.getByRole("status");
    expect(status.textContent).toContain("白酒研报");
    expect(screen.getByRole("button", { name: "撤销" })).toBeTruthy();
  });

  it("点撤销 → 调 restore 并把行拉回来", async () => {
    await renderPage();
    fireEvent.click(screen.getByLabelText("删除 K线截图"));
    await waitFor(() => expect(m.remove).toHaveBeenCalledWith("d-img"));

    // 撤销后后端列表恢复原状（4 行）
    m.list.mockResolvedValue(ROWS);
    fireEvent.click(screen.getByRole("button", { name: "撤销" }));
    await waitFor(() => expect(m.restore).toHaveBeenCalledWith("d-img"));
    await waitFor(() => expect(screen.getAllByTestId("doc-row")).toHaveLength(4));
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("不用 window.confirm（确认弹窗防不了「确认完才发现想错了」）", async () => {
    const confirmSpy = vi.spyOn(window, "confirm");
    await renderPage();
    fireEvent.click(screen.getByLabelText("删除 估值判断"));
    await waitFor(() => expect(m.remove).toHaveBeenCalled());
    expect(confirmSpy).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});
