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
/** 把带 semanticScale="pnl" 的 visualMap 用当前 palette 重上色。 */
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
