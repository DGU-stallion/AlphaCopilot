/**
 * 全站数据时点（M5-4 / ADR-0012）。
 *
 * 问题：页面上的数字带不带时间戳，决定了你敢不敢用它。
 * 「涨停 54 家」如果是昨天收盘的，和「今天 14:30 的」，是两个完全不同的事实。
 *
 * 做法：页面把自己的数据时点报告上来，布局底栏统一显示。
 * 为什么用 context 而不是让每个页面各画一行小字：
 *   - 底栏位置固定，用户不用在每页重新找「这数据是什么时候的」
 *   - 一处显示，格式必然一致（各页各写会出现三种日期格式）
 *
 * as-of 有两个维度，都要能表达：
 *   - dataAsOf：数据所属交易日（"2026-10-21"）
 *   - fetchedAt：什么时候取的（盘口类数据要精确到分钟，因为它会变）
 */
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export interface DataAsOf {
  /** 数据所属交易日 "YYYY-MM-DD"；空串表示未知。 */
  dataAsOf: string;
  /** 取数时刻（ms）；0 表示未知。 */
  fetchedAt: number;
  /** 一句话说明这份数据是什么（如「实时打板情绪」）。 */
  label?: string;
}

interface Ctx {
  current: DataAsOf | null;
  set: (v: DataAsOf | null) => void;
}

const DataAsOfContext = createContext<Ctx>({ current: null, set: () => {} });

export function DataAsOfProvider({ children }: { children: ReactNode }) {
  const [current, set] = useState<DataAsOf | null>(null);
  const value = useMemo(() => ({ current, set }), [current]);
  return <DataAsOfContext.Provider value={value}>{children}</DataAsOfContext.Provider>;
}

/**
 * 页面调用：报告本页数据的时点。
 *
 * ⚠️ 传 `null` 表示**本页没有数据**（不是「未知」）。两者的区别在于：
 * 有数据但时点未知，要明确显示「时点未知」，而不是装作没这回事 ——
 * 未知的时间戳和不显示时间戳一样危险。
 */
export function useDataAsOf(info: DataAsOf | null) {
  const { set } = useContext(DataAsOfContext);
  // 依赖用具体字段而不是对象：调用方常写内联对象字面量，
  // 依赖对象本身会导致每次渲染都 setState → 无限重渲染（踩过类似的坑）。
  const { dataAsOf, fetchedAt, label } = info ?? { dataAsOf: "", fetchedAt: 0, label: undefined };
  useEffect(() => {
    set(info === null ? null : { dataAsOf, fetchedAt, label });
    return () => set(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataAsOf, fetchedAt, label, info === null]);
}

export function useDataAsOfValue(): DataAsOf | null {
  return useContext(DataAsOfContext).current;
}

/** 给底栏用的展示文案。把「格式化规则」收在一处，避免各页各写。 */
export function formatAsOf(info: DataAsOf | null): { text: string; stale: boolean } {
  if (!info) return { text: "无数据", stale: false };
  if (!info.dataAsOf) return { text: "时点未知", stale: true };

  const t = info.fetchedAt ? new Date(info.fetchedAt) : null;
  const hhmm = t ? `${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}` : "";
  const sameDay = t ? localDay(t) === localDay(new Date()) : false;

  // 跨日的数据一定要标出来：底栏写「as-of 2026-10-20」时，
  // 用户看到的第一个问题是「今天是几号」，所以要带相对说法。
  const text = sameDay
    ? `${info.dataAsOf} ${hhmm}`.trim()
    : `${info.dataAsOf}（非今日）`;
  return { text, stale: !sameDay };
}

function localDay(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
