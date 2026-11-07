/**
 * Page spec 的前端类型（与 backend/api/page_spec.py 的 PAGE_SPEC_SCHEMA 对应）。
 *
 * 为什么单独一个文件：spec 类型会被 PageCanvas / ParamBar / PageView / 将来的
 * spec 编辑器共用。塞在 research.ts 里会让那个文件既是「取数客户端」又是
 * 「契约定义」，两件事混在一起，改契约时容易连带改坏取数。
 */

/** 参数类型，与 alpha/registry.py 的 PARAM_TYPES 一一对应。 */
export type ParamType =
  | "symbol_list"
  | "int"
  | "float"
  | "date_range"
  | "str"
  | "enum";

export interface PageParam {
  name: string;
  type: ParamType;
  label?: string;
  default?: unknown;
  /** int/float 的下界 */
  min?: number;
  /** int/float 的上界 */
  max?: number;
  /** enum 的可选值 */
  choices?: string[];
}

export interface PageSpec {
  slug: string;
  title: string;
  kind: "builtin" | "user";
  status?: "draft" | "published";
  layout: "grid" | "stack";
  params?: PageParam[];
  blocks: {
    kind: "chart" | "table" | "markdown" | "metric";
    span?: number;
    renderer?: "lwc" | "echarts";
    analysis_ref?: { fn: string };
    artifact_id?: string;
    text?: string;
  }[];
  refresh?: { mode: "manual" | "on_open" | "cron"; cron?: string };
}

/** `GET /api/pages/{slug}` 的响应。 */
export interface PageRecord {
  id: string;
  slug: string;
  title: string;
  kind: string;
  status: string;
  spec: PageSpec;
  created_at: number;
  updated_at: number;
}

/**
 * spec.params 的默认值集合。
 *
 * 为什么单独抽：PageView 需要「初始值」和「重置」两处都要它，
 * 写在组件里就成了两处各自拼一遍，很容易漏掉某个 param。
 */
export function defaultValues(spec: PageSpec | null | undefined): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const p of spec?.params ?? []) {
    if (p.default !== undefined) out[p.name] = p.default;
    else if (p.type === "symbol_list") out[p.name] = [];
    else if (p.type === "int" || p.type === "float") out[p.name] = 0;
    else out[p.name] = "";
  }
  return out;
}

/**
 * date_range 的预设选项。
 *
 * ⚠️ **必须与 `alpha/registry.py` 的 `_coerce_date_range` 白名单一致**：
 * 后端只认 `1y` / `6m` / `3m` 或 ISO 区间 `YYYY-MM-DD:YYYY-MM-DD`。
 *
 * 这里曾经多给了 2y / 3y（想当然），选一下就 400 —— 前端提供的选项后端不认，
 * 是「UI 撒谎」类 bug。要加更长的预设，两处必须同时改，且后端
 * `alpha/data.py` 的 `RANGE_COUNT` 也要加（否则日期会被兜底成 250 根）。
 */
export const DATE_RANGE_PRESETS: { value: string; label: string }[] = [
  { value: "3m", label: "3 个月" },
  { value: "6m", label: "6 个月" },
  { value: "1y", label: "1 年" },
];

/** ISO 区间分隔符。与后端 `_coerce_date_range` 的 `start:end` 约定一致。 */
export const RANGE_SEP = ":";

/** 'YYYY-MM-DD:YYYY-MM-DD' → { start, end }；不是自定义区间则返回 null。 */
export function parseIsoRange(v: unknown): { start: string; end: string } | null {
  if (typeof v !== "string") return null;
  const i = v.indexOf(RANGE_SEP);
  if (i < 0) return null;
  return { start: v.slice(0, i), end: v.slice(i + 1) };
}
