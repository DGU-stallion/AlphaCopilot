import { useEffect, useState } from "react";
import { Play, RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { Caliber } from "@/components/ui/Caliber";
import { EChart } from "@/components/ui/EChart";
import { api } from "@/lib/api";
import { pctColor } from "@/lib/colors";
import { cn } from "@/lib/utils";
import { useCachedResource } from "@/lib/cache";
import { renderPage, type RenderResult, type MetricItem } from "@/lib/research";

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
  const [equity, drawdown] = blocks.filter((b) => b.kind === "chart");
  const err = res.error;

  return (
    <div className="space-y-5">
      <PageHeader
        title="回测"
        subtitle="双均线金叉策略净值 vs 买入持有 · 确定性计算，扣 A 股费用、无未来函数"
        actions={<AskAiButton context="回测结果解读" label="问 AI" />}
      />

      <GlassCard>
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
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary/15 px-4 py-2 text-sm font-medium text-primary shadow-glow hover:bg-primary/25 disabled:opacity-50">
            {res.loading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} 回测
          </button>
        </div>
        {inputErr && <p className="mt-2 text-xs text-destructive">{inputErr}</p>}
      </GlassCard>

      {err ? (
        <GlassCard><p className="py-8 text-center text-sm text-muted-foreground/60">回测暂不可用：{String((err as Error).message || err)}</p></GlassCard>
      ) : res.loading && !res.data ? (
        <GlassCard><p className="py-8 text-center text-sm text-muted-foreground/60">回测中…</p></GlassCard>
      ) : (
        <>
          {metric?.metric && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
              {metric.metric.items.map((it) => (
                <GlassCard key={it.label} className="p-3">
                  <p className="truncate text-xs text-muted-foreground">{it.label}</p>
                  <p className={cn("mt-1 font-mono text-lg font-bold", toneCls(it.tone))}>{it.value}</p>
                  {it.hint && <p className="mt-0.5 text-[10px] text-muted-foreground/50">{it.hint}</p>}
                </GlassCard>
              ))}
            </div>
          )}
          {equity && (
            <GlassCard glow>
              {equity.title && <h3 className="mb-2 text-sm font-semibold">{equity.title}</h3>}
              <EChart option={equity.option ?? null} height={360} />
            </GlassCard>
          )}
          {drawdown && (
            <GlassCard>
              {drawdown.title && <h3 className="mb-2 text-sm font-semibold">{drawdown.title}</h3>}
              <EChart option={drawdown.option ?? null} height={280} />
            </GlassCard>
          )}
        </>
      )}

      <Disclaimer />
    </div>
  );
}
