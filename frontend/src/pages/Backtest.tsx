import { useEffect, useState } from "react";
import { Play, RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { Caliber } from "@/components/ui/Caliber";
import { EquityChart, equityLegend } from "@/components/charts/EquityChart";
import { PriceChart } from "@/components/charts/PriceChart";
import { EChart } from "@/components/ui/EChart";
import { usePalette } from "@/theme/usePalette";
import { rendererOf } from "@/lib/research";
import { api } from "@/lib/api";
import { pctColor } from "@/lib/colors";
import { cn } from "@/lib/utils";
import { useCachedResource } from "@/lib/cache";
import { renderPage, type RenderResult, type MetricItem } from "@/lib/research";
import { useAiPage } from "@/lib/ai-page";

// 回测（量化）—— 双均线金叉策略净值 vs 买入持有 + 回撤曲线 + 指标卡。
// 后端 backtest.* 白名单分析函数（alpha/backtest_page.py），页面 spec slug=backtest。
// 净值扣 A 股费用、无未来函数（信号次日成交、涨跌停按前收）；数据源不可用时空图 + 提示。
// 缓存：切页不重取；改参数点「回测」才重拉（cacheKey 带参数）。AI 占位(S5)。

const toneCls = (t?: MetricItem["tone"]) =>
  t === "up" ? pctColor(1) : t === "down" ? pctColor(-1) : "text-foreground";

// 可选策略（与后端 alpha/backtest_page.py 的 STRATEGIES 对应）。
// 现只有双均线金叉一个；将来后端登记新策略（含 vnpy 适配器）后在此加选项即可。
const STRATEGY_OPTIONS = [{ value: "dual_ma", label: "双均线金叉" }];

export function Backtest() {
  const [symbol, setSymbol] = useState("600519");
  const [fast, setFast] = useState("20");
  const [slow, setSlow] = useState("60");
  const [range, setRange] = useState("1y");
  const [strategy, setStrategy] = useState("dual_ma");
  const [inputErr, setInputErr] = useState("");
  const [params, setParams] = useState({ symbol: "600519", fast: 20, slow: 60, range: "1y", strategy: "dual_ma" });

  // 当前输入代码对应的名称，仅为展示更直观。api.quote 拿不到时静默降级（不显示）。
  const [symbolName, setSymbolName] = useState("");
  useEffect(() => {
    const code = symbol.trim();
    if (!(code.length === 6 && /^\d+$/.test(code))) { setSymbolName(""); return; }
    let alive = true;
    api.quote(code)
      .then((qs) => { if (alive) setSymbolName(qs[code]?.name || ""); })
      .catch(() => { /* 名称拉取失败静默降级，不阻塞主流程 */ });
    return () => { alive = false; };
  }, [symbol]);

  const key = `bt:${params.symbol}:${params.fast}:${params.slow}:${params.range}:${params.strategy}`;
  const res = useCachedResource<RenderResult>(key, () => renderPage("backtest", params));

  // 向全局 AI 浮标登记本页确定性数据快照，作对话上下文。
  useAiPage({
    key,
    title: "回测",
    context:
      `标的：${params.symbol}${symbolName ? `(${symbolName})` : ""}\n` +
      `策略：${params.strategy}（快线 ${params.fast} / 慢线 ${params.slow}）；区间：${params.range}\n` +
      `口径：净值扣 A 股费用、无未来函数（信号次日成交、涨跌停按前收）`,
    suggestions: ["这个回测结果怎么解读", "净值和回撤说明什么", "双均线策略的局限在哪"],
  });

  const run = () => {
    const code = symbol.trim();
    if (!(code.length === 6 && /^\d+$/.test(code))) { setInputErr("标的须为 6 位数字 A 股代码"); return; }
    const f = parseInt(fast, 10);
    const s = parseInt(slow, 10);
    if (!(f >= 2 && f <= 120)) { setInputErr("快线须在 2~120"); return; }
    if (!(s >= 3 && s <= 250)) { setInputErr("慢线须在 3~250"); return; }
    if (f >= s) { setInputErr("快线须小于慢线"); return; }
    setInputErr("");
    setParams({ symbol: code, fast: f, slow: s, range, strategy });
  };

  const blocks = res.data?.blocks ?? [];
  const metric = blocks.find((b) => b.kind === "metric");
  const charts = blocks.filter((b) => b.kind === "chart");
  // 除「净值+回撤」那一块之外，页面上还有 tearsheet（滚动 Sharpe / 月度热力图）
  // 与归因块。这些必须渲染出来 —— 只画净值等于把后端算好的东西丢掉了
  // （实测：加了 block 但页面只看 equity，其余全被静默忽略）。
  const metrics = blocks.filter((b) => b.kind === "metric");
  // 净值与回撤在同一个实例的两个 pane（ADR-0014 §6）。优先取声明 lwc 的那块，
  // 老后端（无 renderer）时回退到第一块 chart —— 但那时没有 lwc 载荷，会提示无数据。
  // 后端有两个 lwc chart 块（净值 + 回撤）。回撤已在净值块的 payload.drawdown 里，
  // 所以只画「有 series 的那个」（净值块），避免同一段回撤画两遍。
  const equity = charts.find((b) => (b.lwc?.series?.length ?? 0) > 0);
  const otherCharts = charts.filter((b) => b !== equity);
  const otherMetrics = metrics.filter((b) => b !== metric);
  const legend = equityLegend(equity?.lwc ?? null, usePalette());
  const err = res.error;

  return (
    <div className="space-y-5">
      <PageHeader
        title="回测"
        subtitle="双均线金叉策略净值 vs 买入持有 · 确定性计算，扣 A 股费用、无未来函数"
      />

      <Panel>
        <div className="mb-2 flex items-center gap-2">
          <label className="text-xs text-muted-foreground">策略参数</label>
          <Caliber text={"双均线金叉：快线上穿慢线买入、下穿卖出。净值扣佣金/印花/过户；信号次日成交、涨跌停按前收，无未来函数。"} />
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">策略</label>
            <select value={strategy} onChange={(e) => setStrategy(e.target.value)}
              className="rounded-lg border border-border bg-card px-3 py-2 text-sm">
              {STRATEGY_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">标的</label>
            <input value={symbol} onChange={(e) => setSymbol(e.target.value.replace(/[^\d]/g, ""))} maxLength={6}
              className="w-28 rounded-lg border border-border bg-black/20 px-3 py-2 text-sm outline-none focus:border-primary/50" />
            {symbolName && <p className="mt-1 text-xs text-muted-foreground/70">{symbolName}</p>}
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">快线</label>
            <input value={fast} onChange={(e) => setFast(e.target.value.replace(/[^\d]/g, ""))}
              className="w-20 rounded-lg border border-border bg-black/20 px-3 py-2 text-sm outline-none focus:border-primary/50" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">慢线</label>
            <input value={slow} onChange={(e) => setSlow(e.target.value.replace(/[^\d]/g, ""))}
              className="w-20 rounded-lg border border-border bg-black/20 px-3 py-2 text-sm outline-none focus:border-primary/50" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">区间</label>
            <select value={range} onChange={(e) => setRange(e.target.value)}
              className="rounded-lg border border-border bg-card px-3 py-2 text-sm">
              {[["3m", "近 3 月"], ["6m", "近 6 月"], ["1y", "近 1 年"]].map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </div>
          <button onClick={run} disabled={res.loading}
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary/15 px-4 py-2 text-sm font-medium text-primary hover:bg-primary/25 disabled:opacity-50">
            {res.loading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} 回测
          </button>
        </div>
        {inputErr && <p className="mt-2 text-xs text-destructive">{inputErr}</p>}
      </Panel>

      {err ? (
        <Panel><p className="py-8 text-center text-sm text-muted-foreground/60">回测暂不可用：{String((err as Error).message || err)}</p></Panel>
      ) : res.loading && !res.data ? (
        <Panel><p className="py-8 text-center text-sm text-muted-foreground/60">回测中…</p></Panel>
      ) : (
        <>
          {metric?.metric && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
              {metric.metric.items.map((it) => (
                <Panel key={it.label} className="p-3">
                  <p className="truncate text-xs text-muted-foreground">{it.label}</p>
                  <p className={cn("mt-1 font-mono text-lg font-bold", toneCls(it.tone))}>{it.value}</p>
                  {it.hint && <p className="mt-0.5 text-[10px] text-muted-foreground/50">{it.hint}</p>}
                </Panel>
              ))}
            </div>
          )}
          {equity && (
            <Panel>
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-semibold">{equity.title || "净值与回撤"}</h3>
                <span className="text-[11px] text-muted-foreground">上：净值　下：回撤</span>
              </div>
              {/* 图例在图上方的 HTML 里自绘，不交给 ECharts（窄容器下 ECharts
                  的 legend 会侵入绘图区，踩过） */}
              {/* 图例颜色必须与线的颜色同源：直接用 equityLegend 的 color，
                  不用 ChartLegend 内部的 seriesColors 序（那是 ECharts 的序，
                  两边不一致会出现「图例橙、线是蓝」）。 */}
              <div className="mb-1 flex flex-wrap items-center gap-x-4 gap-y-1">
                {legend.map((l) => (
                  <span key={l.name} className="inline-flex items-center gap-1.5">
                    <span className="inline-block h-2 w-2 shrink-0 rounded-[2px]" style={{ background: l.color }} />
                    <span className="text-[11px] text-muted-foreground">{l.name}</span>
                  </span>
                ))}
              </div>
              {equity.lwc && (equity.lwc.series?.length ?? 0) > 0 ? (
                <EquityChart payload={equity.lwc} height={420} />
              ) : (
                <p className="py-16 text-center text-sm text-muted-foreground/60">
                  净值序列暂不可用（后端未返回时间序列载荷）
                </p>
              )}
            </Panel>
          )}
        </>
      )}

          {/* 其余分析块（tearsheet / 归因）。按 renderer 分派：
              lwc → PriceChart（折线），echarts → EChart。
              不做「按 fn 名硬编码」——那会让加一个新图就要改一次页面。 */}
          {otherMetrics.map((m, i) => m.metric && (
            <Panel key={`m-${i}`}>
              {m.title && <h3 className="mb-2 text-[13px] font-semibold">{m.title}</h3>}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {m.metric.items.map((it) => (
                  <div key={it.label} className="rounded-[4px] border border-border px-3 py-2">
                    <p className="truncate text-[11px] text-muted-foreground">{it.label}</p>
                    <p className="mt-1 font-mono text-[15px]" style={{ fontVariantNumeric: "tabular-nums" }}>
                      {String(it.value)}
                    </p>
                    {it.hint && <p className="mt-0.5 text-[10px] text-muted-foreground/50">{it.hint}</p>}
                  </div>
                ))}
              </div>
            </Panel>
          ))}

          {otherCharts.length > 0 && (
            <div className="grid gap-3 lg:grid-cols-2">
              {otherCharts.map((b, i) => (
                <Panel key={`c-${i}`}>
                  {b.title && <h3 className="mb-2 text-[13px] font-semibold">{b.title}</h3>}
                  {rendererOf(b) === "lwc" ? (
                    (b.lwc?.series?.length ?? 0) > 0
                      ? <div className="h-[220px]"><PriceChart bars={lwcToBars(b)} mode="line" /></div>
                      : <p className="py-8 text-center text-[12px] text-muted-foreground/60">无数据</p>
                  ) : (
                    // 剥掉 option 里的 title：Panel 已经用 h3 显示了标题，
                    // ECharts 再画一遍就是同一句话出现两次（实测重复）。
                    <EChart option={stripTitle(b.option)} height={220} />
                  )}
                </Panel>
              ))}
            </div>
          )}

      <Disclaimer />
    </div>
  );
}

/** 把 lwc 载荷的 {time,value} 转成 PriceChart 需要的 bar 形状（line 模式只用 close）。 */
function lwcToBars(b: { lwc?: { series?: { points?: { time: string; value: number }[] }[] } }) {
  const pts = b.lwc?.series?.[0]?.points ?? [];
  return pts.map((p) => ({
    datetime: p.time, open: p.value, close: p.value, high: p.value, low: p.value, vol: 0,
  }));
}

/** 去掉 ECharts option 里的 title（Panel 的 h3 已经显示标题）。 */
function stripTitle(opt: Record<string, unknown> | null | undefined) {
  if (!opt) return null;
  const { title: _t, ...rest } = opt as Record<string, unknown>;
  return rest;
}
