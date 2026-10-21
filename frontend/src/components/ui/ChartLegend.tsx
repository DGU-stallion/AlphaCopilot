import { SIZE } from "@/theme/tokens";
import { getChartTheme } from "@/lib/chart-theme";
import { usePalette } from "@/theme/usePalette";
import { cn } from "@/lib/utils";

/**
 * 图表图例（HTML 自绘版）。
 *
 * 为什么不用 ECharts 自带 legend（M2-8 缺陷 1 的根因）：
 * ECharts 的 legend 自动布局假设「容器足够宽」，一行放不下时**不会换行**，
 * 而是直接与 title / grid 争夺顶部空间 —— 窄容器（两列面板）里
 * 4 个系列名的 legend 会侵入绘图区，把曲线盖住。这不是容器高度的问题，
 * 是 ECharts 默认布局在窄容器下不可控。
 *
 * 约定：**页面代码不给 ECharts option 传 legend**（守门测试钉住，
 * design-system.test.ts「页面不渲染 ECharts 自带 legend」）；
 * 多系列图例一律由本组件在图表上方自绘 —— 位置天然在绘图区之外，无重叠。
 *
 * 颜色序与 EChart 注入的 `chart-theme.seriesColors` 一致（序列 0..n 依次取色），
 * 主题/涨跌口径变化经 usePalette 订阅跟随，不写死 hex（硬规则 7）。
 */
export function ChartLegend({ items, className }: { items: string[]; className?: string }) {
  // 订阅主题与口径：class 变化时重渲染，getChartTheme 缓存按 class 失效即换色。
  usePalette();
  const colors = getChartTheme().seriesColors;
  const shown = items.filter(Boolean);
  if (shown.length === 0) return null;
  return (
    <div className={cn("mb-1 flex flex-wrap items-center gap-x-4 gap-y-1", className)}>
      {shown.map((label, i) => (
        <span key={`${label}-${i}`} className="inline-flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-2 shrink-0 rounded-[2px]"
            style={{ background: colors[i % colors.length] }}
          />
          <span className="text-muted-foreground" style={{ fontSize: SIZE.xs }}>
            {label}
          </span>
        </span>
      ))}
    </div>
  );
}

/**
 * 类型安全取 chart 块 option 的系列名（供 ChartLegend 用）。
 */
export function chartSeriesNames(option: Record<string, unknown> | null | undefined): string[] {
  const series = (option as { series?: unknown } | null | undefined)?.series;
  if (!Array.isArray(series)) return [];
  return series
    .map((s) => (typeof s === "object" && s !== null ? (s as { name?: unknown }).name : undefined))
    .filter((n): n is string => typeof n === "string");
}

/**
 * 页面对后端 option 只接管「展示件」：title 由页面的 <h3> 渲染、
 * legend 由 <ChartLegend> 自绘，其余（数据 series / 坐标轴 / tooltip）原样。
 * 返回 null 当 option 缺失。
 */
export function bareChartOption(
  option: Record<string, unknown> | null | undefined,
): Record<string, unknown> | null {
  if (!option) return null;
  const rest = { ...option };
  delete rest.title;
  delete rest.legend;
  return rest;
}
