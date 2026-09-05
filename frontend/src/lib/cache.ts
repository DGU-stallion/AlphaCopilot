// 模块级内存缓存：取一次存内存，切页复用不重取，只有手动 refresh() 才重新拉。
// 低频盘面数据"取一次就够"，避免切换路由时重复打后端请求。
import { useCallback, useEffect, useState } from "react";

interface Entry<T> {
  data: T | null;
  loading: boolean;
  error: unknown;
}

// key -> 已取到的数据。进程内存活到刷新页面为止。
const store = new Map<string, unknown>();
// 正在飞的请求：同一 key 并发挂载只发一次。
const inflight = new Map<string, Promise<unknown>>();

/** 判断某 key 是否已缓存（组件挂载时决定要不要发首次请求）。 */
export function hasCache(key: string): boolean {
  return store.has(key);
}

/** 读缓存值（没有返回 undefined）。 */
export function getCache<T>(key: string): T | undefined {
  return store.get(key) as T | undefined;
}

/** 写缓存值（loader 成功后调用，切页回来直接复用）。 */
export function setCache<T>(key: string, value: T) {
  store.set(key, value);
}

/** 手动清掉某个 key（换维度/日期时可用）。 */
export function dropCache(key: string) {
  store.delete(key);
  inflight.delete(key);
}

export interface CachedResource<T> {
  data: T | null;
  loading: boolean;
  error: unknown;
  refresh: () => void;
}

/**
 * 首次挂载：缓存有值直接用、不发请求；没有则拉一次并存内存。
 * refresh()：无视缓存重新 fetch 并更新缓存。
 */
export function useCachedResource<T>(key: string, fetcher: () => Promise<T>): CachedResource<T> {
  const cached = store.get(key) as T | undefined;
  const [state, setState] = useState<Entry<T>>({
    data: cached ?? null,
    loading: cached === undefined,
    error: null,
  });

  const run = useCallback(
    (force: boolean): Promise<void> => {
      if (!force && store.has(key)) {
        setState({ data: store.get(key) as T, loading: false, error: null });
        return Promise.resolve();
      }
      setState((s) => ({ ...s, loading: true, error: null }));
      // 复用在飞请求，避免同 key 重复打
      let p = force ? undefined : (inflight.get(key) as Promise<T> | undefined);
      if (!p) {
        p = fetcher();
        inflight.set(key, p);
      }
      return p
        .then((data) => {
          store.set(key, data);
          setState({ data, loading: false, error: null });
        })
        .catch((error) => {
          setState((s) => ({ ...s, loading: false, error }));
        })
        .finally(() => {
          if (inflight.get(key) === p) inflight.delete(key);
        });
    },
    [key, fetcher],
  );

  useEffect(() => {
    // 挂载：有缓存直接用，没有才拉
    void run(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const refresh = useCallback(() => {
    void run(true);
  }, [run]);

  return { data: state.data, loading: state.loading, error: state.error, refresh };
}
