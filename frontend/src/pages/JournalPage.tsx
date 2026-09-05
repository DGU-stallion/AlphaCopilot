/**
 * JournalPage — 交易日志专用页（S3，状态型 CRUD）。
 * 记录真实成交（买/卖/价/量/费/日期/备注）+ 列表 + 删除。落 SQLite 真源。
 */

import { useCallback, useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { addJournal, type JournalEntry, listJournal, removeJournal } from "@/lib/api";
import { useAiPage } from "@/lib/ai-page-context";

const EMPTY = {
  code: "",
  name: "",
  side: "buy" as "buy" | "sell",
  price: 0,
  shares: 0,
  fee: 0,
  traded_at: "",
  note: "",
};

export function JournalPage() {
  const [rows, setRows] = useState<JournalEntry[]>([]);
  const [form, setForm] = useState({ ...EMPTY });
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    listJournal()
      .then(setRows)
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(refresh, [refresh]);

  useAiPage({
    key: `journal:${rows.length}`,
    title: "交易日志",
    context: { count: rows.length },
    suggestions: ["我的交易胜率如何？", "哪些交易亏损最多？"],
  });

  const onAdd = async () => {
    setError(null);
    try {
      await addJournal(form);
      setForm({ ...EMPTY });
      refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  const set = (k: keyof typeof form, v: string | number) =>
    setForm((f) => ({ ...f, [k]: v }));

  return (
    <div className="flex h-full flex-col gap-3 overflow-auto p-1">
      <div className="glass flex flex-wrap items-end gap-2 rounded-lg p-3">
        <h2 className="w-full text-base font-semibold text-foreground">交易日志</h2>
        <input aria-label="代码" placeholder="代码" value={form.code}
          onChange={(e) => set("code", e.target.value)}
          className="glass w-24 rounded-md px-2 py-1 text-sm text-foreground" />
        <input aria-label="名称" placeholder="名称" value={form.name}
          onChange={(e) => set("name", e.target.value)}
          className="glass w-28 rounded-md px-2 py-1 text-sm text-foreground" />
        <select aria-label="方向" value={form.side}
          onChange={(e) => set("side", e.target.value)}
          className="glass rounded-md px-2 py-1 text-sm text-foreground">
          <option value="buy">买入</option>
          <option value="sell">卖出</option>
        </select>
        <input aria-label="价格" type="number" placeholder="价格" value={form.price || ""}
          onChange={(e) => set("price", Number(e.target.value))}
          className="glass w-24 rounded-md px-2 py-1 text-sm text-foreground" />
        <input aria-label="数量" type="number" placeholder="数量" value={form.shares || ""}
          onChange={(e) => set("shares", Number(e.target.value))}
          className="glass w-24 rounded-md px-2 py-1 text-sm text-foreground" />
        <input aria-label="日期" type="date" value={form.traded_at}
          onChange={(e) => set("traded_at", e.target.value)}
          className="glass rounded-md px-2 py-1 text-sm text-foreground" />
        <button type="button" onClick={onAdd}
          className="glass rounded-md px-4 py-1.5 text-sm text-primary hover:text-accent">
          记录
        </button>
      </div>

      {error && <div className="glass rounded-lg p-3 text-sm text-destructive">{error}</div>}

      <div className="glass overflow-x-auto rounded-lg p-3">
        {rows.length === 0 ? (
          <div className="p-4 text-center text-sm text-muted-foreground">暂无交易记录。</div>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>
                {["日期", "代码", "名称", "方向", "价格", "数量", "费用", "操作"].map((h) => (
                  <th key={h} className="border border-border px-2 py-1 text-left text-muted-foreground">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="border border-border px-2 py-1">{r.traded_at}</td>
                  <td className="border border-border px-2 py-1">{r.code}</td>
                  <td className="border border-border px-2 py-1">{r.name}</td>
                  <td className={`border border-border px-2 py-1 ${r.side === "buy" ? "text-danger" : "text-success"}`}>
                    {r.side === "buy" ? "买入" : "卖出"}
                  </td>
                  <td className="border border-border px-2 py-1">{r.price}</td>
                  <td className="border border-border px-2 py-1">{r.shares}</td>
                  <td className="border border-border px-2 py-1">{r.fee}</td>
                  <td className="border border-border px-2 py-1">
                    <button type="button" aria-label={`删除 ${r.id}`}
                      onClick={() => removeJournal(r.id).then(refresh)}
                      className="text-muted-foreground hover:text-destructive">
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
