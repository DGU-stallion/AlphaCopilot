/**
 * 净值 / 回撤数据整形（M2-6）。
 *
 * 数据来自后端 `lwc` 载荷（alpha/lwc.py 产 {series:[{name,points}], drawdown}），
 * 前端**不做任何数值计算** —— 回撤、去重、排序都在后端（硬规则 6：
 * 确定性计算不进 UI 层）。这里只做「形状转换 + 脏数据兜底」。
 */
import type { Palette } from "@/theme/tokens";

export interface Point { time: string; value: number }
export interface Series { name: string; points: Point[] }
export interface LwcPayload { series: Series[]; drawdown: Point[] }

/** 净值线上的一条折线（LWC 的 LineData 形状）。 */
export interface EquityLine { name: string; points: { time: string; value: number }[] }
/** 回撤面积（负值，画到 0 轴下方）。 */
export interface DrawdownArea { time: string; value: number }

const finite = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);

/** 按 (name, index) 给系列上色：主策略用 accent，基准用 warning，其余轮转分类色。 */
export function seriesColor(index: number, p: Palette): string {
  const seq = [p.accent, p.warning, p.catViolet, p.catTeal, p.info];
  return seq[index % seq.length];
}

/**
 * 取可由 LWC 画出的净值线。
 *
 * 丢弃：
 *   - 点数 < 2 的系列（一个点画不出线，LWC 会画成一个孤立标记，看着像 bug）
 *   - time 非严格递增的（LWC 内部断言会抛错 → 整页白屏）
 */
export function toEquityLines(payload: LwcPayload | null): EquityLine[] {
  if (!payload || !Array.isArray(payload.series)) return [];
  const out: EquityLine[] = [];
  for (const s of payload.series) {
    const pts = (s.points ?? []).filter((p) => (
      typeof p?.time === "string" && p.time.length > 0 && finite(p.value)
    ));
    if (pts.length < 2) continue;
    // 后端已排序；这里再兜一层，因为「严格递增」是 LWC 的硬要求，
    // 违反的代价是整页白屏 —— 这种代价下值得重复检查一次。
    for (let i = 1; i < pts.length; i += 1) {
      if (pts[i].time <= pts[i - 1].time) return out;   // 弃掉这一条及后续（数据已经不可信）
    }
    out.push({ name: s.name, points: pts.map(({ time, value }) => ({ time, value })) });
  }
  return out;
}

/** 回撤序列：LWC 要严格递增、值为非正。 */
export function toDrawdown(payload: LwcPayload | null): DrawdownArea[] {
  const dd = payload?.drawdown;
  if (!Array.isArray(dd)) return [];
  const seen = new Set<string>();
  const out: DrawdownArea[] = [];
  for (const p of [...dd].sort((a, b) => (a.time < b.time ? -1 : 1))) {
    if (typeof p?.time !== "string" || !p.time || !finite(p.value)) continue;
    if (seen.has(p.time)) continue;
    seen.add(p.time);
    // 回撤不该为正；若为正说明上游算错，截到 0 而不是让面积翻上去
    out.push({ time: p.time, value: Math.min(0, p.value) });
  }
  return out;
}

/** 区间的涨跌幅（用于标题旁的小字，纯展示；不做投资判断）。 */
export function totalReturn(points: Point[]): number | null {
  if (points.length < 2) return null;
  const a = points[0].value;
  const b = points[points.length - 1].value;
  if (!(a > 0)) return null;
  return (b - a) / a;
}
