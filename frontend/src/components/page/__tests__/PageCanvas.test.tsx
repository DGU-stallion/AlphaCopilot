/**
 * 页面画布（ADR-0016 决定 2）：按 spec 摆栅格 + 按 params 生成控件。
 *
 * 它是「不写 React 也能加一个分析页」的那一层：拿 spec 与 render 结果，
 * 自动排布，不需要为每个页面写 TSX。
 *
 * span 语义 = 三列栅格下占几列（契约见 backend/api/page_spec.py，span ∈ 1..3）。
 * 为什么固定三列而不是自由坐标：见 ADR-0016 决定 4（不做拖拽编辑器）。
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/page/BlockRenderer", () => ({
  BlockRenderer: ({ block }: { block: { kind: string; title?: string } }) => (
    <div data-testid="block" data-kind={block.kind}>{block.title ?? block.kind}</div>
  ),
}));

import { GRID_COLS, PageCanvas, clampSpan, packRows } from "../PageCanvas";
import type { RenderBlock } from "@/lib/research";

const b = (span: number, title: string): RenderBlock =>
  ({ kind: "chart", span, renderer: "echarts", title, option: { series: [] } }) as RenderBlock;

describe("PageCanvas 的栅格", () => {
  it("每个 block 都渲染出来，不吞块", () => {
    render(<PageCanvas blocks={[b(1, "A"), b(1, "B"), b(1, "C")]} />);
    expect(screen.getAllByTestId("block")).toHaveLength(3);
  });

  it("span 决定占几列（三列栅格），且用 flex 比例而不是 col-span 类", () => {
    const { container } = render(<PageCanvas blocks={[b(2, "宽")]} />);
    const cell = container.querySelector("[data-span]") as HTMLElement;
    expect(cell.getAttribute("data-span")).toBe("2");
    // ROUND2 §13：栅格换成 flex 比例分配后，col-span-N 不再生效（也没有这个类了）。
    // 断言的是**真实生效的**布局手段，避免测试钉住一个已废弃的类名。
    expect(cell.style.flexGrow).toBe("2");
  });

  it("span 越界（0 或 9）被夹到 1..3，不会撑破栅格", () => {
    // 后端 schema 已限制 1..3，但老 spec / 手写数据可能越界。
    // 越界值直接进 col-span-N 会得到一个不存在的 Tailwind 类 → 块宽度塌掉。
    const { container } = render(<PageCanvas blocks={[b(9, "越界"), b(0, "下界")]} />);
    const cells = container.querySelectorAll("[data-span]");
    expect(cells[0].getAttribute("data-span")).toBe("3");
    expect(cells[1].getAttribute("data-span")).toBe("1");
  });

  it("没有 block 时给出空态提示，不是白屏", () => {
    render(<PageCanvas blocks={[]} />);
    expect(screen.getByText(/还没有内容|暂无/)).toBeTruthy();
  });
});


/**
 * 切行算法（ROUND2 §13）。
 *
 * 真 bug：三列 `grid` + `col-span-N` 时，回测页 span 序列 `3,2,1,2,1,3,1` 的
 * 最后一个块独占 1/3 宽度，右边 2/3 空白 —— 读者会以为「这块图没加载完」。
 * 修法是自己切行 + flex 按比例分配，行内永远填满。
 */
describe("packRows 切行", () => {
  it("恰好填满时不拆行（用 > 而不是 >= 判断）", () => {
    // 写错成 >= 的话 [1,1,1] 会变成三行，每行一块占满整行 —— 密度全丢。
    expect(packRows([1, 1, 1])).toEqual([[0, 1, 2]]);
  });

  it("回测页的真实序列：最后一行单独一块，但它自己占满整行", () => {
    // spans = 3,2,1,2,1,3,1（builtin_pages 的 backtest 页）
    expect(packRows([3, 2, 1, 2, 1, 3, 1])).toEqual([
      [0], [1, 2], [3, 4], [5], [6],
    ]);
  });

  it("放不下就换行，不重排（顺序是作者写的叙述顺序）", () => {
    expect(packRows([2, 2])).toEqual([[0], [1]]);
    // 1+2 恰好等于 3，属于「填满」不是「放不下」
    expect(packRows([1, 2])).toEqual([[0, 1]]);
    expect(packRows([1, 1, 2])).toEqual([[0, 1], [2]]);
  });

  it("越界 span 先夹到 1..3 再切行", () => {
    expect(packRows([9])).toEqual([[0]]);
    expect(clampSpan(9)).toBe(GRID_COLS);
    expect(clampSpan(0)).toBe(1);
    expect(clampSpan(undefined)).toBe(1);
    expect(clampSpan(Number.NaN)).toBe(1);
  });

  it("空输入不产生空行", () => {
    expect(packRows([])).toEqual([]);
  });

  it("行内 span 之和永不超过列数（布局不会溢出）", () => {
    const spans = [1, 2, 3, 1, 1, 2, 3, 2, 1];
    for (const row of packRows(spans)) {
      expect(row.reduce((s, i) => s + clampSpan(spans[i]), 0)).toBeLessThanOrEqual(GRID_COLS);
    }
  });
});

describe("PageCanvas 用切行渲染", () => {
  it("每一行是一个容器，行内块用 flexGrow 按 span 分配", () => {
    const { container } = render(<PageCanvas blocks={[b(2, "A"), b(1, "B"), b(2, "C")]} />);
    const rows = container.querySelectorAll("[data-row]");
    expect(rows).toHaveLength(2);
    expect(rows[0].querySelectorAll("[data-span]")).toHaveLength(2);
    expect(rows[1].querySelectorAll("[data-span]")).toHaveLength(1);
    // 最后一行那块占满整行（flexGrow = 它自己的 span，行内只有它 → 自然填满）
    const last = rows[1].querySelector("[data-span]") as HTMLElement;
    expect(last.style.flexGrow).toBe("2");
  });
});
