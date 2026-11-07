// M2-7：rendererOf 分派测试 —— chart 块回 renderer，非 chart 块恒 undefined。
import { describe, expect, it } from "vitest";
import { rendererOf, type RenderBlock } from "../research";

const chart = (renderer?: "lwc" | "echarts"): RenderBlock => ({
  kind: "chart",
  span: 1,
  ...(renderer ? { renderer } : {}),
});

describe("rendererOf", () => {
  it("chart 块返回声明的 renderer", () => {
    expect(rendererOf(chart("lwc"))).toBe("lwc");
    expect(rendererOf(chart("echarts"))).toBe("echarts");
  });

  it("缺 renderer 的 chart（老数据）返回 undefined，不默认猜", () => {
    expect(rendererOf(chart())).toBeUndefined();
  });

  it("非 chart 块即使带 renderer 也返回 undefined（分派只关 chart）", () => {
    const metric: RenderBlock = {
      kind: "metric",
      span: 1,
      renderer: "echarts",
      metric: { items: [] },
    };
    expect(rendererOf(metric)).toBeUndefined();
  });
});
