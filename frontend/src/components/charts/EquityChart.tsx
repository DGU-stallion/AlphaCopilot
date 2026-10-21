/**
 * 净值 + 回撤（M2-6 / ADR-0014 §6 §7）：一个 chart 实例，两个 pane。
 *
 * 为什么回撤不单独一张图：分开画时两张图的时间轴各自缩放，
 * 「回撤最深的那段对应净值哪一段」要靠眼睛在两图之间来回找。
 * 同一个实例的 pane 共享时间轴，缩放/十字光标天然同步。
 */
import { useEffect, useRef } from "react";
import {
  createChart, LineSeries, AreaSeries,
  type IChartApi, type ISeriesApi,
} from "lightweight-charts";
import { usePalette } from "@/theme/usePalette";
import { DARK, FONT, type Palette } from "@/theme/tokens";
import { paneHeight } from "./kline-data";
import { toDrawdown, toEquityLines, seriesColor, type LwcPayload } from "./equity-data";

export interface EquityChartProps {
  payload: LwcPayload | null;
  height?: number | string;
}

export function EquityChart({ payload, height = 360 }: EquityChartProps) {
  const palette = usePalette();
  const boxRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const linesRef = useRef<ISeriesApi<"Line">[]>([]);
  const ddRef = useRef<ISeriesApi<"Area"> | null>(null);

  // ① 建实例：依赖 []（依赖 palette 会在切主题时销毁重建 → 白屏）
  useEffect(() => {
    const box = boxRef.current;
    if (!box) return;
    const chart = createChart(box, {
      autoSize: true,
      layout: {
        background: { color: "transparent" },
        textColor: DARK.textTertiary,
        fontFamily: FONT.mono,
        fontSize: 11,
        attributionLogo: false,
      },
      grid: { vertLines: { visible: false }, horzLines: { color: "transparent" } },
      rightPriceScale: {
        borderVisible: false,
        entireTextOnly: true,          // 边缘刻度宁可不显示，也不露半截数字
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      timeScale: { borderVisible: false, rightOffset: 3 },
      crosshair: { mode: 0 },
      handleScroll: { mouseWheel: false },
    });
    chartRef.current = chart;
    return () => {
      chartRef.current = null;
      linesRef.current = [];
      ddRef.current = null;
      chart.remove();
    };
  }, []);

  // ② 系列数量变化时重建（只在条数变化时，不是每次数据变化）
  const lineCount = toEquityLines(payload).length;
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    // 清掉旧系列（数量变了才走到这里）
    for (const s of linesRef.current) { try { chart.removeSeries(s); } catch { /* 已销毁 */ } }
    linesRef.current = [];
    if (ddRef.current) { try { chart.removeSeries(ddRef.current); } catch { /* 已销毁 */ } ddRef.current = null; }

    for (let i = 0; i < lineCount; i += 1) {
      linesRef.current.push(chart.addSeries(LineSeries, {
        lineWidth: 2, priceLineVisible: false, lastValueVisible: i === 0,
      }, 0));
    }
    // 回撤放 pane 1，面积图填到 0 轴
    ddRef.current = chart.addSeries(AreaSeries, {
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      topColor: `${DARK.down}55`,
      bottomColor: `${DARK.down}08`,
    }, 1);
    return () => {
      linesRef.current = [];
      ddRef.current = null;
    };
  }, [lineCount]);

  // ③ 主题变化只 applyOptions
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    chart.applyOptions({
      layout: { background: { color: "transparent" }, textColor: palette.textTertiary },
      grid: { horzLines: { color: palette.border } },
    });
    linesRef.current.forEach((s, i) => s.applyOptions({ color: seriesColor(i, palette) }));
    ddRef.current?.applyOptions({
      // 回撤用「跌色」：A 股口径是绿，国际口径是红（palette 已处理）
      topColor: `${palette.down}55`,
      bottomColor: `${palette.down}08`,
    });
  }, [palette, lineCount]);

  // ④ 数据变化只 setData
  useEffect(() => {
    const lines = toEquityLines(payload);
    lines.forEach((line, i) => {
      const s = linesRef.current[i];
      if (s) s.setData(line.points as never);
    });
    const dd = toDrawdown(payload);
    // 回撤为空时也要 setData([])，不能用 `if (dd.length)` 跳过 ——
    // 跳过会让**上一个 payload 的回撤**留在 pane 里，于是净值和回撤
    // 讲的是两个不同的时间区间（review 指出的残留问题）。
    ddRef.current?.setData(dd as never);
  }, [payload, lineCount]);

  // ⑤ pane 高度随容器
  useEffect(() => {
    const box = boxRef.current;
    const chart = chartRef.current;
    if (!box || !chart) return;
    const sync = () => {
      const panes = chart.panes();
      if (panes.length > 1) panes[1].setHeight(paneHeight(box.clientHeight));
    };
    sync();
    const ro = new ResizeObserver(sync);
    ro.observe(box);
    return () => ro.disconnect();
  }, [lineCount, payload]);

  return <div ref={boxRef} style={{ height, width: "100%" }} data-chart="equity" />;
}

/** 供页面取系列颜色画 HTML 图例（与图里线的颜色必须一致）。 */
export function equityLegend(payload: LwcPayload | null, p: Palette) {
  return toEquityLines(payload).map((s, i) => ({ name: s.name, color: seriesColor(i, p) }));
}
