import { useEffect, useRef, useState } from "react";
import { echarts } from "@/lib/echarts";
import { getChartTheme } from "@/lib/chart-theme";
import { useDarkMode } from "@/hooks/useDarkMode";

interface Props {
  // 后端 alpha.chart 产出的 ECharts option（line / heatmap 等），直接 setOption。
  option: Record<string, unknown> | null;
  className?: string;
  height?: number;
}

// 把设计系统的主题色注入后端产的 option：坐标轴/网格/文字/tooltip 用 CSS 变量色，
// 图表才和玻璃暖橙风一致。只补样式，不改数据结构（series.data 原样）。
/** 给带 semanticScale="pnl-bars" 的柱系列逐柱按正负上色。 */
function retintBars(series: any, t: ReturnType<typeof getChartTheme>): any {
  if (!Array.isArray(series)) return series;
  return series.map((s: any) => {
    if (!s || s.semanticScale !== "pnl-bars" || !Array.isArray(s.data)) return s;
    const { semanticScale: _drop, ...rest } = s;
    return {
      ...rest,
      data: s.data.map((v: any) => (
        typeof v === "number"
          ? { value: v, itemStyle: { color: v >= 0 ? t.upColor : t.downColor } }
          : v
      )),
    };
  });
}

/** 把带 `semanticTone` 的系列按当前 palette 上色（ROUND2 阶段 2）。
 *
 * 为什么需要它：情绪图里的「涨停」必须是涨色、「跌停」必须是跌色，但**颜色
 * 真源在 tokens.ts**（AGENTS 硬规则 7），前端 option 里不能写 `#` 字面量。
 * 所以 option 只标语义（up/down/neutral），由这里换成具体色值。
 *
 * 与 `semanticScale: "pnl-bars"`（逐柱按正负）的区别：那个表达「数值的正负」，
 * 这个表达「这一条线代表的含义就是涨/跌」—— 涨停家数本身永远是正数，
 * 不能靠正负判断。
 */
function retintTone(series: any, t: ReturnType<typeof getChartTheme>): any {
  if (!Array.isArray(series)) return series;
  return series.map((s: any) => {
    if (!s || !s.semanticTone || s.semanticTone === "neutral") return s;
    const { semanticTone, ...rest } = s;
    const color = semanticTone === "up" ? t.upColor : t.downColor;
    return {
      ...rest,
      itemStyle: { ...(s.itemStyle ?? {}), color },
      ...(s.type === "line" ? { lineStyle: { ...(s.lineStyle ?? {}), color } } : {}),
    };
  });
}

/** 把带语义标记的 visualMap 用当前 palette 重上色。 */
function retintPnl(vm: any, t: ReturnType<typeof getChartTheme>): any {
  const apply = (one: any) => {
    if (!one || one.semanticScale !== "pnl") return one;
    const { semanticScale: _drop, ...rest } = one;   // 语义标记不传给 ECharts
    return {
      ...rest,
      inRange: {
        ...(one.inRange ?? {}),
        // 跌色 → 中性 → 涨色。中性别用纯白（浅色主题下会刺眼），用 panel 色。
        color: [t.downColor, t.tooltipBg, t.upColor],
      },
    };
  };
  return Array.isArray(vm) ? vm.map(apply) : apply(vm);
}

function themed(option: Record<string, any>): Record<string, any> {
  const t = getChartTheme();
  const axis = {
    axisLine: { lineStyle: { color: t.axisColor } },
    axisLabel: { color: t.textColor },
    splitLine: { lineStyle: { color: t.gridColor } },
  };
  const applyAxis = (a: any) =>
    Array.isArray(a) ? a.map((x) => ({ ...axis, ...x })) : { ...axis, ...(a ?? {}) };
  return {
    color: t.seriesColors,
    textStyle: { color: t.textColor },
    ...option,
    title: option.title ? { ...option.title, textStyle: { color: t.textColor } } : undefined,
    tooltip: {
      ...(option.tooltip ?? {}),
      backgroundColor: t.tooltipBg,
      borderColor: t.tooltipBorder,
      textStyle: { color: t.tooltipText },
    },
    legend: option.legend ? { ...option.legend, textStyle: { color: t.textColor } } : undefined,
    // 后端产的热力图带 `semanticScale: "pnl"` 时，色阶必须用**当前 palette**
    // 重上色（ADR-0014：颜色真源是 tokens.ts，后端只给语义标记）。
    // 不这样做的话：后端写死「涨=红」，用户切成国际口径后热力图还是红的 ——
    // 同一屏里数字绿了、热力图红着。
    visualMap: retintPnl(option.visualMap, t),
    // 柱状图逐柱按正负上色（后端标 semanticScale: "pnl-bars"）。
    // 不做的话「选股 +5%」和「择时 -12%」是一个颜色，归因图等于没读。
    series: retintTone(retintBars(option.series, t), t),
    xAxis: option.xAxis ? applyAxis(option.xAxis) : undefined,
    yAxis: option.yAxis ? applyAxis(option.yAxis) : undefined,
  };
}

export function EChart({ option, className, height = 320 }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const { dark } = useDarkMode();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!ref.current) return;
    let chart: echarts.ECharts;
    try {
      chart = echarts.init(ref.current);
    } catch (e) {
      console.error("[EChart] init failed", e);
      setFailed(true);
      return;
    }
    chartRef.current = chart;
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    if (!option) {
      chart.clear();
      return;
    }
    // dark 依赖：切主题时重算颜色。notMerge=true 避免残留旧系列。
    // 单个图表的 option 异常不应崩掉整页——捕获并降级为占位。
    try {
      chart.setOption(themed(option), true);
      setFailed(false);
    } catch (e) {
      console.error("[EChart] setOption failed", e, option);
      setFailed(true);
    }
  }, [option, dark]);

  if (failed) {
    return (
      <div className={className} style={{ height }}>
        <p className="flex h-full items-center justify-center text-sm text-muted-foreground/60">
          图表渲染失败（数据格式异常）
        </p>
      </div>
    );
  }
  return <div ref={ref} className={className} style={{ height }} />;
}
