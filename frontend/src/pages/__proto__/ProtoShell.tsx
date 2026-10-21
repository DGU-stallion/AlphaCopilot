/**
 * 🔵 原型 v2（throwaway）—— 回答「ADR-0013 终端风长什么样」。
 *
 * v1 的教训：我把平面深色表格塞进旧的玻璃侧栏里，评审看到的「丑」其实是
 * 旧外壳 + 没有图，而不是 ADR-0013 的方向。所以 v2 做了三件事：
 *   1. **全屏，不套旧 Layout**（旧侧栏的玻璃/暖橙是要删掉的东西）
 *   2. **有真 K 线**（交易界面没图就只是后台管理表格）
 *   3. **克制到近乎无彩色**（一个蓝色强调色，红绿只给涨跌）
 *
 * 访问：/proto/shell?proto=A|B|C
 *   A 单图专注：大 K 线 + 右侧指标栏（TradingView 最常用的形态）
 *   B 多 pane 网格：K线 / 成交量 / 净值·回撤 三 pane 联动
 *   C 极简暗色：只有一个图 + 一条底部状态栏，其余全留白
 *
 * 数据真实：K 线走 /api/kline（本次新增的原型接口），净值/回撤走
 * /api/pages/backtest/render。原型不写库。
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  createChart, CandlestickSeries, LineSeries, HistogramSeries,
  type IChartApi, type ISeriesApi, type CandlestickData, type UTCTimestamp,
} from "lightweight-charts";
import "./proto.css";

// ---------------------------------------------------------------- token
// ADR-0013 §2 的值，比 v1 更克制：面板与背景几乎同色，靠 1px 边框分区。
const T = {
  bg: "#0E1117", panel: "#131722", surf: "#1A1F2B",
  border: "#232838", text: "#D1D4DC", muted: "#787B86", faint: "#4C525E",
  accent: "#4C8DFF", up: "#F04438", down: "#12B76A",
};

// ---------------------------------------------------------------- 数据
type Bar = { datetime: string; open: number; close: number; high: number; low: number; vol: number };

function useKline(code = "600519") {
  const [bars, setBars] = useState<Bar[]>([]);
  const [err, setErr] = useState("");
  useEffect(() => {
    fetch(`/api/kline?code=${code}&offset=180`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((d) => setBars(d?.data?.bars ?? d?.bars ?? []))
      .catch(() => setErr("K 线取不到"));
  }, [code]);
  return { bars, err };
}

type BtBlock = { kind: string; option?: Record<string, unknown> };

function useBacktest(code = "600519") {
  const [blocks, setBlocks] = useState<BtBlock[]>([]);
  useEffect(() => {
    fetch("/api/pages/backtest/render", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol: code, fast: 20, slow: 60, range: "1y", strategy: "dual_ma" }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((d) => setBlocks(d.blocks ?? []))
      .catch(() => {});
  }, [code]);
  return blocks;
}

// ---------------------------------------------------------------- LWC 封装
// ADR-0013：颜色统一注入，不硬编码绿涨红跌（TradingView 默认与国际接轨，A 股相反）。
function useChart(height: number) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  // ⚠️ 不能返回 chartRef.current 的快照：首次 render 时它还是 null，
  // 后面 chart 建好了，组件拿到的仍是 null，图表永远画不出来（实测踩过）。
  // 所以用 state 存 chart 实例，建好时 setState 触发重渲染。
  const [chart, setChart] = useState<IChartApi | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      height,
      layout: {
        background: { color: T.bg },
        textColor: T.muted,
        fontSize: 11,
        // Apache 2.0 + NOTICE 要求署名，一行满足
        attributionLogo: true,
      },
      grid: {
        vertLines: { color: T.border },
        horzLines: { color: T.border },
      },
      rightPriceScale: { borderColor: T.border },
      timeScale: { borderColor: T.border, timeVisible: false },
      crosshair: {
        mode: 1,
        vertLine: { color: T.muted, width: 1, style: 3, labelBackgroundColor: T.surf },
        horzLine: { color: T.muted, width: 1, style: 3, labelBackgroundColor: T.surf },
      },
    });
    chartRef.current = chart;
    setChart(chart);
    const ro = new ResizeObserver(() => {
      if (ref.current) chart.applyOptions({ width: ref.current.clientWidth });
    });
    ro.observe(ref.current);
    return () => { ro.disconnect(); chart.remove(); chartRef.current = null; setChart(null); };
  }, [height]);

  return { ref, chart };
}

const toTs = (d: string) => (Date.parse(d + "T00:00:00Z") / 1000) as UTCTimestamp;

// ---------------------------------------------------------------- 变体 A：单图专注
// TradingView 最常用形态：一张大 K 线占满，指标塞右侧窄栏。
function VariantA() {
  const { bars, err } = useKline();
  const blocks = useBacktest();
  const { ref, chart } = useChart(430);
  const { ref: vref, chart: vchart } = useChart(120);
  const [hover, setHover] = useState<Bar | null>(null);

  useEffect(() => {
    if (!chart || !bars.length) return;
    const candle: ISeriesApi<"Candlestick"> = chart.addSeries(CandlestickSeries, {
      upColor: T.up, downColor: T.down, borderVisible: false,
      wickUpColor: T.up, wickDownColor: T.down,
    });
    candle.setData(bars.map((b): CandlestickData => ({
      time: toTs(b.datetime), open: b.open, high: b.high, low: b.low, close: b.close,
    })));
    chart.timeScale().fitContent();
    chart.subscribeCrosshairMove((p) => {
      const t = p.time as number | undefined;
      if (!t) { setHover(null); return; }
      setHover(bars.find((b) => toTs(b.datetime) === t) ?? null);
    });
    return () => { chart.removeSeries(candle); };
  }, [chart, bars]);

  useEffect(() => {
    if (!vchart || !bars.length) return;
    const s = vchart.addSeries(HistogramSeries, { priceFormat: { type: "volume" } });
    s.setData(bars.map((b, i) => ({
      time: toTs(b.datetime), value: b.vol,
      color: i > 0 && b.close >= bars[i - 1].close ? `${T.up}66` : `${T.down}66`,
    })));
    vchart.timeScale().fitContent();
    return () => vchart.removeSeries(s);
  }, [vchart, bars]);

  const metric = blocks.find((b) => b.kind === "metric");
  const last = bars[bars.length - 1];
  const shown = hover ?? last;
  const chg = shown && last ? shown.close - last.open : 0;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 260px", height: "100%" }}>
      <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
        {/* 顶部价格条：贴图，不占额外高度 */}
        <div style={{ display: "flex", alignItems: "baseline", gap: 16, padding: "8px 12px", borderBottom: `1px solid ${T.border}` }}>
          <span style={{ fontSize: 15, fontWeight: 600 }}>贵州茅台</span>
          <span style={{ fontSize: 11, color: T.faint }}>600519 · 日线</span>
          {shown && (
            <>
              <span style={{ fontSize: 18, color: chg >= 0 ? T.up : T.down, fontVariantNumeric: "tabular-nums" }}>
                {shown.close.toFixed(2)}
              </span>
              <span style={{ fontSize: 12, color: T.muted, fontVariantNumeric: "tabular-nums" }}>
                O {shown.open.toFixed(2)} H {shown.high.toFixed(2)} L {shown.low.toFixed(2)}
              </span>
              <span style={{ fontSize: 11, color: T.faint, fontVariantNumeric: "tabular-nums" }}>
                量 {(shown.vol / 1e4).toFixed(1)}万
              </span>
            </>
          )}
          {err && <span style={{ fontSize: 11, color: T.down }}>{err}</span>}
        </div>
        <div ref={ref} style={{ flex: "0 0 auto" }} />
        <div style={{ borderTop: `1px solid ${T.border}`, padding: "2px 12px", fontSize: 10, color: T.muted }}>成交量</div>
        <div ref={vref} style={{ flex: "0 0 auto" }} />
        {/* 留白区域放「最近 5 根」小表：终端里这一栏是给人扫的，不是装饰 */}
        <div style={{ flex: 1, minHeight: 0, overflow: "auto", borderTop: `1px solid ${T.border}` }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
            <thead>
              <tr style={{ color: T.muted, textAlign: "right" }}>
                <th style={{ padding: "4px 12px", fontWeight: 400, textAlign: "left" }}>日期</th>
                <th style={{ padding: "4px 12px", fontWeight: 400 }}>开</th>
                <th style={{ padding: "4px 12px", fontWeight: 400 }}>高</th>
                <th style={{ padding: "4px 12px", fontWeight: 400 }}>低</th>
                <th style={{ padding: "4px 12px", fontWeight: 400 }}>收</th>
                <th style={{ padding: "4px 12px", fontWeight: 400 }}>涨跌%</th>
                <th style={{ padding: "4px 12px", fontWeight: 400 }}>量(万)</th>
              </tr>
            </thead>
            <tbody>
              {bars.slice(-8).reverse().map((b, i, arr) => {
                const prev = arr[i + 1];
                const pct = prev ? ((b.close - prev.close) / prev.close) * 100 : 0;
                return (
                  <tr key={b.datetime} style={{ borderTop: `1px solid ${T.border}22`, color: T.text }}>
                    <td style={{ padding: "3px 12px", color: T.muted }}>{b.datetime.slice(5)}</td>
                    <td style={{ padding: "3px 12px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{b.open.toFixed(2)}</td>
                    <td style={{ padding: "3px 12px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{b.high.toFixed(2)}</td>
                    <td style={{ padding: "3px 12px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{b.low.toFixed(2)}</td>
                    <td style={{ padding: "3px 12px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{b.close.toFixed(2)}</td>
                    <td style={{ padding: "3px 12px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: pct >= 0 ? T.up : T.down }}>
                      {pct >= 0 ? "+" : ""}{pct.toFixed(2)}%
                    </td>
                    <td style={{ padding: "3px 12px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: T.muted }}>{(b.vol / 1e4).toFixed(1)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* 右：指标栏 */}
      <div style={{ borderLeft: `1px solid ${T.border}`, padding: 12, overflow: "auto" }}>
        <div style={{ fontSize: 10, color: T.muted, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>
          回测指标
        </div>
        {metric ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
            {((metric as { metric?: { items?: { label: string; value: unknown; tone?: string }[] } })
              .metric?.items ?? []).map((it) => (
              <div key={it.label} style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                <span style={{ color: T.muted }}>{it.label}</span>
                <span style={{
                  fontVariantNumeric: "tabular-nums",
                  color: it.tone === "down" ? T.down : it.tone === "up" ? T.up : T.text,
                }}>{String(it.value)}</span>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ fontSize: 12, color: T.faint }}>计算中…</div>
        )}
        <div style={{ height: 1, background: T.border, margin: "14px 0" }} />
        <div style={{ fontSize: 10, color: T.muted, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>
          当前 K 线
        </div>
        {shown && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 12 }}>
            {([["开", shown.open], ["高", shown.high], ["低", shown.low], ["收", shown.close], ["量", shown.vol]] as const).map(([k, v]) => (
              <div key={k} style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: T.muted }}>{k}</span>
                <span style={{ fontVariantNumeric: "tabular-nums" }}>
                  {k === "量" ? `${(v / 1e4).toFixed(1)} 万` : v.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- 变体 B：多 pane 网格
// K线 + 成交量 + 净值/回撤，三段联动。ADR-0013 的「多 pane」能力展示。
function VariantB() {
  const { bars } = useKline();
  const blocks = useBacktest();
  const { ref: kref, chart: kchart } = useChart(300);
  const { ref: vref, chart: vchart } = useChart(90);
  const { ref: nref, chart: nchart } = useChart(160);

  useEffect(() => {
    if (!kchart || !bars.length) return;
    const s = kchart.addSeries(CandlestickSeries, {
      upColor: T.up, downColor: T.down, borderVisible: false, wickUpColor: T.up, wickDownColor: T.down,
    });
    s.setData(bars.map((b) => ({ time: toTs(b.datetime), open: b.open, high: b.high, low: b.low, close: b.close })));
    kchart.timeScale().fitContent();
    return () => kchart.removeSeries(s);
  }, [kchart, bars]);

  useEffect(() => {
    if (!vchart || !bars.length) return;
    const s = vchart.addSeries(HistogramSeries, { priceFormat: { type: "volume" } });
    s.setData(bars.map((b, i) => ({
      time: toTs(b.datetime), value: b.vol,
      color: i > 0 && b.close >= bars[i - 1].close ? `${T.up}66` : `${T.down}66`,
    })));
    vchart.timeScale().fitContent();
    return () => vchart.removeSeries(s);
  }, [vchart, bars]);

  // 净值曲线：从后端 option 里取 series.data（真数据，不是 mock）
  useEffect(() => {
    if (!nchart || !bars.length) return;
    const chartBlock = blocks.filter((b) => b.kind === "chart")[0];
    const series = (chartBlock?.option as { series?: { name?: string; data?: number[] }[] })?.series?.[0];
    if (!series?.data?.length) return;
    const n = series.data.length;
    const dates = bars.slice(-n);
    // LWC 要求 time 严格递增且无重复，否则内部 ensureDefined 直接抛错。
    // 后端净值序列可能与 K 线长度不一致，这里按日期去重再排。
    const seen = new Set<number>();
    const pts: { time: UTCTimestamp; value: number }[] = [];
    series.data.forEach((v, i) => {
      const d = dates[i]?.datetime;
      if (!d || typeof v !== "number" || !Number.isFinite(v)) return;
      const t = toTs(d);
      if (seen.has(t)) return;
      seen.add(t);
      pts.push({ time: t, value: v });
    });
    if (pts.length < 2) return;
    pts.sort((a, b) => (a.time as number) - (b.time as number));
    const s = nchart.addSeries(LineSeries, { color: T.accent, lineWidth: 2 });
    s.setData(pts);
    nchart.timeScale().fitContent();
    return () => nchart.removeSeries(s);
  }, [nchart, bars, blocks]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, padding: "6px 12px", borderBottom: `1px solid ${T.border}` }}>
        <span style={{ fontSize: 14, fontWeight: 600 }}>600519 贵州茅台</span>
        <span style={{ fontSize: 11, color: T.faint }}>日线 · 180 根</span>
      </div>
      <div ref={kref} style={{ flex: "0 0 auto" }} />
      <div style={{ borderTop: `1px solid ${T.border}`, padding: "2px 12px", fontSize: 10, color: T.muted }}>成交量</div>
      <div ref={vref} style={{ flex: "0 0 auto" }} />
      <div style={{ borderTop: `1px solid ${T.border}`, padding: "2px 12px", fontSize: 10, color: T.muted }}>净值（双均线策略）</div>
      <div ref={nref} style={{ flex: "0 0 auto" }} />
    </div>
  );
}

// ---------------------------------------------------------------- 变体 C：极简暗色
// 只有一个图，其余留白。用来判断「少即是多」能否成立。
function VariantC() {
  const { bars } = useKline();
  const { ref, chart } = useChart(620);

  useEffect(() => {
    if (!chart || !bars.length) return;
    const s = chart.addSeries(CandlestickSeries, {
      upColor: T.up, downColor: T.down, borderVisible: false, wickUpColor: T.up, wickDownColor: T.down,
    });
    s.setData(bars.map((b) => ({ time: toTs(b.datetime), open: b.open, high: b.high, low: b.low, close: b.close })));
    chart.timeScale().fitContent();
    return () => chart.removeSeries(s);
  }, [chart, bars]);

  const last = bars[bars.length - 1];
  const prev = bars[bars.length - 2];
  const pct = last && prev ? ((last.close - prev.close) / prev.close) * 100 : 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div ref={ref} style={{ flex: 1, minHeight: 0 }} />
      {/* 底栏：一行放全部元信息，不占视觉重心 */}
      <div style={{
        display: "flex", alignItems: "center", gap: 20, padding: "6px 12px",
        borderTop: `1px solid ${T.border}`, fontSize: 11, color: T.muted,
      }}>
        <span style={{ color: T.text }}>600519 贵州茅台</span>
        {last && (
          <span style={{ color: pct >= 0 ? T.up : T.down, fontVariantNumeric: "tabular-nums" }}>
            {last.close.toFixed(2)} {pct >= 0 ? "+" : ""}{pct.toFixed(2)}%
          </span>
        )}
        <span style={{ marginLeft: "auto", color: T.faint }}>
          数据 腾讯行情 · as-of {last?.datetime ?? "—"}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- 切换
const VARIANTS = [
  { key: "A", name: "单图专注", C: VariantA },
  { key: "B", name: "多 pane 网格", C: VariantB },
  { key: "C", name: "极简暗色", C: VariantC },
] as const;

export function ProtoShell() {
  const [sp, setSp] = useSearchParams();
  const cur = useMemo(() => {
    const k = (sp.get("proto") ?? "A").toUpperCase();
    return VARIANTS.find((v) => v.key === k) ?? VARIANTS[0];
  }, [sp]);

  const i = VARIANTS.findIndex((v) => v.key === cur.key);
  const go = (d: number) => {
    const n = VARIANTS[(i + d + VARIANTS.length) % VARIANTS.length];
    setSp({ proto: n.key }, { replace: true });
  };

  return (
    // 全屏、无侧栏：旧外壳的玻璃/暖橙正是要换掉的东西，不能拿它当背景板
    <div style={{ position: "fixed", inset: 0, background: T.bg, color: T.text, fontFamily: "Inter, system-ui, -apple-system, sans-serif", fontSize: 12 }}>
      <cur.C />
      <div style={{
        position: "fixed", bottom: 14, left: "50%", transform: "translateX(-50%)", zIndex: 50,
        display: "flex", alignItems: "center", gap: 6, borderRadius: 999,
        background: "rgba(0,0,0,0.9)", border: `1px solid ${T.border}`, color: "#fff", padding: "5px 6px",
        boxShadow: "0 8px 28px rgba(0,0,0,.5)",
      }}>
        <button onClick={() => go(-1)} style={{ padding: "0 7px", fontSize: 16, lineHeight: 1, color: "#fff" }}>←</button>
        <span style={{ minWidth: 120, textAlign: "center", fontSize: 12 }}>
          <b>{cur.key}</b> · {cur.name}
        </span>
        <button onClick={() => go(1)} style={{ padding: "0 7px", fontSize: 16, lineHeight: 1, color: "#fff" }}>→</button>
      </div>
    </div>
  );
}
