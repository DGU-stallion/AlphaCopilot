import { useEffect, useRef } from "react";
import {
  createChart, CandlestickSeries, HistogramSeries, LineSeries,
  type IChartApi, type ISeriesApi,
} from "lightweight-charts";
import { usePalette } from "@/theme/usePalette";
import { DARK, FONT, type Palette } from "@/theme/tokens";
import { toCandleData, toVolumeData, paneHeight, type RawBar } from "./kline-data";

/**
 * K 线 + 成交量（M2-6 / ADR-0014 §6 §7）：**一个 chart 实例，两个 pane**。
 *
 * 为什么不是两个 createChart 上下堆叠（v4 原型的做法，已否决）：
 *   - 左右边缘差约 5px（两个实例各自算价格轴宽度）
 *   - 缩放/十字光标不联动（各管各的 timeScale）
 *   - 多一份 canvas 开销、多一处 LWC 署名
 *
 * ⚠️ 三条生命周期纪律（违反过的症状写在每条旁边）：
 *   ① 建实例的 effect 依赖 `[]`。依赖 palette 会在切主题时销毁重建，
 *      而 series 的 cleanup 随后 removeSeries 打到已销毁实例上
 *      → 内部 ensureDefined 抛错 → 整页白屏。
 *   ② 主题变化只 applyOptions，不重建。
 *   ③ 数据变化只 setData，不重建 series（重建会丢缩放位置与十字光标状态）。
 */

export interface PriceChartProps {
  bars: RawBar[];
  /** 只画收盘价折线（净值曲线场景），不画 K 线与成交量 */
  mode?: "candles" | "line";
  height?: number | string;
}

export function PriceChart({ bars, mode = "candles", height = "100%" }: PriceChartProps) {
  const palette = usePalette();
  const boxRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const priceRef = useRef<ISeriesApi<"Candlestick" | "Line"> | null>(null);
  const volRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  // ---------------- ① 建实例：依赖必须为空 ----------------
  useEffect(() => {
    const box = boxRef.current;
    if (!box) return;

    const chart = createChart(box, {
      autoSize: true,                       // 跟随容器尺寸，不用手写 ResizeObserver
      layout: {
        background: { color: "transparent" },
        textColor: DARK.textTertiary,        // 首帧占位，随后 applyOptions 覆盖
        fontFamily: FONT.mono,
        fontSize: 11,
        attributionLogo: false,
      },
      grid: { vertLines: { visible: false }, horzLines: { color: "transparent" } },
      rightPriceScale: {
        borderVisible: false,
        // 边缘刻度宁可不显示，也不要露出半截数字（canvas 会裁掉）
        entireTextOnly: true,
        scaleMargins: { top: 0.08, bottom: 0.08 },
      },
      timeScale: { borderVisible: false, rightOffset: 4, barSpacing: 8 },
      crosshair: { mode: 0 },
      handleScroll: { mouseWheel: false, pressedMouseMove: true },
    });
    chartRef.current = chart;

    // ---------------- ② 主题变化只 applyOptions ----------------
    // 放在建实例之后由独立 effect 处理，见下。这里先放默认色避免首帧闪烁。

    return () => {
      chartRef.current = null;
      priceRef.current = null;
      volRef.current = null;
      // remove() 之后再碰 series 会抛错，所以先把 ref 清空再销毁
      chart.remove();
    };
  }, []);

  // ---------------- series：按 mode 创建一次 ----------------
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    if (mode === "candles") {
      priceRef.current = chart.addSeries(CandlestickSeries, {
        // 首帧占位用 DARK 的值；真实颜色由下面的 palette effect 覆盖
        upColor: DARK.up, downColor: DARK.down,
        borderUpColor: DARK.up, borderDownColor: DARK.down,
        wickUpColor: DARK.up, wickDownColor: DARK.down,
      }, 0);
      // pane 1 = 成交量。每个 pane 自带一条右侧价格轴，不要给 series 指定
      // 自定义 priceScaleId —— 那样必须等轴注册后才能 chart.priceScale(id)，
      // 否则抛 "Trying to apply price scale options with incorrect ID"（踩过）。
      const vol = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" } }, 1);
      vol.priceScale().applyOptions({ scaleMargins: { top: 0.1, bottom: 0 } });
      volRef.current = vol;
    } else {
      priceRef.current = chart.addSeries(
        LineSeries,
        { lineWidth: 2, priceLineVisible: false, lastValueVisible: true },
        0,
      );
    }

    return () => {
      // 只在 mode 真变化时清；chart.remove() 会连带销毁，重复 remove 会抛错
      if (chartRef.current) {
        if (priceRef.current) { try { chart.removeSeries(priceRef.current); } catch { /* 已销毁 */ } }
        if (volRef.current) { try { chart.removeSeries(volRef.current); } catch { /* 已销毁 */ } }
      }
      priceRef.current = null;
      volRef.current = null;
    };
  }, [mode]);

  // ---------------- 主题：只改颜色 ----------------
  useEffect(() => {
    applyPalette(chartRef.current, priceRef.current, volRef.current, palette, mode);
  }, [palette, mode]);

  // ---------------- 数据：只 setData ----------------
  useEffect(() => {
    const price = priceRef.current;
    const vol = volRef.current;
    if (!price) return;

    if (mode === "candles") {
      price.setData(toCandleData(bars) as never);
      vol?.setData(toVolumeData(bars, palette) as never);
    } else {
      price.setData(toCandleData(bars).map((c) => ({ time: c.time, value: c.close })) as never);
    }
  }, [bars, mode, palette]);

  // ---------------- pane 高度：跟容器高度联动 ----------------
  useEffect(() => {
    const box = boxRef.current;
    const chart = chartRef.current;
    if (!box || !chart || mode !== "candles") return;

    const sync = () => {
      const panes = chart.panes();
      if (panes.length > 1) panes[1].setHeight(paneHeight(box.clientHeight));
    };
    sync();
    const ro = new ResizeObserver(sync);
    ro.observe(box);
    return () => ro.disconnect();
  }, [mode, bars]);

  return <div ref={boxRef} style={{ height, width: "100%" }} data-chart="price" />;
}

/* ------------------------------------------------------------------ */

function applyPalette(
  chart: IChartApi | null,
  price: ISeriesApi<"Candlestick" | "Line"> | null,
  vol: ISeriesApi<"Histogram"> | null,
  p: Palette,
  mode: "candles" | "line",
) {
  if (!chart) return;
  chart.applyOptions({
    layout: { background: { color: "transparent" }, textColor: p.textTertiary },
    grid: { horzLines: { color: p.border } },
  });

  if (price) {
    if (mode === "candles") {
      price.applyOptions({
        upColor: p.up, downColor: p.down,
        borderUpColor: p.up, borderDownColor: p.down,
        wickUpColor: p.up, wickDownColor: p.down,
      });
    } else {
      price.applyOptions({ color: p.accent });
    }
  }
  if (vol) {
    vol.applyOptions({
      // 量柱颜色带透明度，避免盖过 K 线；每根的颜色在数据里逐条给
      lastValueVisible: false,
      priceLineVisible: false,
    });
  }
}
