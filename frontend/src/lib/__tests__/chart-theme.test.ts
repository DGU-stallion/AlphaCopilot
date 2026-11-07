/**
 * chart-theme 必须与 UI token 同源（ADR-0014 §2）。
 *
 * 这个文件原来自己算 HSL→hex、自己判断 zh/en 决定红绿方向。后果是：
 * 图表和 UI 各走一套色，同一屏里出现两种蓝；而且「涨跌口径」本该由用户
 * 选择决定，却被语言替用户做了决定（中文=红涨）。
 *
 * 所以这里测的不是「颜色好不好看」，而是**两件事**：
 *   1. 图表色 == palette 里的值（没有第二套定义）
 *   2. 涨跌方向跟着 palette 的 up/down 走，不跟 locale 走
 */
import { beforeEach, describe, expect, it } from "vitest";
import { DARK, LIGHT } from "@/theme/tokens";
import { getChartTheme, currentPalette, _resetChartThemeCache } from "@/lib/chart-theme";

function setDocClass(cls: string, lang = "zh-CN") {
  document.documentElement.className = cls;
  document.documentElement.lang = lang;
  _resetChartThemeCache();
}

describe("图表色与 UI token 同源", () => {
  beforeEach(() => setDocClass("dark"));

  it("深色下图表色直接等于 DARK palette 的值", () => {
    const t = getChartTheme();
    expect(t.upColor).toBe(DARK.up);
    expect(t.downColor).toBe(DARK.down);
    expect(t.gridColor).toBe(DARK.border);
    expect(t.textColor).toBe(DARK.textTertiary);
    expect(t.accentColor).toBe(DARK.accent);
  });

  it("浅色下切到 LIGHT palette", () => {
    setDocClass("light");
    const t = getChartTheme();
    expect(t.upColor).toBe(LIGHT.up);
    expect(t.downColor).toBe(LIGHT.down);
    expect(t.gridColor).toBe(LIGHT.border);
  });

  it("涨跌色跟随 palette，不跟随界面语言", () => {
    // 这是原来真正的 bug：旧实现用 isChinese() 判断红绿方向，
    // 于是「中文界面的用户偏好国际口径」这种情况根本没法支持。
    setDocClass("dark", "en-US");
    const en = getChartTheme();
    setDocClass("dark", "zh-CN");
    const zh = getChartTheme();

    expect(en.upColor).toBe(zh.upColor);
    expect(en.downColor).toBe(zh.downColor);
    expect(zh.upColor).toBe(DARK.up);
  });

  it("成交量柱是涨跌色加透明度，不是另一组颜色", () => {
    const t = getChartTheme();
    expect(t.volumeUp.startsWith(DARK.up)).toBe(true);
    expect(t.volumeDown.startsWith(DARK.down)).toBe(true);
  });

  it("涨跌口径变化必须让缓存自动失效（否则切口径图表不更新）", () => {
    // 这条抓的是一个很隐蔽的 bug：缓存键只含 DOM class 的话，
    // 用户在**同一主题下**切换涨跌口径（红涨绿跌 ↔ 绿涨红跌）时
    // class 没变 → 缓存命中 → 图表颜色不跟着变，而 UI 的数字已经变了。
    // 表现是「数字红了、K 线还是绿的」。
    //
    // 关键：这里**不手动清缓存**。清缓存等于绕过被测逻辑本身，
    // 那样实现把缓存键写错也照样绿（第一版测试就是这么写的，变异测试发现的）。
    setDocClass("dark");

    const originalUp = DARK.up;
    try {
      expect(getChartTheme().upColor).toBe(originalUp);

      // 同一主题下改涨跌色 = 用户切了口径
      (DARK as { up: string }).up = "#00FF00";
      expect(getChartTheme().upColor).toBe("#00FF00");
    } finally {
      (DARK as { up: string }).up = originalUp;
      _resetChartThemeCache();
    }
  });
});

describe("currentPalette", () => {
  it("无 dark class 时是浅色（与 useDarkMode 的判定一致）", () => {
    document.documentElement.className = "light";
    _resetChartThemeCache();
    expect(currentPalette()).toEqual(LIGHT);
  });

  it("有 dark class 时是深色", () => {
    document.documentElement.className = "dark";
    _resetChartThemeCache();
    expect(currentPalette()).toEqual(DARK);
  });
});
