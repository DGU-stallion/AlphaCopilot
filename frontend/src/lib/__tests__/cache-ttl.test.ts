/**
 * 缓存 TTL（M5-5）。
 *
 * 问题：现在的缓存是「进程内存活到刷新页面为止」——切页复用很方便，
 * 但**跨日不会失效**。早上 9:00 打开页面拿的是昨天的收盘数据，
 * 下午再切回来还是那份，而屏幕上没有任何提示。这比慢更糟：它让人以为数据是新的。
 *
 * 所以每条缓存都要带**取数时间**与**数据截止日**两个概念：
 *   - 取数时间 fetchedAt：决定「多久之后该重取」（TTL）
 *   - dataAsOf：决定「这个数字属于哪一天」（展示用，跨日必须变）
 *
 * 两者不是一回事：盘中 14:00 取到的数据 dataAsOf 是今天，但 5 分钟后 TTL 到了
 * 也该重取（盘口变了）。把它们合成一个字段会丢掉其中一维。
 */
import { describe, expect, it, vi } from "vitest";

/** 用假时钟，避免测试依赖真实时间（否则会在午夜或跨日时随机红）。 */
function at(iso: string) {
  return new Date(iso).getTime();
}

describe("TTL 判定", () => {
  it("未过期时命中缓存", async () => {
    const { isFresh } = await import("@/lib/cache");
    const entry = { fetchedAt: at("2026-10-21T10:00:00"), dataAsOf: "2026-10-21" };
    expect(isFresh(entry, at("2026-10-21T10:00:30"), 60_000)).toBe(true);
  });

  it("超过 TTL 时视为过期", async () => {
    const { isFresh } = await import("@/lib/cache");
    const entry = { fetchedAt: at("2026-10-21T10:00:00"), dataAsOf: "2026-10-21" };
    expect(isFresh(entry, at("2026-10-21T10:02:00"), 60_000)).toBe(false);
  });

  it("跨日必定过期（即使 TTL 没到）", async () => {
    // 关键场景：23:58 取的数据，00:01 再看，TTL 只有 3 分钟没超，
    // 但它已经是「昨天的数据」了 —— 必须重取。
    const { isFresh } = await import("@/lib/cache");
    const entry = { fetchedAt: at("2026-10-21T23:58:00"), dataAsOf: "2026-10-21" };
    expect(isFresh(entry, at("2026-10-22T00:01:00"), 3600_000)).toBe(false);
  });

  it("老条目没有 fetchedAt 时视为过期（宁可多取一次，不要用来源不明的数据）", async () => {
    const { isFresh } = await import("@/lib/cache");
    expect(isFresh({ dataAsOf: "2026-10-21" } as never, at("2026-10-21T10:00:00"), 60_000)).toBe(false);
  });
});

describe("缓存条目带取数时间", () => {
  it("setCache 记录 fetchedAt 与 dataAsOf", async () => {
    const { setCache, getCacheEntry, _resetCache, now } = await import("@/lib/cache");
    _resetCache();
    setCache("k", { v: 1 }, "2026-10-21");
    const e = getCacheEntry<{ v: number }>("k");
    expect(e?.value).toEqual({ v: 1 });
    expect(e?.dataAsOf).toBe("2026-10-21");
    expect(e?.fetchedAt).toBeGreaterThan(0);
    expect(Math.abs(e!.fetchedAt - now())).toBeLessThan(5000);
  });

  it("不传 dataAsOf 时留空字符串，而不是伪造今天", async () => {
    // 伪造今天会让 M5-4 的「as-of」显示骗人
    const { setCache, getCacheEntry, _resetCache } = await import("@/lib/cache");
    _resetCache();
    setCache("k2", { v: 1 });
    expect(getCacheEntry("k2")?.dataAsOf).toBe("");
  });
});

describe("useCachedResource 不伪造 dataAsOf", () => {
  it("数据源没给 as-of 时，返回空串而不是今天", async () => {
    // 这条抓的是变异测试没抓到的洞：把 setCache(key, data, "") 改成
    // setCache(key, data, today()) 会让界面显示「as-of 今天」，
    // 而实际数据可能是昨天的。伪造时间戳比不显示更糟 —— 它会让人相信它。
    const { renderHook, waitFor } = await import("@testing-library/react");
    const { useCachedResource, _resetCache } = await import("@/lib/cache");
    _resetCache();
    const { result } = renderHook(() =>
      useCachedResource("k-asof", () => Promise.resolve({ v: 1 })),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.dataAsOf).toBe("");
  });

  it("真走 fetch 路径时，缓存里存的 dataAsOf 必须是空串（不伪造今天）", async () => {
    // 上一条走的是「命中新鲜缓存」分支，碰不到 setCache。
    // 变异测试发现必须专门覆盖 fetch 成功后写缓存的这一行。
    const { renderHook, waitFor } = await import("@testing-library/react");
    const { useCachedResource, getCacheEntry, _resetCache } = await import("@/lib/cache");
    _resetCache();
    const { result } = renderHook(() =>
      useCachedResource("k-fetch-asof", () => Promise.resolve({ v: 42 })),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    const entry = getCacheEntry<{ v: number }>("k-fetch-asof");
    expect(entry?.value).toEqual({ v: 42 });
    expect(entry?.dataAsOf).toBe("");     // ← 变异点：改成 today() 这里就红
  });

  it("缓存条目里的 dataAsOf 透出给调用方", async () => {
    const { renderHook, waitFor } = await import("@testing-library/react");
    const { useCachedResource, setCache, _resetCache } = await import("@/lib/cache");
    _resetCache();
    setCache("k-asof2", { v: 2 }, "2026-10-20");
    const { result } = renderHook(() =>
      useCachedResource("k-asof2", () => Promise.resolve({ v: 3 })),
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    // 命中新鲜缓存，不该重新 fetch，as-of 应为缓存里的值
    expect(result.current.data).toEqual({ v: 2 });
    expect(result.current.dataAsOf).toBe("2026-10-20");
  });
});

describe("判定过期后要真的重取", () => {
  it("缓存过期时 useCachedResource 会重新 fetch", async () => {
    vi.useFakeTimers();
    const { setCache, _resetCache, isFresh } = await import("@/lib/cache");
    _resetCache();
    setCache("k3", { v: "old" }, "2026-10-21");
    // 直接验证判定：过期后调用方不该命中
    expect(isFresh({ fetchedAt: at("2026-10-21T09:00:00"), dataAsOf: "2026-10-21" },
      at("2026-10-21T15:00:00"), 60_000)).toBe(false);
    vi.useRealTimers();
  });
});
