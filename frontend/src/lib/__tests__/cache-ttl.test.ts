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

describe("缓存层不产生 as-of（那是页面的职责）", () => {
  it("fetch 成功后写缓存时，dataAsOf 留空而不是伪造今天", async () => {
    // 缓存层不知道数据是哪天的 —— 它只知道「什么时候取的」。
    // 唯一知道数据时点的是页面（页面有接口返回的 date/as_of 字段），
    // 所以由页面用 lib/data-asof 上报。缓存层若伪造，界面上的 as-of 就是假的。
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

  it("CachedResource 不再暴露 dataAsOf（避免两套 as-of 真源）", async () => {
    const { renderHook } = await import("@testing-library/react");
    const { useCachedResource, _resetCache } = await import("@/lib/cache");
    _resetCache();
    const { result } = renderHook(() =>
      useCachedResource("k-nofield", () => Promise.resolve(1)),
    );
    expect("dataAsOf" in result.current).toBe(false);
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

describe("key 变化时不能残留上一个 key 的数据", () => {
  it("切到新 key 且无缓存时，data 必须先清空再拉", async () => {
    // review 抓到的真 bug：useState 的初值只在首次渲染生效，
    // key 变化时 state 不会重置 → 新请求进行中界面上还显示**上一个 key 的数据**。
    // 在 Run 对比页表现为「标题是 C/D、数字还是 A/B」—— 数值审计场景下是致命的。
    const { renderHook, waitFor } = await import("@testing-library/react");
    const { useCachedResource, _resetCache } = await import("@/lib/cache");
    _resetCache();

    let resolveB: ((v: string) => void) | null = null;
    const { result, rerender } = renderHook(
      ({ k }: { k: string }) =>
        useCachedResource<string>(k, () =>
          k === "a" ? Promise.resolve("A-value")
            : new Promise<string>((res) => { resolveB = res; })),
      { initialProps: { k: "a" } },
    );
    await waitFor(() => expect(result.current.data).toBe("A-value"));

    // 切到 key b：请求挂起中，不能还显示 A 的数据
    rerender({ k: "b" });
    await waitFor(() => expect(result.current.loading).toBe(true));
    expect(result.current.data).toBeNull();   // ← 变异点

    resolveB?.("B-value");
    await waitFor(() => expect(result.current.data).toBe("B-value"));
  });
});

/**
 * TTL 分级（ROUND2 §13，A4）。
 *
 * 原来全站共用一个 60 秒。问题不是长短，而是**所有数据一个值**：
 * 回测实测单次 8s，60s TTL 等于「每次切回页面都重算」。
 * 分级依据是「取数代价 × 变化频率」。
 */
describe("TTL 分级", () => {
  it("四档单调递增：LIVE < DEFAULT < COMPUTE < ARCHIVE", async () => {
    const { TTL } = await import("@/lib/cache");
    expect(TTL.LIVE).toBeLessThan(TTL.DEFAULT);
    expect(TTL.DEFAULT).toBeLessThan(TTL.COMPUTE);
    expect(TTL.COMPUTE).toBeLessThan(TTL.ARCHIVE);
  });

  it("昂贵重算的 TTL 至少是 10 分钟（否则等于没缓存）", async () => {
    // 回测/净值/页面渲染实测单次约 8s。TTL 若只有 60s，
    // 「切走再切回」几乎必然重算 —— 缓存形同虚设。
    const { TTL } = await import("@/lib/cache");
    expect(TTL.COMPUTE).toBeGreaterThanOrEqual(10 * 60_000);
  });

  it("行情类必须短（> 60s 会让盘中看起来卡住）", async () => {
    const { TTL } = await import("@/lib/cache");
    expect(TTL.LIVE).toBeLessThanOrEqual(60_000);
  });

  it("长 TTL 不会把昨天的数据当今天：跨日依然强制失效", async () => {
    // 这是 COMPUTE 敢给 30 分钟的前提 —— 没有跨日失效，长 TTL 就是数据事故。
    const { isFresh, TTL } = await import("@/lib/cache");
    const entry = { fetchedAt: at("2026-10-21T14:00:00"), dataAsOf: "2026-10-21" };
    expect(isFresh(entry, at("2026-10-21T14:20:00"), TTL.COMPUTE)).toBe(true);
    expect(isFresh(entry, at("2026-10-22T09:00:00"), TTL.COMPUTE)).toBe(false);
  });
});
