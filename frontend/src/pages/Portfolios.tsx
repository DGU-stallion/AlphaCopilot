import { useCallback, useState } from "react";
import { Plus, Trash2, Loader2, X, CalendarClock } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { Caliber } from "@/components/ui/Caliber";
import { EChart } from "@/components/ui/EChart";
import { useCachedResource, dropCache } from "@/lib/cache";
import {
  listPortfolios, createPortfolio, deletePortfolio, addRebalance, portfolioNav,
  type Portfolio, type NavResult,
} from "@/lib/research";
import { ApiError } from "@/lib/api";

// 模拟组合 —— 雪球式：组合 = 若干调仓事件（生效日 + {code: 权重}），事件之间权重随价格漂移。
// 净值曲线 vs 基准（默认沪深300），后端 compute_nav 确定性算。第一版不计手续费、不做空。
// 缓存：列表切页不重取；改动（建/删/调仓）后 dropCache 重取。AI 占位(S5)。

interface WeightRow { code: string; weight: string }

export function Portfolios() {
  const list = useCachedResource<Portfolio[]>("pf:list", () => listPortfolios());
  const [selected, setSelected] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // 建组合
  const [name, setName] = useState("");
  const [benchmark, setBenchmark] = useState("000300");
  const [createdOn, setCreatedOn] = useState("");
  const [creating, setCreating] = useState(false);

  // 调仓录入
  const [effDate, setEffDate] = useState("");
  const [rows, setRows] = useState<WeightRow[]>([{ code: "", weight: "" }]);
  const [rebalancing, setRebalancing] = useState(false);

  const portfolios = list.data ?? [];
  const active = portfolios.find((p) => p.id === selected) ?? portfolios[0] ?? null;

  const reloadList = useCallback(() => { dropCache("pf:list"); list.refresh(); }, [list]);

  const create = async () => {
    if (!name.trim()) { setErr("组合名不能为空"); return; }
    setCreating(true); setErr(null);
    try {
      const { id } = await createPortfolio(name.trim(), benchmark.trim() || "000300", createdOn);
      setName(""); setCreatedOn("");
      setSelected(id);
      reloadList();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "创建失败");
    } finally { setCreating(false); }
  };

  const remove = async (pid: string) => {
    if (!confirm("删除该组合及其调仓历史？")) return;
    try {
      await deletePortfolio(pid);
      if (selected === pid) setSelected(null);
      dropCache(`pf:nav:${pid}`);
      reloadList();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "删除失败"); }
  };

  const submitRebalance = async () => {
    if (!active) return;
    if (!effDate) { setErr("请选生效日期"); return; }
    const weights: Record<string, number> = {};
    for (const r of rows) {
      const c = r.code.trim();
      if (!c) continue;
      if (!(c.length === 6 && /^\d+$/.test(c))) { setErr(`非法标的 ${c}`); return; }
      const w = parseFloat(r.weight);
      if (!(w >= 0 && w <= 1)) { setErr(`${c} 权重须在 0~1`); return; }
      weights[c] = w;
    }
    if (Object.keys(weights).length === 0) { setErr("至少填一个标的权重"); return; }
    const total = Object.values(weights).reduce((a, b) => a + b, 0);
    if (total > 1 + 1e-9) { setErr(`权重和 ${total.toFixed(3)} > 1（超出部分应为现金）`); return; }
    setRebalancing(true); setErr(null);
    try {
      await addRebalance(active.id, effDate, weights);
      setEffDate(""); setRows([{ code: "", weight: "" }]);
      dropCache(`pf:nav:${active.id}`);
      reloadList();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "调仓失败");
    } finally { setRebalancing(false); }
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="模拟组合"
        subtitle="雪球式调仓事件驱动净值 · 组合净值 vs 沪深300 · 确定性计算"
        actions={<AskAiButton context="模拟组合结构解读" label="问 AI" />}
      />

      <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
        {/* 左：组合列表 + 新建 */}
        <div className="space-y-4">
          <GlassCard>
            <h3 className="mb-3 text-sm font-semibold">新建组合</h3>
            <div className="space-y-2">
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="组合名，如 白酒龙头"
                className="w-full rounded-lg border border-border bg-black/20 px-3 py-2 text-sm outline-none focus:border-primary/50" />
              <input value={benchmark} onChange={(e) => setBenchmark(e.target.value.replace(/[^\d]/g, ""))} maxLength={6} placeholder="基准代码（默认 000300）"
                className="w-full rounded-lg border border-border bg-black/20 px-3 py-2 text-sm outline-none focus:border-primary/50" />
              <input type="date" value={createdOn} onChange={(e) => setCreatedOn(e.target.value)}
                className="w-full rounded-lg border border-border bg-black/20 px-3 py-2 text-sm outline-none focus:border-primary/50" />
              <button onClick={create} disabled={creating}
                className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-primary/15 px-4 py-2 text-sm font-medium text-primary shadow-glow hover:bg-primary/25 disabled:opacity-50">
                {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} 创建
              </button>
            </div>
          </GlassCard>

          <GlassCard>
            <h3 className="mb-2 text-sm font-semibold">我的组合</h3>
            {list.loading && portfolios.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground/60">加载中…</p>
            ) : portfolios.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground/60">还没有组合，用上面表单建一个。</p>
            ) : (
              <div className="space-y-1">
                {portfolios.map((p) => (
                  <div key={p.id}
                    onClick={() => setSelected(p.id)}
                    className={`flex cursor-pointer items-center justify-between rounded-lg px-3 py-2 text-sm ${active?.id === p.id ? "bg-primary/15 text-primary" : "hover:bg-muted/40"}`}>
                    <span className="truncate">{p.name}<span className="ml-1.5 text-[11px] text-muted-foreground/60">{p.rebalances.length} 次调仓</span></span>
                    <button onClick={(e) => { e.stopPropagation(); remove(p.id); }} className="text-muted-foreground/40 hover:text-destructive"><Trash2 className="h-3.5 w-3.5" /></button>
                  </div>
                ))}
              </div>
            )}
          </GlassCard>
        </div>

        {/* 右：净值曲线 + 调仓 */}
        <div className="space-y-4">
          {active ? <PortfolioDetail portfolio={active} /> : (
            <GlassCard><p className="py-16 text-center text-sm text-muted-foreground/60">选择或新建一个组合查看净值曲线。</p></GlassCard>
          )}

          {active && (
            <GlassCard>
              <div className="mb-3 flex items-center gap-2">
                <h3 className="text-sm font-semibold">添加调仓事件</h3>
                <Caliber text={"调仓在生效日按当日收盘价换算虚拟持股数；事件之间持股不变、权重随价格漂移。权重和不足 1 的部分视为现金。"} />
              </div>
              <div className="mb-2">
                <label className="mb-1 block text-xs text-muted-foreground">生效日期</label>
                <input type="date" value={effDate} onChange={(e) => setEffDate(e.target.value)}
                  className="rounded-lg border border-border bg-black/20 px-3 py-2 text-sm outline-none focus:border-primary/50" />
              </div>
              <div className="space-y-2">
                {rows.map((r, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <input value={r.code} onChange={(e) => { const v = e.target.value.replace(/[^\d]/g, ""); setRows(rows.map((x, j) => j === i ? { ...x, code: v } : x)); }}
                      maxLength={6} placeholder="标的 600519"
                      className="w-32 rounded-lg border border-border bg-black/20 px-3 py-2 text-sm outline-none focus:border-primary/50" />
                    <input value={r.weight} onChange={(e) => { const v = e.target.value.replace(/[^\d.]/g, ""); setRows(rows.map((x, j) => j === i ? { ...x, weight: v } : x)); }}
                      placeholder="权重 0~1，如 0.3"
                      className="w-32 rounded-lg border border-border bg-black/20 px-3 py-2 text-sm outline-none focus:border-primary/50" />
                    {rows.length > 1 && <button onClick={() => setRows(rows.filter((_, j) => j !== i))} className="text-muted-foreground/50 hover:text-destructive"><X className="h-4 w-4" /></button>}
                  </div>
                ))}
              </div>
              <div className="mt-3 flex items-center gap-2">
                <button onClick={() => setRows([...rows, { code: "", weight: "" }])} className="inline-flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground"><Plus className="h-3.5 w-3.5" /> 加一行</button>
                <button onClick={submitRebalance} disabled={rebalancing}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-primary/15 px-4 py-1.5 text-sm font-medium text-primary shadow-glow hover:bg-primary/25 disabled:opacity-50">
                  {rebalancing ? <Loader2 className="h-4 w-4 animate-spin" /> : <CalendarClock className="h-4 w-4" />} 提交调仓
                </button>
              </div>
            </GlassCard>
          )}
        </div>
      </div>

      {err && <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{err}</div>}
      <Disclaimer />
    </div>
  );
}

// 单组合详情：净值曲线（自带缓存，按 pid + 调仓次数 key，调仓后变 key 自然重取）+ 调仓事件列表。
function PortfolioDetail({ portfolio }: { portfolio: Portfolio }) {
  const key = `pf:nav:${portfolio.id}:${portfolio.rebalances.length}`;
  const nav = useCachedResource<NavResult>(key, () => portfolioNav(portfolio.id));
  const option = nav.data?.option ?? null;

  return (
    <>
      <GlassCard glow>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold">{portfolio.name} · 净值曲线</h3>
          <span className="rounded-full border border-border px-2 py-0.5 font-mono text-[11px] text-muted-foreground">基准 {portfolio.benchmark}</span>
        </div>
        {nav.loading && !nav.data ? (
          <p className="py-16 text-center text-sm text-muted-foreground/60">净值计算中…</p>
        ) : nav.error ? (
          <p className="py-16 text-center text-sm text-muted-foreground/60">净值暂不可用：{String((nav.error as Error).message || nav.error)}</p>
        ) : (
          <EChart option={option} height={360} />
        )}
      </GlassCard>

      <GlassCard>
        <h3 className="mb-2 text-sm font-semibold">调仓事件</h3>
        {portfolio.rebalances.length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground/60">尚无调仓事件。用下方表单添加一次调仓，净值才会开始计算。</p>
        ) : (
          <div className="space-y-2">
            {portfolio.rebalances.map((rb) => (
              <div key={rb.id} className="rounded-lg border border-border/40 bg-black/10 px-3 py-2 text-sm">
                <p className="font-mono text-xs text-muted-foreground">{rb.effective_on}</p>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {Object.entries(rb.weights).map(([c, w]) => (
                    <span key={c} className="rounded-full bg-primary/10 px-2 py-0.5 font-mono text-[11px] text-primary">{c} {(w * 100).toFixed(0)}%</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </GlassCard>
    </>
  );
}
