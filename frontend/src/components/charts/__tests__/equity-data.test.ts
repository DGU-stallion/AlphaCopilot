/**
 * 净值/回撤整形（M2-6）。
 *
 * 前端**不做数值计算**（回撤在后端算，硬规则 6），这里只做形状转换 + 兜底。
 * 兜底规则都有代价可讲：
 *   - 单点系列画不出线 → 丢（画成孤立标记像 bug）
 *   - time 非严格递增 → 丢（LWC 内部断言抛错 → 整页白屏）
 *   - 回撤为正 → 截到 0（面积翻上去比没画更误导）
 */
import { describe, expect, it } from "vitest";
import { DARK } from "@/theme/tokens";
import {
  toEquityLines, toDrawdown, seriesColor, totalReturn, type LwcPayload,
} from "@/components/charts/equity-data";

const pt = (t: string, v: number) => ({ time: t, value: v });
const payload = (over: Partial<LwcPayload> = {}): LwcPayload => ({
  series: [{ name: "策略", points: [pt("d1", 1), pt("d2", 1.1)] }],
  drawdown: [pt("d1", 0), pt("d2", -0.05)],
  ...over,
});

describe("toEquityLines", () => {
  it("正常载荷转成 {time,value}", () => {
    const out = toEquityLines(payload());
    expect(out).toHaveLength(1);
    expect(out[0].name).toBe("策略");
    expect(out[0].points).toEqual([pt("d1", 1), pt("d2", 1.1)]);
  });

  it("丢弃点数 < 2 的系列（一个点画不出线）", () => {
    const out = toEquityLines(payload({ series: [{ name: "单点", points: [pt("d1", 1)] }] }));
    expect(out).toEqual([]);
  });

  it("time 非严格递增的系列整个丢弃（LWC 会抛错白屏）", () => {
    const out = toEquityLines(payload({
      series: [{ name: "乱序", points: [pt("d2", 1), pt("d1", 1.1), pt("d3", 1.2)] }],
    }));
    expect(out).toEqual([]);
  });

  it("重复 time 也算不严格递增", () => {
    const out = toEquityLines(payload({
      series: [{ name: "重复", points: [pt("d1", 1), pt("d1", 1.1)] }],
    }));
    expect(out).toEqual([]);
  });

  it("滤掉非有限数点，剩下的仍递增则保留", () => {
    const out = toEquityLines(payload({
      series: [{ name: "含空", points: [pt("d1", 1), { time: "d2", value: NaN }, pt("d3", 1.2)] }],
    }));
    expect(out[0].points.map((p) => p.time)).toEqual(["d1", "d3"]);
  });

  it("null / 空载荷返回空数组（调用方直接 setData）", () => {
    expect(toEquityLines(null)).toEqual([]);
    expect(toEquityLines({ series: [], drawdown: [] })).toEqual([]);
  });
});

describe("toDrawdown", () => {
  it("非正值原样保留", () => {
    expect(toDrawdown(payload()).map((p) => p.value)).toEqual([0, -0.05]);
  });

  it("正值截到 0（面积不该翻上去）", () => {
    const out = toDrawdown(payload({ drawdown: [pt("d1", 0.1), pt("d2", -0.05)] }));
    expect(out[0].value).toBe(0);
    expect(out[1].value).toBe(-0.05);
  });

  it("排序去重（LWC 要求严格递增）", () => {
    const out = toDrawdown(payload({
      drawdown: [pt("d2", -0.05), pt("d1", 0), pt("d2", -0.09)],
    }));
    expect(out.map((p) => p.time)).toEqual(["d1", "d2"]);
  });

  it("空载荷返回空数组", () => {
    expect(toDrawdown(null)).toEqual([]);
  });
});

describe("seriesColor", () => {
  it("第一条是 accent、第二条是 warning，之后轮转", () => {
    expect(seriesColor(0, DARK)).toBe(DARK.accent);
    expect(seriesColor(1, DARK)).toBe(DARK.warning);
  });

  it("超出序列长度时轮转，不返回 undefined", () => {
    for (let i = 0; i < 9; i += 1) {
      expect(typeof seriesColor(i, DARK)).toBe("string");
      expect(seriesColor(i, DARK).startsWith("#")).toBe(true);
    }
  });
});

describe("totalReturn", () => {
  it("算区间涨跌（纯展示）", () => {
    expect(totalReturn([pt("d1", 1), pt("d2", 1.2)])).toBeCloseTo(0.2);
    expect(totalReturn([pt("d1", 1), pt("d2", 0.8)])).toBeCloseTo(-0.2);
  });

  it("点数不足或起点非正时返回 null（不返回 0 假装有值）", () => {
    expect(totalReturn([pt("d1", 1)])).toBeNull();
    expect(totalReturn([pt("d1", 0), pt("d2", 1)])).toBeNull();
  });
});
