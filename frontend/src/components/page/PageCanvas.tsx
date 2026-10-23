/**
 * 页面画布（ADR-0016 决定 2）：按 spec 摆栅格。
 *
 * 参数与布局分离：块怎么画是 BlockRenderer 的事，参数控件是 ParamBar 的事。
 * 这个组件只做布局，一个组件只做一件事，才不会长成第二个 Backtest.tsx。
 *
 * ## 为什么不是 CSS Grid 的 `col-span-N`（ROUND2 §13 修）
 *
 * 原来的实现是三列 `grid` + 每块 `col-span-{span}`。问题出在**行尾留洞**：
 * 回测页的 span 序列是 `3,2,1,2,1,3,1` —— 前四行正好填满，最后一行只有一块
 * `span=1`，于是最后一个图表被挤在 1/3 宽度里，右边 2/3 是空白。
 * 这不是「密度不够」，是布局没收敛：读者会以为「这块图没加载完」。
 *
 * 修法不是去猜怎么重排（重排会改变阅读顺序，而报告页的顺序是有意义的），
 * 而是**自己切行 + flex 按比例分配**：
 *   - 按顺序贪心切成若干行，每行 span 之和 ≤ 3
 *   - 行内用 `flex-grow: span`，于是行内**永远填满**，无论 span 怎么组合
 *   - 例如最后一行只有 `span=1` → 它自己占满整行；`[2,1]` → 2/3 + 1/3
 *
 * 顺带解决另一个坑：`span=2` 接 `span=1` 接 `span=2` 在 grid 下会换行 +
 * 行高按最高块拉伸，导致同一行里短卡片被拉长、图上下留白。flex 行内
 * `items-stretch` 是同样的行为，但因为行切得对，不会再出现错的配对。
 */
import { BlockRenderer } from "./BlockRenderer";
import type { RenderBlock } from "@/lib/research";

/** 三列栅格。span 只能 1..3 —— 与 backend/api/page_spec.py 的 schema 一致。 */
export const GRID_COLS = 3;

/** span 归一到 1..3 的整数（缺失/NaN 当 1，超界截到 3）。 */
export function clampSpan(span: number | undefined): number {
  const n = typeof span === "number" && Number.isFinite(span) ? Math.round(span) : 1;
  return Math.min(GRID_COLS, Math.max(1, n));
}

/**
 * 按顺序把块切成行（每行 span 之和 ≤ GRID_COLS），返回每行的下标数组。
 *
 * 纯函数，单独导出是为了能脱离 React 测：布局算法的 bug 用渲染快照很难发现，
 * 用下标数组一眼就看得出「这一行是多出来的」。
 *
 * 注意**不重排**：贪心只决定「在哪里断行」，块的前后顺序原样保留。
 * 重排虽能填得更满，但会打乱作者写的叙述顺序（先总览后细节），得不偿失。
 */
export function packRows(spans: number[]): number[][] {
  const rows: number[][] = [];
  let cur: number[] = [];
  let used = 0;
  spans.forEach((raw, i) => {
    const span = clampSpan(raw);
    // 放不下就换行。用 `used + span > GRID_COLS` 而不是 `>=`：
    // 恰好填满时要留在同一行，否则每一行都会被拆成两块。
    if (used + span > GRID_COLS && cur.length > 0) {
      rows.push(cur);
      cur = [];
      used = 0;
    }
    cur.push(i);
    used += span;
  });
  if (cur.length > 0) rows.push(cur);
  return rows;
}

export function PageCanvas({ blocks }: { blocks: RenderBlock[] }) {
  if (blocks.length === 0) {
    return (
      <p className="py-16 text-center text-[12px] text-muted-foreground/60">
        这个页面还没有内容 —— 让助手添加图表，或换一组参数重算。
      </p>
    );
  }

  const rows = packRows(
    blocks.map((b) => (typeof b.span === "number" ? b.span : 1)),
  );

  return (
    <div className="flex flex-col gap-3">
      {rows.map((row, ri) => (
        <div
          key={`row-${ri}`}
          data-row={ri}
          // 窄屏一律单列：三列在 768px 以下每块只剩 200px 出头，
          // 图表的坐标轴刻度会被裁掉（比堆叠更难看）。
          className="flex flex-col gap-3 lg:flex-row lg:items-stretch"
        >
          {row.map((i) => {
            const block = blocks[i];
            const span = clampSpan(block.span);
            return (
              <div
                key={`${block.kind}-${block.title ?? ""}-${i}`}
                data-span={span}
                // flexGrow=span 让「行内按比例分配」成立；flexBasis=0 保证
                // 分配只由比例决定，不被内容宽度带偏（默认 basis:auto 时
                // 标题长的那块会莫名变宽）。
                className="min-w-0 lg:min-w-[0px]"
                style={{ flexGrow: span, flexBasis: 0 }}
              >
                <BlockRenderer block={block} />
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
