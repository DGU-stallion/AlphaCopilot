/**
 * ChartBlock — 把 artifact.payload（ECharts option，由 alpha.chart 产出）渲染为可交互图。
 * 交互能力（legend 切换 / hover 十字 / dataZoom）由 option 自身携带；本组件只负责
 * 挂载 echarts 实例、setOption、随主题/尺寸变化重绘。颜色由 chart-theme.ts 单点注入。
 */

import { useEffect, useRef } from "react";
import { echarts } from "@/lib/echarts";
import { getChartTheme } from "@/lib/chart-theme";
import { useTheme } from "@/theme";

type EChartsOption = Record<string, unknown>;

function applyTheme(option: EChartsOption): EChartsOption {
  const t = getChartTheme();
  // 轻量注入：坐标轴/文本颜色 + tooltip 底色。不覆盖 option 已有的 series 数据。
  return {
    backgroundColor: "transparent",
    textStyle: { color: t.textColor },
    tooltip: {
      backgroundColor: t.tooltipBg,
      borderColor: t.tooltipBorder,
      textStyle: { color: t.tooltipText },
      ...(option.tooltip as object),
    },
    ...option,
  };
}

export function ChartBlock({ option, title }: { option: EChartsOption; title?: string }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<ReturnType<typeof echarts.init> | null>(null);
  const { theme } = useTheme();

  useEffect(() => {
    if (!ref.current) return;
    const inst = echarts.init(ref.current);
    chartRef.current = inst;
    const ro = new ResizeObserver(() => inst.resize());
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      inst.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(applyTheme(option), true);
  }, [option, theme]);

  return (
    <div className="glass rounded-lg p-3">
      {title && <div className="mb-2 text-sm font-medium text-foreground">{title}</div>}
      <div ref={ref} style={{ height: 360, width: "100%" }} data-testid="chart-block" />
    </div>
  );
}
