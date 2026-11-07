/**
 * 涨跌双口径（M2-9 / ADR-0014 §3）。
 *
 * 要分清两类颜色，这是这个模块存在的全部理由：
 *
 *   1. **涨跌色**（up / down）——表达「涨/跌」这个市场事实，随口径切换而反向。
 *      A 股口径：涨=红、跌=绿（cn，默认）。国际口径：涨=绿、跌=红（intl）。
 *
 *   2. **UI 语义色**（danger / success）——表达「操作出错 / 操作成功」，
 *      **不随口径变化**。否则国际口径下用户删除成功会看到红色提示，
 *      把「删掉了」误读成「出错了」。
 *
 * 之前 tokens.ts 把这两个概念混用（antd 的 colorError 直接吃 up），
 * 一旦加了口径切换，表单校验的红绿就会跟着市场口径翻转 —— 所以先拆开。
 */
import { DARK, LIGHT, withCaliber, type Caliber, type Palette } from "@/theme/tokens";

describe("withCaliber", () => {
  it("A 股口径：涨红跌绿（默认，不改 palette）", () => {
    const p = withCaliber(DARK, "cn");
    expect(p.up).toBe(DARK.up);
    expect(p.down).toBe(DARK.down);
  });

  it("国际口径：涨绿跌红（up/down 互换）", () => {
    const p = withCaliber(DARK, "intl");
    expect(p.up).toBe(DARK.down);
    expect(p.down).toBe(DARK.up);
  });

  it("不修改原 palette（纯函数）", () => {
    const before = { up: DARK.up, down: DARK.down };
    withCaliber(DARK, "intl");
    expect({ up: DARK.up, down: DARK.down }).toEqual(before);
  });

  it("浅色主题同样适用", () => {
    const p = withCaliber(LIGHT, "intl");
    expect(p.up).toBe(LIGHT.down);
    expect(p.down).toBe(LIGHT.up);
  });

  it("口径只动涨跌色，不碰 UI 语义色与强调色", () => {
    // 这是上面注释说的那个 bug 的守门：如果 danger/success 也跟着翻，
    // 国际口径下的「保存成功」提示会变红。
    const cn = withCaliber(DARK, "cn");
    const intl = withCaliber(DARK, "intl");
    expect(intl.danger).toBe(cn.danger);
    expect(intl.success).toBe(cn.success);
    expect(intl.accent).toBe(cn.accent);
    expect(intl.text).toBe(cn.text);
  });
});

describe("Palette 的语义色是固定的", () => {
  it("danger 永远是红系、success 永远是绿系（与口径无关）", () => {
    const p: Palette = DARK;
    // 用 HSL 判色相，避免写死具体 hex（hex 会被设计系统守门测试抓）
    expect(p.danger).not.toBe(p.success);
    // danger 的红色通道应明显强于绿色通道
    const red = parseInt(p.danger.slice(1, 3), 16);
    const green = parseInt(p.danger.slice(3, 5), 16);
    expect(red).toBeGreaterThan(green);

    const sRed = parseInt(p.success.slice(1, 3), 16);
    const sGreen = parseInt(p.success.slice(3, 5), 16);
    expect(sGreen).toBeGreaterThan(sRed);
  });
});

describe("Caliber 类型", () => {
  it("只有 cn / intl 两个值", () => {
    const values: Caliber[] = ["cn", "intl"];
    expect(values).toHaveLength(2);
  });
});
