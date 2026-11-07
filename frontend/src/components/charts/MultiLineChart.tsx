/**
 * 多线时间序列（ROUND3 D5）—— 相关性叠加走势：**一个 chart 实例，N 条线同 pane**。
 *
 * 为什么是同一个 pane 而不是 pane 分区：分 pane 是给「量纲不同」的场景
 * （净值 1.0 附近 vs 回撤 -0.2 —— ADR-0014 §6 的 EquityChart）。相关性叠加
 * 的每条线都是「起点 = 100」的相对走势，量纲相同，分区只会让它们各自缩放、
 * 看起来互不相干。这里 N 条线共享一条价格轴、一条时间轴，缩放与十字光标天然联动。
 *
 * 为什么不用两个/多个 chart 实例：左右边缘差约 5px、缩放与十字光标不联动、
 * 多一份 canvas 开销、多一处 LWC 署名（ADR-0014 §6，v4 实测）。
 *
 * ⚠️ 三条生命周期纪律与 PriceChart.tsx 完全一致（违反过的症状见那边注释）：
 *   ① 建实例的 effect 依赖 `[]`。依赖 palette 会在切主题时销毁重建，
 *      而 series 的 cleanup 随后 removeSeries 打到已销毁实例上 → 整页白屏。
 *   ② 主题变化只 applyOptions，不重建。
 *   ③ 数据变化只 setData，不重建 series（重建会丢缩放位置与十字光标状态）。
 *
 * 颜色不在组件里写死（硬规则 7）：序列色取自 `lib/chart-theme` 的 seriesColors
 * ——它与 `<ChartLegend>` 用的**同一份**序列，所以线上颜色与图例色块必然一致。
 */

import { useEffect, useRef } from "react";
import {
  createChart, LineSeries, LineStyle,
  type IChartApi, type IPriceLine, type ISeriesApi,
} from "lightweight-charts";
import { usePalette } from "@/theme/usePalette";
import { DARK, FONT, type Palette } from "@/theme/tokens";
import { getChartTheme } from "@/lib/chart-theme";
import { ChartLegend } from "@/components/ui/ChartLegend";
import { toEquityLines, type LwcPayload } from "./equity-data";

export interface MultiLineChartProps {
  payload: LwcPayload | null;
  /** 容器高度（默认 260：相关性叠加是主图，比单线图给得高一点） */
  height?: number | string;
}

export function MultiLineChart({ payload, height = 260 }: MultiLineChartProps) {
  const palette = usePalette();
  const boxRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const linesRef = useRef<ISeriesApi<"Line">[]>([]);
  const zeroRef = useRef<IPriceLine | null>(null);

  // 脏数据兜底（点数 < 2 / 时间非严格递增）在后端契约的同一套工具里做，
  // 与 EquityChart 共用 —— 前端不做数值计算（硬规则 6）。
  const lines = toEquityLines(payload);
  const lineCount = lines.length;

  // ---------------- ① 建实例：依赖必须为空 ----------------
  useEffect(() => {
    const box = boxRef.current;
    if (!box) return;

    const chart = createChart(box, {
      autoSize: true,
      layout: {
        background: { color: "transparent" },
        textColor: DARK.textTertiary,       // 首帧占位，随后 applyPalette 覆盖
        fontFamily: FONT.mono,
        fontSize: 11,
        attributionLogo: false,
      },
      grid: { vertLines: { visible: false }, horzLines: { color: "transparent" } },
      rightPriceScale: {
        borderVisible: false,
        entireTextOnly: true,               // 宁可不显示，也不露半截数字
        scaleMargins: { top: 0.12, bottom: 0.12 },
      },
      timeScale: { borderVisible: false, rightOffset: 4 },
      crosshair: { mode: 0 },
      // 滚轮缩放会吃掉页面滚动（PriceChart 同样关掉）；拖拽时间轴/价格轴仍可缩放。
      // 用户要的「TradingView 式交互」= 十字光标 + 拖拽缩放，不是抢页面滚动。
      handleScroll: { mouseWheel: false, pressedMouseMove: true },
    });
    chartRef.current = chart;

    return () => {
      chartRef.current = null;
      linesRef.current = [];
      zeroRef.current = null;
      // remove() 之后再碰 series 会抛错，所以先把 ref 清空再销毁
      chart.remove();
    };
  }, []);

  // ---------------- series：只在条数变化时增删 ----------------
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    for (const s of linesRef.current) {
      try { chart.removeSeries(s); } catch { /* 已销毁 */ }
    }
    linesRef.current = [];
    zeroRef.current = null;

    const colors = getChartTheme().seriesColors;
    for (let i = 0; i < lineCount; i += 1) {
      linesRef.current.push(chart.addSeries(LineSeries, {
        color: colors[i % colors.length],   // 调色板不够时按序回绕
        lineWidth: 2,
        priceLineVisible: false,
        // 多条线时只留十字光标，不显示每条的右轴标签（会叠在一起看不清）
        lastValueVisible: lineCount === 1,
      }, 0));
    }

    // 0 基线：相关性为负时能一眼看出上下分界。挂在第一条 series 上
    // （LWC 的 price line 必须属于某条 series），首色占位随后由主题 effect 覆盖。
    const first = linesRef.current[0];
    if (first) {
      zeroRef.current = first.createPriceLine({
        price: 0,
        color: DARK.borderStrong,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: false,
        title: "",
      });
    }

    return () => {
      linesRef.current = [];
      zeroRef.current = null;
    };
  }, [lineCount]);

  // ---------------- ② 主题：只改颜色（不重建） ----------------
  useEffect(() => {
    applyPalette(chartRef.current, linesRef.current, zeroRef.current, palette);
  }, [palette, lineCount]);

  // ---------------- ③ 数据：只 setData ----------------
  useEffect(() => {
    lines.forEach((line, i) => {
      linesRef.current[i]?.setData(line.points as never);
    });
  }, [payload, lineCount]);

  const empty = lineCount === 0;

  return (
    <div data-chart="multi-line-wrap">
      {/* 图例在 HTML 层自绘：图里不放 legend（窄容器会被它压住绘图区） */}
      {lineCount > 1 && <ChartLegend items={lines.map((l) => l.name)} />}
      {/* 容器常驻：数据从空到有不需要重建 chart 实例 */}
      <div
        ref={boxRef}
        style={{ height, width: "100%", display: empty ? "none" : undefined }}
        data-chart="multi-line"
      />
      {empty && (
        <p className="py-8 text-center text-[12px] text-muted-foreground/60">
          序列数据暂不可用
        </p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */

function applyPalette(
  chart: IChartApi | null,
  lines: ISeriesApi<"Line">[],
  zero: IPriceLine | null,
  p: Palette,
) {
  if (!chart) return;
  const colors = getChartTheme().seriesColors;
  chart.applyOptions({
    layout: { background: { color: "transparent" }, textColor: p.textTertiary },
    grid: { horzLines: { color: p.border } },
  });
  lines.forEach((s, i) => s.applyOptions({ color: colors[i % colors.length] }));
  zero?.applyOptions({ color: p.borderStrong });
}
