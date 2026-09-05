import { useMemo, useState } from "react";
import { Plus, X, RefreshCw, NotebookPen } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { pctColor } from "@/lib/colors";
import { api, type JournalRow } from "@/lib/api";
import { useCachedResource, dropCache } from "@/lib/cache";
import { cn } from "@/lib/utils";

// 交易日志 —— 基于 AlphaCopilot 已有 journal 后端（add/list/delete）新建的务实录入页。
// 参考 vibe-astock Journal.tsx 的信息架构（录入 + 列表 + 基础盈亏），但不搬其 80KB 专有特性。
// 盈亏口径：按「现金流」算 —— 卖出所得 − 买入花费 − 费用。⚠️ 这是现金流口径，
// 不是市值盯市（未卖出的持仓不折现价），标签写死避免误读。

const CACHE_KEY = "journal:list";
const money = (v: number) => v.toLocaleString("zh-CN", { maximumFractionDigits: 2 });

interface Form {
  code: string; name: string; side: "buy" | "sell";
  price: string; shares: string; fee: string; traded_at: string; note: string;
}
const EMPTY_FORM: Form = {
  code: "", name: "", side: "buy", price: "", shares: "", fee: "", traded_at: "", note: "",
};

// 按标的聚合现金流盈亏：卖出收入 − 买入支出 − 全部费用。
function cashflowByCode(rows: JournalRow[]) {
  const acc = new Map<string, { name: string; net: number; buy: number; sell: number }>();
  for (const r of rows) {
    const gross = r.price * r.shares;
    const cur = acc.get(r.code) ?? { name: r.name || r.code, net: 0, buy: 0, sell: 0 };
    if (r.name) cur.name = r.name;
    if (r.side === "sell") { cur.sell += gross; cur.net += gross - r.fee; }
    else { cur.buy += gross; cur.net -= gross + r.fee; }
    acc.set(r.code, cur);
  }
  return acc;
}

export function Journal() {
  const res = useCachedResource<JournalRow[]>(CACHE_KEY, () => api.journal());
  const rows = res.data ?? [];
  const [form, setForm] = useState<Form>(EMPTY_FORM);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = () => { dropCache(CACHE_KEY); res.refresh(); };

  const submit = async () => {
    const price = Number(form.price);
    const shares = Number(form.shares);
    if (!Number.isFinite(price) || price <= 0) { setErr("价格须为正数"); return; }
    if (!Number.isInteger(shares) || shares <= 0) { setErr("股数须为正整数"); return; }
    setErr(null); setBusy(true);
    try {
      await api.addJournal({
        code: form.code.trim(), name: form.name.trim(), side: form.side,
        price, shares, fee: Number(form.fee) || 0,
        traded_at: form.traded_at.trim(), note: form.note.trim(),
      });
      setForm(EMPTY_FORM);
      reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "提交失败");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (jid: string) => {
    await api.removeJournal(jid).catch(() => {});
    reload();
  };

  const byCode = useMemo(() => cashflowByCode(rows), [rows]);
  const totalNet = useMemo(() => [...byCode.values()].reduce((s, v) => s + v.net, 0), [byCode]);

  const set = (k: keyof Form, v: string) => setForm((f) => ({ ...f, [k]: v }));
  const inputCls = "rounded-lg border border-border bg-black/20 px-3 py-2 text-sm outline-none focus:border-primary/50";

  return (
    <div>
      <PageHeader
        title="交易日志"
        subtitle="记录每一笔成交，按标的看现金流盈亏。数据落本地后端 SQLite。"
      />

      {/* 录入 */}
      <GlassCard className="mb-4">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <input className={inputCls} placeholder="代码 600519" value={form.code} onChange={(e) => set("code", e.target.value)} />
          <input className={inputCls} placeholder="名称（可选）" value={form.name} onChange={(e) => set("name", e.target.value)} />
          <select className={inputCls} value={form.side} onChange={(e) => set("side", e.target.value)}>
            <option value="buy">买入</option>
            <option value="sell">卖出</option>
          </select>
          <input className={inputCls} placeholder="成交日 2025-01-02" value={form.traded_at} onChange={(e) => set("traded_at", e.target.value)} />
          <input className={inputCls} type="number" placeholder="价格" value={form.price} onChange={(e) => set("price", e.target.value)} />
          <input className={inputCls} type="number" placeholder="股数" value={form.shares} onChange={(e) => set("shares", e.target.value)} />
          <input className={inputCls} type="number" placeholder="费用（可选）" value={form.fee} onChange={(e) => set("fee", e.target.value)} />
          <input className={inputCls} placeholder="备注（可选）" value={form.note} onChange={(e) => set("note", e.target.value)} />
        </div>
        <div className="mt-2 flex items-center gap-3">
          <button
            onClick={submit}
            disabled={busy}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-primary/15 px-4 text-sm font-medium text-primary shadow-glow hover:bg-primary/25 disabled:opacity-50"
          >
            <Plus className="h-4 w-4" /> 记一笔
          </button>
          {err && <span className="text-xs text-destructive">{err}</span>}
        </div>
      </GlassCard>

      {/* 按标的现金流盈亏 */}
      {byCode.size > 0 && (
        <GlassCard className="mb-4">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-muted-foreground">
              现金流盈亏（卖出所得 − 买入花费 − 费用）
            </h3>
            <span className={cn("font-mono text-sm font-bold", pctColor(totalNet))}>
              合计 {totalNet > 0 ? "+" : ""}{money(totalNet)}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {[...byCode.entries()].map(([code, v]) => (
              <div key={code} className="rounded-lg bg-muted/25 p-3">
                <p className="truncate text-xs text-muted-foreground">{v.name} <span className="font-mono">{code}</span></p>
                <p className={cn("mt-0.5 font-mono text-lg font-bold", pctColor(v.net))}>
                  {v.net > 0 ? "+" : ""}{money(v.net)}
                </p>
                <p className="mt-0.5 text-[10px] text-muted-foreground/60">买 {money(v.buy)} · 卖 {money(v.sell)}</p>
              </div>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-muted-foreground/60">
            现金流口径：未卖出的持仓不按现价折算，只统计已发生的买卖现金流。
          </p>
        </GlassCard>
      )}

      {/* 成交列表 */}
      <GlassCard glow>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="flex items-center gap-1.5 font-semibold">
            <NotebookPen className="h-4 w-4 text-primary" /> 成交记录
            <span className="text-xs font-normal text-muted-foreground">（{rows.length}）</span>
          </h3>
          <button onClick={reload} disabled={res.loading} className="text-muted-foreground hover:text-primary" title="刷新">
            <RefreshCw className={cn("h-3.5 w-3.5", res.loading && "animate-spin")} />
          </button>
        </div>
        {rows.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground/60">还没有成交记录，用上面的表单记一笔。</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/50 text-left text-xs text-muted-foreground">
                  {["成交日", "名称", "代码", "方向", "价格", "股数", "费用", "金额", "备注", ""].map((h) => (
                    <th key={h} className="whitespace-nowrap px-2 py-2 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b border-border/30">
                    <td className="whitespace-nowrap px-2 py-2.5 font-mono text-xs text-muted-foreground">{r.traded_at || "—"}</td>
                    <td className="px-2 py-2.5 font-medium">{r.name || "—"}</td>
                    <td className="px-2 py-2.5 font-mono text-xs text-muted-foreground">{r.code || "—"}</td>
                    <td className={cn("px-2 py-2.5 font-medium", r.side === "buy" ? "text-danger" : "text-success")}>
                      {r.side === "buy" ? "买入" : "卖出"}
                    </td>
                    <td className="px-2 py-2.5 font-mono">{r.price}</td>
                    <td className="px-2 py-2.5 font-mono">{r.shares}</td>
                    <td className="px-2 py-2.5 font-mono text-muted-foreground">{r.fee || 0}</td>
                    <td className="px-2 py-2.5 font-mono text-muted-foreground">{money(r.price * r.shares)}</td>
                    <td className="max-w-40 truncate px-2 py-2.5 text-xs text-muted-foreground">{r.note || "—"}</td>
                    <td className="px-2 py-2.5">
                      <button onClick={() => remove(r.id)} className="text-muted-foreground/50 hover:text-destructive" title="删除">
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>

      <Disclaimer />
    </div>
  );
}
