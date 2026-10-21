/**
 * 前端设计系统守门测试（ADR-0014）。
 *
 * 这些测试**不测渲染结果**，测的是「纪律有没有被破坏」——因为 M2 最容易
 * 出的问题不是功能坏，而是规则慢慢失效：某天有人顺手写了个 `#3B82F6`，
 * 某天有人又用 `.toFixed()` 直接渲染数字，某天有人把 K 线和成交量拆成两个
 * chart 实例。这些都不会让测试变红，只会让观感一致性一点点烂掉。
 *
 * 所以这里用源码扫描的方式把规则钉住。每一条都写清「违反了会怎样」。
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..", "..");

/** 递归收集 .ts/.tsx 源码（跳过测试目录与原型目录）。 */
function collect(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) {
      if (name === "node_modules" || name === "__tests__") continue;
      collect(full, out);
    } else if (/\.tsx?$/.test(name)) {
      out.push(full);
    }
  }
  return out;
}

/** 全部生产源码（原型目录已于 M2 完成时删除，不再有豁免）。 */
function prodFiles(): { path: string; rel: string; src: string }[] {
  return collect(SRC)
    .map((p) => ({ path: p, rel: relative(SRC, p), src: readFileSync(p, "utf8") }));
}

describe("设计 token 单一真源", () => {
  it("颜色字面量只能出现在 theme/tokens.ts 里", () => {
    // 违反的后果：同一种蓝在 5 个文件里是 5 个略有差别的值，
    // 切主题时有的变了有的没变，观感失控。
    // 例外：proto.css 里的原型 token（不参与生产）。
    const allowed = ["theme/tokens.ts", "lib/chart-theme.ts"];
    const offenders = prodFiles()
      .filter((f) => !allowed.includes(f.rel.replace(/\\/g, "/")))
      .filter((f) => /#[0-9A-Fa-f]{6}\b/.test(f.src))
      .map((f) => f.rel);

    expect(
      offenders,
      "颜色必须来自 theme/tokens.ts，不要在组件里写死 hex：\n" + offenders.join("\n"),
    ).toEqual([]);
  });
});

describe("数字渲染唯一路径", () => {
  it("toFixed 不能直接出现在 JSX 里（必须走 <Num>）", () => {
    // 违反的后果：那一处数字没用等宽字体，表格里会跳；
    // 也没走涨跌色，同一行里两种配色打架。
    // Num 组件自身与图表坐标轴格式化除外（图表内部不走 DOM 文本）。
    const offenders: string[] = [];
    for (const f of prodFiles()) {
      const rel = f.rel.replace(/\\/g, "/");
      if (rel.includes("components/Num")) continue;
      // 只抓「JSX 里直接渲染」的形态：`{x.toFixed(2)}`，且该 `{` 不在模板字符串里。
      // 合法的三类要排除：
      //   · 模板字符串里的（`权重和 ${total.toFixed(3)}`）——错误消息，不是渲染数字
      //   · 格式函数内部的（formatters.ts）——它本身就被 <Num> 之类调用
      //   · 算术表达式里的（`{(i/n*W).toFixed(1)}`）——坐标计算
      const lines = f.src.split("\n");
      lines.forEach((line, i) => {
        const m = line.match(/\{\s*([A-Za-z_$][\w.$]*)\.toFixed\(\s*\d+\s*\)\s*\}/);
        if (!m) return;
        // 模板字符串内（同一行里该位置之前有 ` 且后面还有 `）视为字符串拼接
        const before = line.slice(0, m.index ?? 0);
        const backticks = (before.match(/`/g) ?? []).length;
        if (backticks % 2 === 1) return;              // 在模板字符串里
        if (rel.includes("lib/formatters")) return;   // 格式函数本身
        offenders.push(`${rel}:${i + 1}: ${m[0]}`);
      });
    }
    expect(
      offenders,
      "数字请用 <Num v={x} />，不要裸写 .toFixed()：\n" + offenders.join("\n"),
    ).toEqual([]);
  });
});

describe("图表实例纪律（ADR-0014 §6/§7）", () => {
  it("LWC 多图必须用 pane，不能出现两个独立 createChart 拼在一起", () => {
    // 违反的后果（v4 实测）：左右边缘差 5px 对不齐、缩放不联动、
    // 多一份 canvas 开销。这条只能靠扫描「同一文件里 createChart 出现次数」守住。
    const offenders: string[] = [];
    for (const f of prodFiles()) {
      const rel = f.rel.replace(/\\/g, "/");
      const n = (f.src.match(/createChart\s*\(/g) ?? []).length;
      if (n > 1) offenders.push(`${rel}: createChart × ${n}`);
    }
    expect(
      offenders,
      "一个文件里只应有一处 createChart；多图请用 addSeries(..., paneIndex)：\n" +
        offenders.join("\n"),
    ).toEqual([]);
  });

  it("建 chart 的 effect 不能依赖 palette（否则切主题白屏）", () => {
    // 违反的后果（v3 实测）：切主题销毁重建 chart → series 的 cleanup
    // 随后 removeSeries 打到已销毁实例 → ensureDefined 抛错 → 整页白屏。
    const offenders: string[] = [];
    for (const f of prodFiles()) {
      const rel = f.rel.replace(/\\/g, "/");
      // 找 `createChart(` 之后的第一个 `}, [` 依赖数组里是否含 palette
      const idx = f.src.search(/createChart\s*\(/);
      if (idx < 0) continue;
      const after = f.src.slice(idx);
      const dep = after.match(/\}\s*,\s*\[([^\]]*)\]\s*\)/);
      if (dep && /palette/.test(dep[1])) {
        offenders.push(`${rel}: 依赖数组含 palette → [${dep[1]}]`);
      }
    }
    expect(
      offenders,
      "建 chart 的 effect 依赖必须为空数组，主题变化走 applyOptions：\n" +
        offenders.join("\n"),
    ).toEqual([]);
  });
});

describe("禁用的旧视觉残留（ADR-0013 §5）", () => {
  it("生产源码不得出现 glass / shadow-glow / backdrop-blur / rounded-2xl", () => {
    // 违反的后果：旧设计系统的视觉噪音回到界面里。
    const banned = ["glass", "shadow-glow", "backdrop-blur", "rounded-2xl"];
    const offenders: string[] = [];
    for (const f of prodFiles()) {
      const rel = f.rel.replace(/\\/g, "/");
      for (const b of banned) {
        if (f.src.includes(b)) offenders.push(`${rel}: ${b}`);
      }
    }
    expect(
      offenders,
      "这些是 ADR-0013 §5 要求清掉的旧视觉语言：\n" + offenders.join("\n"),
    ).toEqual([]);
  });
});

describe("带符号的数字不能被固定语义类包裹", () => {
  it("不得用 text-danger / text-success 包 <Num pct>（与按符号上色打架）", () => {
    // 抓到的真实 bug：`最好 <b className="text-success"><Num pct inheritColor/>`
    // 「最好」被当成「好=绿」，但 A 股口径下正收益是红 —— 于是 +24.12% 显示成绿色，
    // 而同一屏其他地方的正收益是红的。用户读到的是「同一类事实两种颜色」。
    //
    // 正确做法：pct 已经有按符号上色，不要再套固定语义类。
    // 这条测试用一个结构性规则替代「靠人眼看截图」。
    const offenders: string[] = [];
    for (const f of prodFiles()) {
      const rel = f.rel.replace(/\\/g, "/");
      const lines = f.src.split("\n");
      lines.forEach((line, i) => {
        const hasFixed = /text-(danger|success)[^\n]*<Num/.test(line);
        const hasPct = /<Num[^/]*\bpct\b/.test(line);
        if (hasFixed && hasPct) offenders.push(`${rel}:${i + 1}: ${line.trim().slice(0, 90)}`);
      });
    }
    expect(
      offenders,
      "带符号数值不要用固定语义类包裹（Num 的 pct 会按符号上色，两者会打架）：\n" +
        offenders.join("\n"),
    ).toEqual([]);
  });
});

describe("ECharts 自带 legend 停用（M2-8 缺陷 1）", () => {
  it("pages 代码不得把 legend 传给 ECharts —— 多系列图例统一自绘", () => {
    // 违反的后果：ECharts legend 的自动布局假定「容器够宽」；多系列名一行放不下时
    // 不换行，而是与 title / grid 争夺顶部空间，在两列窄面板里侵入绘图区盖住曲线。
    //
    // 规则要精确到「传给 ECharts 的 option 里出现 legend」，不能禁词：
    // 页面完全可以自己有 legend 变量、或自绘 HTML 图例（Backtest 页就是这么做的，
    // 第一版规则用禁词误报了它 —— 守门测试误报会让人开始绕过它，那比没有更糟）。
    // 真正要禁的形态：option 对象字面量里出现 legend / option.legend 赋值。
    const offenders = prodFiles()
      .filter((f) => /(^|\/)pages\//.test(f.rel.replace(/\\/g, "/")))
      .filter((f) => /(^\s*|[{,]\s*)legend\s*:/.test(f.src) || /\.legend\s*=/.test(f.src))
      .map((f) => f.rel);
    expect(
      offenders,
      "图例一律经 ChartLegend 自绘，页面不要给 ECharts 传/提 legend：\n" + offenders.join("\n"),
    ).toEqual([]);
  });
});
