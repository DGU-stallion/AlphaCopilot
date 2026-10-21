import { useMemo, useState } from "react";
import { Plus, X, RefreshCw, NotebookPen } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { Num } from "@/components/Num";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { api, type JournalRow } from "@/lib/api";
import { useCachedResource, dropCache } from "@/lib/cache";
import { useAiPage } from "@/lib/ai-page";
import { cn } from "@/lib/utils";
import { SIZE, ROW } from "@/theme/tokens";

// 交易日志 —— 基于 AlphaCopilot 已有 journal 后端（add/list/delete）新建的务实录入页。
// 参考上游项目 Journal.tsx 的信息架构（录入 + 列表 + 基础盈亏），但不搬其 80KB 专有特性。
// 盈亏口径：按「现金流」算 —— 卖出所得 − 买入花费 − 费用。⚠️ 这是现金流口径，
// 不是市值盯市（未卖出的持仓不折现价），标签写死避免误读。

const CACHE_KEY = "journal:list";

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

  // 向全局 AI 浮标登记本页确定性数据快照，作对话上下文。
  // 盈亏口径：现金流（卖出所得 − 买入花费 − 费用），不是市值盯市。未加载时如实说。
  const aiContext = (() => {
    if (res.loading && rows.length === 0) return "交易日志加载中…";
    if (rows.length === 0) return "尚无成交记录";
    const lines =
      `共 ${rows.length} 笔成交；现金流盈亏合计 ${totalNet > 0 ? "+" : ""}${Number(totalNet).toLocaleString("zh-CN", { maximumFractionDigits: 2 })}（口径：卖出所得 − 买入花费 − 费用，未卖持仓不折现）\n` +
      (byCode.size > 0
        ? `按标的盈亏：${[...byCode.entries()].map(([code, v]) => `${code} ${v.net > 0 ? "+" : ""}${v.net.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`).join("、")}\n`
        : "");
    const recent = rows.slice(0, 5).map((r) =>
      `${r.traded_at || "未填日期"} ${r.side === "buy" ? "买入" : "卖出"} ${r.code}${r.name ? ` ${r.name}` : ""} @${r.price} × ${r.shares}`);
    return lines + `最近几笔：\n` + recent.join("\n");
  })();
  useAiPage({
    key: `journal:${rows.length}:${rows[0]?.id ?? ""}`,
    title: "交易日志",
    context: aiContext,
    suggestions: ["帮我看看目前各标的的盈亏情况", "我的交易有什么明显问题", "现金流盈亏口径是什么意思"],
  });

  const set = (k: keyof Form, v: string) => setForm((f) => ({ ...f, [k]: v }));
  // 统一控件样式（ADR-0014 §5）：高 28 / 圆角 4 / 实色底，与 antd controlHeight 对齐。
  // 原来这里用 rounded-lg + bg-black/20，和股票池/研报页的输入框长得不一样。
  const inputCls = "h-7 rounded-[4px] border border-border bg-[hsl(var(--card))] px-2.5 text-[13px] outline-none placeholder:text-muted-foreground/60 focus:border-[hsl(var(--primary))]";

  return (
    <div>
      <PageHeader
        title="交易日志"
        subtitle="记录每一笔成交，按标的看现金流盈亏。数据落本地后端 SQLite。"
      />

      {/* 录入 */}
      <Panel className="mb-4">
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
            className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-primary/15 px-4 text-sm font-medium text-primary hover:bg-primary/25 disabled:opacity-50"
          >
            <Plus className="h-4 w-4" /> 记一笔
          </button>
          {err && <span className="text-xs text-destructive">{err}</span>}
        </div>
      </Panel>

      {/* 按标的现金流盈亏 */}
      {byCode.size > 0 && (
        <Panel className="mb-4">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-muted-foreground">
              现金流盈亏（卖出所得 − 买入花费 − 费用）
            </h3>
            <span className="text-sm font-bold text-muted-foreground">
              合计 <Num v={totalNet} signed colorBySign />
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {[...byCode.entries()].map(([code, v]) => (
              <div key={code} className="rounded-lg bg-muted/25 p-3">
                <p className="truncate text-xs text-muted-foreground">{v.name} <span className="font-mono">{code}</span></p>
                <p className="mt-0.5 text-lg font-bold">
                  <Num v={v.net} signed colorBySign />
                </p>
                <p className="mt-0.5 text-[10px] text-muted-foreground/60">买 <Num v={v.buy} digits={2} inheritColor /> · 卖 <Num v={v.sell} digits={2} inheritColor /></p>
              </div>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-muted-foreground/60">
            现金流口径：未卖出的持仓不按现价折算，只统计已发生的买卖现金流。
          </p>
        </Panel>
      )}

      {/* 成交列表 */}
      <Panel>
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
                <tr className="border-b border-border/50 text-left text-muted-foreground" style={{ fontSize: SIZE.xs }}>
                  {["成交日", "名称", "代码", "方向", "价格", "股数", "费用", "金额", "备注", ""].map((h) => (
                    <th key={h} className="whitespace-nowrap px-2 py-1.5 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b border-border/30" style={{ height: ROW.compact }}>
                    <td className="whitespace-nowrap px-2 py-1 font-mono text-xs text-muted-foreground">{r.traded_at || "—"}</td>
                    <td className="px-2 py-1 font-medium">{r.name || "—"}</td>
                    <td className="whitespace-nowrap px-2 py-1 font-mono text-xs text-muted-foreground">{r.code || "—"}</td>
                    <td className={cn("px-2 py-1 font-medium", r.side === "buy" ? "text-danger" : "text-success")}>
                      {r.side === "buy" ? "买入" : "卖出"}
                    </td>
                    <td className="px-2 py-1"><Num v={r.price} digits={2} /></td>
                    <td className="px-2 py-1"><Num v={r.shares} digits={0} /></td>
                    <td className="px-2 py-1 text-muted-foreground"><Num v={r.fee} digits={2} inheritColor /></td>
                    <td className="whitespace-nowrap px-2 py-1 font-mono text-muted-foreground"><Num v={r.price * r.shares} digits={2} inheritColor /></td>
                    <td className="max-w-40 truncate px-2 py-1 text-xs text-muted-foreground">{r.note || "—"}</td>
                    <td className="px-2 py-1">
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
      </Panel>

      <Disclaimer />
    </div>
  );
}
