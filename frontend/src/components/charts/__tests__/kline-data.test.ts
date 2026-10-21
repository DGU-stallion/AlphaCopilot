/**
 * K 线数据整形（M2-6）。
 *
 * 图表组件本身是 imperative + canvas，难写单测；但**喂给它的数据**是纯函数，
 * 而这里恰好是踩过坑的地方，所以单独抽出来测。
 *
 * 已知的坑（每条都有对应测试）：
 *   1. LWC 要求 time 严格递增且不重复，否则内部断言直接抛错（整页白屏）
 *   2. 后端偶尔返回同一天两条（数据源合并/重试），必须去重而不是原样喂
 *   3. 成交量柱的颜色要跟**当根 K 线**的方向走（收 >= 开 用涨色），
 *      不能跟"今天涨跌"走 —— 那会让阴线的量柱显示成红色
 */
import { describe, expect, it } from "vitest";
import { DARK } from "@/theme/tokens";
import {
  toCandleData, toVolumeData, paneHeight, type RawBar,
} from "@/components/charts/kline-data";

const bar = (date: string, o: number, c: number, v = 100): RawBar => ({
  datetime: date, open: o, close: c, high: Math.max(o, c) + 1, low: Math.min(o, c) - 1, vol: v,
});

describe("toCandleData", () => {
  it("把后端的 datetime/open/close/high/low 映射成 LWC 的 time/OHLC", () => {
    const [c] = toCandleData([bar("2026-10-21", 10, 12)]);
    expect(c).toEqual({ time: "2026-10-21", open: 10, close: 12, high: 13, low: 9 });
  });

  it("保证严格递增：乱序输入会被排序", () => {
    const out = toCandleData([
      bar("2026-10-21", 1, 1), bar("2026-10-19", 1, 1), bar("2026-10-20", 1, 1),
    ]);
    expect(out.map((x) => x.time)).toEqual(["2026-10-19", "2026-10-20", "2026-10-21"]);
  });

  it("同一天重复只保留最后一条（否则 LWC 内部断言抛错、页面白屏）", () => {
    const out = toCandleData([
      bar("2026-10-20", 1, 2), bar("2026-10-21", 3, 4), bar("2026-10-21", 5, 6),
    ]);
    expect(out).toHaveLength(2);
    expect(out[1]).toEqual({ time: "2026-10-21", open: 5, close: 6, high: 7, low: 4 });
  });

  it("丢弃字段缺失/非有限数的行，而不是喂 NaN 给图表", () => {
    const out = toCandleData([
      bar("2026-10-19", 1, 1),
      { datetime: "2026-10-20", open: NaN, close: 2, high: 3, low: 1, vol: 5 },
      { datetime: "", open: 1, close: 2, high: 3, low: 1, vol: 5 },
    ]);
    expect(out).toHaveLength(1);
  });

  it("空输入返回空数组（不是 undefined，调用方要能直接 setData）", () => {
    expect(toCandleData([])).toEqual([]);
  });
});

describe("toVolumeData", () => {
  it("量柱颜色跟当根 K 线方向走：收 >= 开 用涨色", () => {
    const bars = [bar("2026-10-20", 10, 12), bar("2026-10-21", 12, 11)];
    const vol = toVolumeData(bars, DARK);
    expect(vol[0].color?.startsWith(DARK.up)).toBe(true);
    expect(vol[1].color?.startsWith(DARK.down)).toBe(true);
  });

  it("量柱与 K 线同一时间轴（time 完全一致，否则 pane 之间会错位）", () => {
    const bars = [bar("2026-10-20", 10, 12), bar("2026-10-21", 12, 11)];
    expect(toVolumeData(bars, DARK).map((v) => v.time))
      .toEqual(toCandleData(bars).map((c) => c.time));
  });

  it("成交量取 vol 字段", () => {
    expect(toVolumeData([bar("2026-10-20", 10, 12, 33514)], DARK)[0].value).toBe(33514);
  });
});

describe("paneHeight", () => {
  it("成交量占总量约 24%", () => {
    expect(paneHeight(800)).toBe(192);
  });

  it("有下限，容器很矮时不至于把量柱压成 0 高", () => {
    expect(paneHeight(100)).toBe(48);
  });

  it("高度为 0 / 负数时返回下限（容器还没测量时的初值）", () => {
    expect(paneHeight(0)).toBe(48);
    expect(paneHeight(-10)).toBe(48);
  });
});
