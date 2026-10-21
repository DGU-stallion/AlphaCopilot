import { useEffect, useState } from "react";
import { Plus, X, RefreshCw, Star } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { Num } from "@/components/Num";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { api, type Quote, type KlineBar } from "@/lib/api";
import { PriceChart } from "@/components/charts/PriceChart";
import { loadWatch, saveWatch, addCodes } from "@/lib/watchlist";
import { useCachedResource, dropCache } from "@/lib/cache";
import { useAiPage } from "@/lib/ai-page";
import { cn } from "@/lib/utils";

// 股票池（缝合搬运自上游项目的 Watchlist.tsx）。
// 定位改造：标题「自选股」→「股票池」；行情接 useCachedResource
// —— 切页复用不重取，只有点刷新 / 增删标的才重拉。代码本身只存本地 localStorage、不上传。

const pct = (v: number | undefined) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v}%`);  // 字符串语境（AI 快照）专用；界面用 <Num>

const CACHE_KEY = "pool:quotes";

export function Watchlist() {
  const [codes, setCodes] = useState<string[]>(loadWatch);
  const [input, setInput] = useState("");
  const [hint, setHint] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  // 选中标的的 K 线。默认跟股票池第一只走 —— 打开页面就该看到图，
  // 而不是先看到一片空白再去找"点一下"。
  const active = selected && codes.includes(selected) ? selected : codes[0] ?? null;
  const [bars, setBars] = useState<KlineBar[]>([]);
  const [barErr, setBarErr] = useState<string | null>(null);

  useEffect(() => {
    if (!active) { setBars([]); setBarErr(null); return; }
    let alive = true;
    setBarErr(null);
    api.kline(active, 120)
      .then((b) => { if (alive) setBars(b); })
      .catch((e) => {
        // 取不到就说取不到（后端 502 而非空数组）。静默画一条平线比报错更糟。
        if (alive) { setBars([]); setBarErr(e instanceof Error ? e.message : "K 线取不到"); }
      });
    return () => { alive = false; };
  }, [active]);

  // 行情按当前代码集缓存；切页复用，改动代码集时 dropCache 强制重取。
  const quotesRes = useCachedResource<Record<string, Quote>>(
    CACHE_KEY,
    () => (codes.length ? api.quote(codes.join(",")) : Promise.resolve({})),
  );
  const quotes = quotesRes.data ?? {};

  // 向全局 AI 浮标登记本页确定性数据快照，作对话上下文。行情未到时如实标「尚未加载」。
  useAiPage({
    key: `pool:${codes.join(",")}`,
    title: "股票池",
    context:
      codes.length === 0 ? "股票池为空（本地 localStorage，未上传）"
      : `自选股 ${codes.length} 只：\n` +
        codes.map((c) => {
          const q = quotes[c];
          return q
            ? `${c} ${q.name} 现价 ${q.price} 涨跌 ${pct(q.change_pct)} PE(TTM) ${q.pe_ttm ?? "—"} PB ${q.pb ?? "—"} 换手 ${q.turnover_pct ?? "—"}%`
            : `${c} 行情尚未加载`;
        }).join("\n"),
    suggestions: ["帮我看看池子里的估值分布", "哪些标的今天涨幅居前", "池子里有什么明显的风险点"],
  });

  const reloadFor = () => { dropCache(CACHE_KEY); quotesRes.refresh(); };

  const add = () => {
    const { next, added } = addCodes(codes, input);
    if (added === 0) {
      setHint(input.trim() ? "没识别到新的 6 位代码（可能已在股票池里）" : null);
      setInput("");
      return;
    }
    setCodes(next); saveWatch(next); setInput(""); setHint(`已添加 ${added} 只`);
    reloadFor();
  };
  const remove = (c: string) => {
    const next = codes.filter((x) => x !== c);
    setCodes(next); saveWatch(next); reloadFor();
  };

  const loading = quotesRes.loading;

  return (
    <div>
      <PageHeader
        title="股票池"
        subtitle="批量添加、一屏总览你关注的标的。代码只存本地、不上传。"
      />

      <Panel className="mb-4">
        <label className="mb-1.5 block text-xs text-muted-foreground">
          批量添加 —— 粘贴一串代码即可（逗号 / 空格 / 换行都行，自动识别 6 位 A 股代码）
        </label>
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) add();
            }}
            rows={2}
            placeholder={"如：600519 000858, 002463\n300750 688017"}
            className="flex-1 resize-y rounded-lg border border-border bg-black/20 px-3 py-2 text-sm outline-none focus:border-primary/50"
          />
          <button
            onClick={add}
            className="inline-flex h-9 shrink-0 items-center gap-1.5 self-start rounded-lg bg-primary/15 px-4 text-sm font-medium text-primary hover:bg-primary/25"
          >
            <Plus className="h-4 w-4" /> 添加
          </button>
        </div>
        {hint && <p className="mt-2 text-xs text-muted-foreground/70">{hint}</p>}
      </Panel>

      <Panel>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="flex items-center gap-1.5 font-semibold">
            <Star className="h-4 w-4 text-primary" /> 股票池总览
            <span className="text-xs font-normal text-muted-foreground">（{codes.length}）</span>
          </h3>
          <button
            onClick={reloadFor}
            disabled={loading}
            className="text-muted-foreground hover:text-primary"
            title="刷新价格"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
          </button>
        </div>
        {codes.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground/60">
            股票池还是空的，用上面的框粘贴一串代码批量添加。
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/50 text-left text-xs text-muted-foreground">
                  {["名称", "代码", "现价", "涨跌%", "PE(TTM)", "PB", "换手%", ""].map((h) => (
                    <th key={h} className="whitespace-nowrap px-2 py-2 font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {codes.map((c) => {
                  const q = quotes[c];
                  return (
                    <tr
                      key={c}
                      onClick={() => setSelected(c)}
                      title="点击查看 K 线"
                      className={cn(
                        "cursor-pointer border-b border-border/30 transition-colors hover:bg-[hsl(var(--muted))]",
                        c === active && "bg-[hsl(var(--muted))]",
                      )}
                    >
                      <td className="px-2 py-2.5 font-medium">{q?.name || "—"}</td>
                      <td className="px-2 py-2.5 font-mono text-xs text-muted-foreground">{c}</td>
                      <td className="px-2 py-2.5">
                        {q ? <Num v={q.price} digits={2} className={q.change_pct > 0 ? "text-danger" : q.change_pct < 0 ? "text-success" : "text-muted-foreground"} inheritColor />
                          : <span className="text-muted-foreground">—</span>}
                      </td>
                      <td className="px-2 py-2.5"><Num v={q?.change_pct ?? null} pct /></td>
                      <td className="px-2 py-2.5 text-muted-foreground"><Num v={q?.pe_ttm ?? null} digits={2} inheritColor /></td>
                      <td className="px-2 py-2.5 text-muted-foreground"><Num v={q?.pb ?? null} digits={2} inheritColor /></td>
                      <td className="px-2 py-2.5 text-muted-foreground"><Num v={q?.turnover_pct ?? null} digits={2} suffix="%" inheritColor /></td>
                      <td className="px-2 py-2.5">
                        <button
                          onClick={() => remove(c)}
                          className="text-muted-foreground/50 hover:text-destructive"
                          title="移除"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {/* K 线：与成交量同一个 chart 实例的两个 pane（ADR-0014 §6）。
          高度用 flex 撑满剩余空间，页面不再有"空白浪费"。 */}
      <Panel className="mt-4">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="flex items-center gap-1.5 font-semibold">
            <span className="text-primary">▤</span> {active ? `${quotes[active]?.name || active} · 日线` : "K 线"}
            {active && <span className="font-mono text-xs font-normal text-muted-foreground">{active}</span>}
          </h3>
          <span className="text-[11px] text-muted-foreground">前复权 · 近 120 个交易日</span>
        </div>
        {!active ? (
          <p className="py-16 text-center text-sm text-muted-foreground/60">
            股票池为空，添加标的后这里会显示 K 线。
          </p>
        ) : barErr ? (
          <p className="py-16 text-center text-sm text-danger">K 线取不到：{barErr}</p>
        ) : bars.length === 0 ? (
          <p className="py-16 text-center text-sm text-muted-foreground/60">加载中…</p>
        ) : (
          // 固定高度而不是 flex-1：外层页面是普通文档流（高度由内容决定），
          // flex-1 在"高度 auto"的父级里解析为 0，图表会整个消失。
          <div className="h-[360px]">
            <PriceChart bars={bars} />
          </div>
        )}
      </Panel>

      <Disclaimer />
    </div>
  );
}
