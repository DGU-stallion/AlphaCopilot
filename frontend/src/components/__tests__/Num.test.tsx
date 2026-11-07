/**
 * <Num>（ADR-0014 §4）。
 *
 * 这里最要紧的不是格式好不好看，而是**符号不能被吞掉**。
 * 实测踩到的 bug：正文用 Math.abs 做千分位格式化，负号没显式拼回去，
 * 于是页面把 -1.67% 显示成 1.67% —— 在股票界面上等于把跌看成涨。
 * 所以符号相关的用例放在最前面，它们是这个组件存在的最低标准。
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { DARK, LIGHT } from "@/theme/tokens";
import { Num } from "@/components/Num";

function text(v: number | null | undefined, props: Record<string, unknown> = {}) {
  const { container } = render(<Num v={v} {...props} />);
  return container.textContent ?? "";
}

/** 从计算样式里取颜色，判断红/绿倾向（不写死 hex）。 */
function colorOf(v: number, props: Record<string, unknown> = {}) {
  const { container } = render(<Num v={v} {...props} />);
  const el = container.firstElementChild as HTMLElement;
  const m = getComputedStyle(el).color.match(/\d+/g);
  if (!m) return null;
  const [r, g] = m.map(Number);
  return { red: r > g + 15, green: g > r + 15 };
}

describe("符号（最低标准）", () => {
  beforeEach(() => { document.documentElement.className = "dark"; });

  it("负数必须带负号", () => {
    expect(text(-1.67, { pct: true })).toBe("-1.67%");
    expect(text(-1309.69)).toBe("-1,309.69");
  });

  it("pct 的正数带 + 号", () => {
    expect(text(1.67, { pct: true })).toBe("+1.67%");
  });

  it("普通数值的正数不带 + 号（只有 pct / signed 才加）", () => {
    expect(text(1309.69)).toBe("1,309.69");
    expect(text(1309.69, { signed: true })).toBe("+1,309.69");
  });

  it("负数在 prefix 之前（货币写法 -¥1,234 而不是 ¥-1,234）", () => {
    expect(text(-1234, { prefix: "¥", digits: 0 })).toBe("-¥1,234");
  });

  it("rate 的负数带负号", () => {
    expect(text(-0.0325, { rate: true, digits: 2 })).toBe("-3.25%");
  });
});

describe("空值与异常", () => {
  it("null / undefined / NaN / Infinity 一律显示 —", () => {
    for (const v of [null, undefined, NaN, Infinity, -Infinity]) {
      expect(text(v as number)).toBe("—");
    }
  });

  it("空值不带单位（不然会出现「—亿」）", () => {
    expect(text(null, { unit: "亿" })).toBe("—");
  });
});

describe("格式", () => {
  it("千分位分组（防 1,234.56 读成 12,34.56）", () => {
    expect(text(1234.56)).toBe("1,234.56");
    expect(text(1234567.891, { digits: 2 })).toBe("1,234,567.89");
  });

  it("digits 控制小数位，默认 2", () => {
    expect(text(1)).toBe("1.00");
    expect(text(1, { digits: 0 })).toBe("1");
    expect(text(1.5, { digits: 3 })).toBe("1.500");
  });

  it("unit 在百分号之后", () => {
    expect(text(3.2, { digits: 2, unit: "亿" })).toBe("3.20亿");
  });
});

describe("颜色方向（A 股口径：涨红跌绿）", () => {
  beforeEach(() => { document.documentElement.className = "dark"; });

  it("正数红、负数绿", () => {
    expect(colorOf(1.2, { pct: true })?.red).toBe(true);
    expect(colorOf(-1.2, { pct: true })?.green).toBe(true);
  });

  it("零走中性色（不是红色也不是绿色）", () => {
    const c = colorOf(0, { pct: true });
    expect(c?.red).toBe(false);
    expect(c?.green).toBe(false);
  });

  it("用舍入后的值判色：0.004 显示 0.00 时不该是红色", () => {
    // 否则表格里一片「+0.00% 红」，看着像全线飘红
    const c = colorOf(0.004, { pct: true, digits: 2 });
    expect(c?.red).toBe(false);
  });

  it("等宽数字 + tabular-nums（否则列不对齐）", () => {
    const { container } = render(<Num v={1234.56} />);
    const el = container.firstElementChild as HTMLElement;
    expect(el.style.fontFamily).toContain("JetBrains Mono");
    expect(el.style.fontVariantNumeric).toBe("tabular-nums");
  });

  it("inheritColor 时不设内联色（交给父元素语义色）", () => {
    const { container } = render(<Num v={1.2} pct inheritColor />);
    expect((container.firstElementChild as HTMLElement).style.color).toBe("");
  });

  it("浅色主题取 LIGHT 的值，不存在写死的深色", () => {
    document.documentElement.className = "light";
    const { container } = render(<Num v={1.2} pct />);
    const color = getComputedStyle(container.firstElementChild as HTMLElement).color;
    const toRgb = (hex: string) => {
      const h = hex.replace("#", "");
      return `rgb(${parseInt(h.slice(0, 2), 16)}, ${parseInt(h.slice(2, 4), 16)}, ${parseInt(h.slice(4, 6), 16)})`;
    };
    expect(color).toBe(toRgb(LIGHT.up));
  });
});
