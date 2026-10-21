import { useEffect, useRef, useState } from "react";
import { Play, RefreshCw, X, Plus } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { Caliber } from "@/components/ui/Caliber";
import { EChart } from "@/components/ui/EChart";
import { Num } from "@/components/Num";
import { ChartLegend, bareChartOption, chartSeriesNames } from "@/components/ui/ChartLegend";
import { api } from "@/lib/api";
import { useCachedResource } from "@/lib/cache";
import { renderPage, type RenderBlock, type RenderResult } from "@/lib/research";
import { useAiPage } from "@/lib/ai-page";

// 相关性分析 —— 多标的对比。后端 correlation.* 白名单函数：
//   overlay 归一化叠加走势（起点=100，看相对强弱）
//   matrix  日收益率皮尔逊相关矩阵热图（基于收益率而非价格，避免伪相关）
//   rolling 前两标的滚动窗口相关（看相关性随时间变化）
// 缓存：切页不重取；改标的/窗口点「计算」才重拉（cacheKey 带参数）。AI 占位(S5)。

const MAX = 8;

// ---- 相关矩阵：正方形格子（M2-8 缺陷 2）-----------------------------------
// ECharts heatmap 的格子 = 绘图区均分 (n,n)；格子不拉伸 ⇔ 绘图区宽 = 高。
// 后端产出的 grid（left 80 / bottom 80 + visualMap 缩在底部）是按整宽设计的，
// 两列布局下格子被压成矩形。这里改由页面接管布局：visualMap 挪到右侧竖排、
// grid 四边收紧，再按容器实测宽反解出容器高（height 使绘图区恰为正方形）。

/** 实测元素内容宽度（ResizeObserver；侧栏折叠时也能跟上）。 */
function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T | null>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const cr = entries[0]?.contentRect;
      if (cr?.width) setW(Math.round(cr.width));
    });
    ro.observe(el);
    setW(Math.round(el.getBoundingClientRect().width));
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

/** 轴标签像素宽估算（12px 字号）：全角字符 12、其余 6.6，另加 4px 缓冲。 */
function labelPixelWidth(s: string): number {
  let w = 0;
  for (const ch of s) w += ch.charCodeAt(0) > 0xff ? 12 : 6.6;
  return w + 4;
}

const PAD = 4;        // grid 四边留白
const VISMAP_W = 56;  // 右侧竖排 visualMap（手柄 + 可拖拽手柄头）总占宽估算

function MatrixPanel({ block }: { block: RenderBlock }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const base = bareChartOption(block.option) as
    | { xAxis?: { data?: string[] }; yAxis?: unknown; visualMap?: unknown }
    | null;

  const labels = base?.xAxis?.data ?? [];
  const n = Math.max(labels.length, 1);
  const maxLabelW = Math.max(1, ...labels.map(labelPixelWidth));
  // 绘图区宽：容器宽 − grid 四边 − visualMap 占位 − y 轴标签宽（containLabel 计入）
  const plotW = Math.max(240, width - PAD * 2 - VISMAP_W - maxLabelW);
  // x 轴标签：一行放得下就横排，否则斜 45°（高按斜投影估算）
  const rot = maxLabelW > plotW / n;
  const labelH = rot ? Math.ceil(maxLabelW * 0.75) + 8 : 18;
  // 绘图区高 = plotW（正方形的另一半）：height = plotW + 上下留白 + x 标签高
  const height = Math.ceil(plotW + PAD * 2 + labelH);

  const square: Record<string, unknown> | null = base
    ? {
        ...base,
        grid: { left: PAD, right: PAD + VISMAP_W, top: PAD, bottom: PAD, containLabel: true },
        xAxis: { ...base.xAxis, axisLabel: { interval: 0, ...(rot ? { rotate: 45 } : {}) } },
        yAxis: { ...(base.yAxis as Record<string, unknown> | undefined), axisLabel: { interval: 0 } },
        visualMap:
          base.visualMap && !Array.isArray(base.visualMap)
            ? {
                ...(base.visualMap as Record<string, unknown>),
                orient: "vertical",
                left: undefined,
                bottom: undefined,
                right: PAD,
                top: "center",
              }
            : base.visualMap,
      }
    : null;

  return (
    <Panel>
      {block.title && <h3 className="mb-2 text-sm font-semibold">{block.title}</h3>}
      <div ref={ref} className="w-full" style={{ height }}>
        {/* key 带实测宽：侧栏折叠改变容器宽时重建实例（EChart 只监听 window resize）*/}
        <EChart key={width || "init"} option={width > 0 ? square : null} height={height} />
      </div>
    </Panel>
  );
}

export function Correlation() {
  const [symbols, setSymbols] = useState<string[]>(["600519", "000858", "000568", "002304"]);
  const [draft, setDraft] = useState("");
  const [window, setWindow] = useState("60");
  const [inputErr, setInputErr] = useState("");
  const [params, setParams] = useState({ symbols: ["600519", "000858", "000568", "002304"], window: 60, range: "1y" });

  // code->name 映射，仅为展示更直观。api.quote 拿不到时静默降级（chip 只显代码）。
  const [names, setNames] = useState<Record<string, string>>({});
  useEffect(() => {
    const missing = symbols.filter((c) => !(c in names));
    if (missing.length === 0) return;
    let alive = true;
    api.quote(missing.join(","))
      .then((qs) => {
        if (!alive) return;
        setNames((prev) => {
          const next = { ...prev };
          for (const c of missing) next[c] = qs[c]?.name || "";
          return next;
        });
      })
      .catch(() => { /* 名称拉取失败静默降级，不阻塞主流程 */ });
    return () => { alive = false; };
  }, [symbols, names]);

  const key = `corr:${params.symbols.join(",")}:${params.window}:${params.range}`;
  const res = useCachedResource<RenderResult>(key, () => renderPage("correlation", params));

  // 向全局 AI 浮标登记本页确定性数据快照，作对话上下文。
  useAiPage({
    key,
    title: "相关性分析",
    context:
      `对比标的：${params.symbols.map((c) => `${c}${names[c] ? `(${names[c]})` : ""}`).join("、")}\n` +
      `滚动窗口：${params.window} 日；区间：${params.range}\n` +
      `分析口径：收益率皮尔逊相关矩阵 + 归一化叠加走势 + 滚动相关（基于收益率，非价格伪相关）`,
    suggestions: ["这几只标的相关性说明什么", "怎么理解收益率相关矩阵", "相关性高低对分散风险的意义"],
  });

  const addSymbol = () => {
    const code = draft.trim();
    if (!(code.length === 6 && /^\d+$/.test(code))) { setInputErr("标的须为 6 位数字 A 股代码"); return; }
    if (symbols.includes(code)) { setInputErr("该标的已在列表"); return; }
    if (symbols.length >= MAX) { setInputErr(`最多 ${MAX} 个标的`); return; }
    setSymbols([...symbols, code]); setDraft(""); setInputErr("");
  };
  const removeSymbol = (c: string) => setSymbols(symbols.filter((s) => s !== c));

  const run = () => {
    if (symbols.length < 2) { setInputErr("至少 2 个标的才能算相关"); return; }
    const w = parseInt(window, 10);
    if (!(w >= 5 && w <= 250)) { setInputErr("滚动窗口须在 5~250"); return; }
    setInputErr("");
    setParams({ symbols, window: w, range: "1y" });
  };

  const blocks = res.data?.blocks ?? [];
  const [overlay, matrix, rolling] = blocks;
  const err = res.error;

  // ECharts 自带的图例已停用（窄容器会压住绘图区，见 ChartLegend.tsx）：
  // 标题由 <h3> 渲染、图例由 <ChartLegend> 在图上方自绘，连重叠的可能性一起拿掉。
  const bare = (b?: (typeof blocks)[number]) =>
    b ? { block: b, option: bareChartOption(b.option) } : null;
  const overlayB = bare(overlay);
  const rollingB = bare(rolling);

  return (
    <div className="space-y-4">
      <PageHeader
        title="相关性分析"
        subtitle="多标的归一化叠加走势 + 日收益率相关矩阵 · 确定性计算"
        meta={
          <>
            滚动窗口 <Num v={params.window} digits={0} /> 日 · 区间 {params.range}
          </>
        }
      />

      <Panel>
        <div className="mb-2 flex items-center gap-2">
          <label className="text-xs text-muted-foreground">标的列表（2~{MAX} 个 A 股）</label>
          <Caliber text={"相关性基于对齐日期后的日收益率皮尔逊系数计算（非价格，避免伪高相关）。叠加走势归一化到起点=100。"} />
        </div>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          {symbols.map((c) => (
            <span key={c} className="inline-flex items-center gap-1 rounded-full border border-border bg-black/20 px-2.5 py-1 font-mono text-xs">
              {names[c] ? `${names[c]} ${c}` : c}
              <button onClick={() => removeSymbol(c)} className="text-muted-foreground/50 hover:text-destructive"><X className="h-3 w-3" /></button>
            </span>
          ))}
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">添加标的</label>
            <div className="flex gap-1">
              <input value={draft} onChange={(e) => setDraft(e.target.value.replace(/[^\d]/g, ""))} maxLength={6}
                onKeyDown={(e) => { if (e.key === "Enter") addSymbol(); }} placeholder="600519"
                className="w-28 rounded-lg border border-border bg-black/20 px-3 py-2 text-sm outline-none focus:border-primary/50" />
              <button onClick={addSymbol} className="rounded-lg border border-border px-2 text-muted-foreground hover:text-primary"><Plus className="h-4 w-4" /></button>
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">滚动窗口（日）</label>
            <input value={window} onChange={(e) => setWindow(e.target.value.replace(/[^\d]/g, ""))}
              className="w-24 rounded-lg border border-border bg-black/20 px-3 py-2 text-sm outline-none focus:border-primary/50" />
          </div>
          <button onClick={run} disabled={res.loading}
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary/15 px-4 py-2 text-sm font-medium text-primary hover:bg-primary/25 disabled:opacity-50">
            {res.loading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} 计算
          </button>
        </div>
        {inputErr && <p className="mt-2 text-xs text-destructive">{inputErr}</p>}
      </Panel>

      {err ? (
        <Panel><p className="py-8 text-center text-sm text-muted-foreground/60">相关性暂不可用：{String((err as Error).message || err)}</p></Panel>
      ) : res.loading && !res.data ? (
        <Panel><p className="py-8 text-center text-sm text-muted-foreground/60">计算中…</p></Panel>
      ) : (
        <>
          {overlayB?.block && (
            <Panel>
              {overlayB.block.title && <h3 className="mb-2 text-sm font-semibold">{overlayB.block.title}</h3>}
              <ChartLegend items={chartSeriesNames(overlayB.option ?? undefined)} />
              <EChart option={overlayB.option} height={340} />
            </Panel>
          )}
          <div className="grid gap-3 lg:grid-cols-2">
            {rollingB?.block && (
              <Panel>
                {rollingB.block.title && <h3 className="mb-2 text-sm font-semibold">{rollingB.block.title}</h3>}
                <ChartLegend items={chartSeriesNames(rollingB.option ?? undefined)} />
                <EChart option={rollingB.option} height={300} />
              </Panel>
            )}
            {matrix && <MatrixPanel block={matrix} />}
          </div>
        </>
      )}

      <Disclaimer />
    </div>
  );
}
