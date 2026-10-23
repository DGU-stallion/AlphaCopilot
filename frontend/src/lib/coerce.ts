/**
 * 不可信输入 → 可渲染值。
 *
 * 后端数据里「没有」有四种形态：`null`、`undefined`、`NaN`、`Infinity`。
 * 它们一路漏到渲染层就是 `—` 变 `NaN`、图表变断线、排序变乱序。
 * 所有跨边界的数字先过 `finite()`，是所有地方唯一该做的收敛。
 *
 * 这个文件原本是 `lib/agent.ts`（679 行）。那个文件里 90% 是早期
 * 复盘面板用的类型声明，面板下线后只剩这两个函数，于是收拢到这里。
 */
export function finite(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** 去掉后端文本里残留的 markdown 粗体标记（`**xx**` → `xx`）。 */
export function plain(v: string | null | undefined): string {
  return (v ?? "").replace(/\*\*/g, "");
}
