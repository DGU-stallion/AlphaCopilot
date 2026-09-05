import { useEffect, useState } from "react";
import { Play, RefreshCw, X, Plus } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { Caliber } from "@/components/ui/Caliber";
import { EChart } from "@/components/ui/EChart";
import { api } from "@/lib/api";
import { useCachedResource } from "@/lib/cache";
import { renderPage, type RenderResult } from "@/lib/research";

// 相关性分析 —— 多标的对比。后端 correlation.* 白名单函数：
//   overlay 归一化叠加走势（起点=100，看相对强弱）
//   matrix  日收益率皮尔逊相关矩阵热图（基于收益率而非价格，避免伪相关）
//   rolling 前两标的滚动窗口相关（看相关性随时间变化）
// 缓存：切页不重取；改标的/窗口点「计算」才重拉（cacheKey 带参数）。AI 占位(S5)。

const MAX = 8;

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

  return (
    <div className="space-y-5">
      <PageHeader
        title="相关性分析"
        subtitle="多标的归一化叠加走势 + 日收益率相关矩阵 · 确定性计算"
        actions={<AskAiButton context="相关性结果解读" label="问 AI" />}
      />

      <GlassCard>
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
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary/15 px-4 py-2 text-sm font-medium text-primary shadow-glow hover:bg-primary/25 disabled:opacity-50">
            {res.loading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} 计算
          </button>
        </div>
        {inputErr && <p className="mt-2 text-xs text-destructive">{inputErr}</p>}
      </GlassCard>

      {err ? (
        <GlassCard><p className="py-8 text-center text-sm text-muted-foreground/60">相关性暂不可用：{String((err as Error).message || err)}</p></GlassCard>
      ) : res.loading && !res.data ? (
        <GlassCard><p className="py-8 text-center text-sm text-muted-foreground/60">计算中…</p></GlassCard>
      ) : (
        <>
          {overlay && (
            <GlassCard glow>
              {overlay.title && <h3 className="mb-2 text-sm font-semibold">{overlay.title}</h3>}
              <EChart option={overlay.option ?? null} height={360} />
            </GlassCard>
          )}
          <div className="grid gap-3 lg:grid-cols-2">
            {matrix && (
              <GlassCard>
                {matrix.title && <h3 className="mb-2 text-sm font-semibold">{matrix.title}</h3>}
                <EChart option={matrix.option ?? null} height={360} />
              </GlassCard>
            )}
            {rolling && (
              <GlassCard>
                {rolling.title && <h3 className="mb-2 text-sm font-semibold">{rolling.title}</h3>}
                <EChart option={rolling.option ?? null} height={360} />
              </GlassCard>
            )}
          </div>
        </>
      )}

      <Disclaimer />
    </div>
  );
}
