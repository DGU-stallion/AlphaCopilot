// 模块级内存缓存：取一次存内存，切页复用不重取；带 TTL 与 dataAsOf（M5-5）。
//
// 为什么要有 TTL：原来的缓存「活到刷新页面为止」——切页很快，但**跨日不失效**。
// 早上打开拿到昨天的收盘数据，屏幕上却没有任何提示。慢还能忍，
// 「看着像新的、其实是昨天的」不能忍。
//
// 两个时间概念必须分开：
//   fetchedAt —— 什么时候取的，决定 TTL 是否到期
//   dataAsOf  —— 数据属于哪一天，决定界面上的「as-of」显示
// 盘中 14:00 取的数据 dataAsOf 是今天，但 5 分钟后也该重取（盘口变了）。
import { useCallback, useEffect, useRef, useState } from "react";

export interface CacheEntry<T> {
  value: T;
  /** 取数时刻（ms）。0 表示老代码写进来的、来源不明。 */
  fetchedAt: number;
  /** 数据截止日 "YYYY-MM-DD"；空串表示数据源没给。 */
  dataAsOf: string;
}

interface Entry<T> {
  data: T | null;
  loading: boolean;
  error: unknown;
}

/** 默认 TTL：60 秒。盘面类数据够用，又不会长时间停在旧值上。 */
export const DEFAULT_TTL_MS = 60_000;

const store = new Map<string, CacheEntry<unknown>>();
const inflight = new Map<string, Promise<unknown>>();

export const now = () => Date.now();

/** 当前自然日（本地时区）"YYYY-MM-DD"。 */
export function today(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/**
 * 条目是否还能用。
 *
 * 三条都要满足：
 *   1. 有 fetchedAt（老条目没有 → 视为过期，宁可多取一次）
 *   2. 没超过 TTL
 *   3. **跨日必过期** —— 即使 TTL 没到（23:58 取的数据 00:01 就不该再用）
 */
export function isFresh(
  entry: Pick<CacheEntry<unknown>, "fetchedAt" | "dataAsOf">,
  atMs: number,
  ttlMs: number = DEFAULT_TTL_MS,
): boolean {
  const fetchedAt = (entry as CacheEntry<unknown>).fetchedAt;
  if (!fetchedAt || !Number.isFinite(fetchedAt)) return false;
  if (atMs - fetchedAt >= ttlMs) return false;
  // 跨日：用「取数那天」与「现在那天」比较，而不是比较 dataAsOf ——
  // dataAsOf 可能本来就是昨天（周末），拿它比会天天判过期。
  return dayOf(fetchedAt) === dayOf(atMs);
}

function dayOf(ms: number): string {
  const d = new Date(ms);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** 判断某 key 是否有**可用**的缓存值。 */
export function hasCache(key: string): boolean {
  const e = store.get(key);
  return !!e && isFresh(e, now());
}

/** 读缓存值（没有或过期返回 undefined）。 */
export function getCache<T>(key: string): T | undefined {
  const e = store.get(key);
  return e && isFresh(e, now()) ? (e.value as T) : undefined;
}

/** 读完整条目（含 fetchedAt / dataAsOf），给底栏展示 as-of 用；不管是否过期。 */
export function getCacheEntry<T>(key: string): CacheEntry<T> | undefined {
  return store.get(key) as CacheEntry<T> | undefined;
}

/** 写缓存值。dataAsOf 不传就是空串 —— **不伪造今天**（否则界面上的 as-of 会骗人）。 */
export function setCache<T>(key: string, value: T, dataAsOf = ""): void {
  store.set(key, { value, fetchedAt: now(), dataAsOf });
}

/** 手动清掉某个 key（换维度/日期时可用）。 */
export function dropCache(key: string): void {
  store.delete(key);
  inflight.delete(key);
}

/** 测试用：清空全部（避免用例间互相污染）。 */
export function _resetCache(): void {
  store.clear();
  inflight.clear();
}

export interface CachedResource<T> {
  data: T | null;
  loading: boolean;
  error: unknown;
  refresh: () => void;
}

/**
 * 首次挂载：缓存新鲜就直接用；过期或没有则拉一次。
 * refresh()：无视缓存重新 fetch。
 *
 * 注意这里**不**提供 dataAsOf：数据的时点由页面用 `lib/data-asof` 的
 * `useDataAsOf` 上报（那才是唯一真源 —— 页面知道自己的数据是哪天的，
 * 缓存层不知道）。曾经在这里放过一个 dataAsOf 字段，永远是空串且无人消费，
 * 是「为假想需求留钩子」，删掉了（review 指出）。
 */
export function useCachedResource<T>(
  key: string,
  fetcher: () => Promise<T>,
  opts: { ttlMs?: number } = {},
): CachedResource<T> {
  const ttl = opts.ttlMs ?? DEFAULT_TTL_MS;
  const cached = store.get(key);
  const usable = cached && isFresh(cached, now(), ttl) ? (cached.value as T) : undefined;

  const [state, setState] = useState<Entry<T>>({
    data: usable ?? null,
    loading: usable === undefined,
    error: null,
  });

  // ⚠️ key 变化时**必须重置 state**：useState 的初值只在首次渲染生效，
  // 不会随 key 变。不重置的症状（review 抓到的真 bug）：
  //   切到新 key、请求还在飞的时候，界面上显示的是**上一个 key 的数据**。
  //   在 Run 对比页表现为「标题是 C/D、数字还是 A/B」——
  //   数值审计场景里这是致命的，而且肉眼很难发现（数字看起来完全合理）。
  // 用「上次渲染的 key」做判据，而不是把 key 塞进依赖后无脑 setState
  // （后者会在每次渲染都 set，造成多余更新）。
  const prevKey = useRef(key);
  if (prevKey.current !== key) {
    prevKey.current = key;
    const c = store.get(key);
    const ok = c && isFresh(c, now(), ttl) ? (c.value as T) : undefined;
    if (state.data !== (ok ?? null)) {
      setState({ data: ok ?? null, loading: ok === undefined, error: null });
    }
  }

  // fetcher 常是内联箭头函数（每次渲染新引用）。放进依赖会让 run 每次重建、
  // 进而触发 effect 重跑 —— 用 ref 拿最新的一份，依赖只留 key。
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const run = useCallback(
    (force: boolean): Promise<void> => {
      const entry = store.get(key);
      const ok = entry && isFresh(entry, now(), ttl);
      if (!force && ok) {
        setState({ data: entry.value as T, loading: false, error: null });
        return Promise.resolve();
      }
      setState((s) => ({ ...s, loading: true, error: null }));
      let p = force ? undefined : (inflight.get(key) as Promise<T> | undefined);
      if (!p) {
        p = fetcherRef.current();
        inflight.set(key, p);
      }
      return p
        .then((data) => {
          setCache(key, data, "");
          setState({ data, loading: false, error: null });
        })
        .catch((error) => {
          setState((s) => ({ ...s, loading: false, error }));
        })
        .finally(() => {
          if (inflight.get(key) === p) inflight.delete(key);
        });
    },
    [key, ttl],
  );

  useEffect(() => {
    void run(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const refresh = useCallback(() => {
    void run(true);
  }, [run]);

  return { data: state.data, loading: state.loading, error: state.error, refresh };
}
