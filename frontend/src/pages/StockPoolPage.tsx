/**
 * StockPoolPage — 股票池（研究池）专用页（S3，状态型 CRUD，不走 page spec）。
 * 列表 + 加入（代码/名称/标签）+ 移除。选中标的可跳相关性/回测/组合（S4 就绪后接）。
 * 向 Agent 占位接口登记当前股票池快照（useAiPage）。
 */

import { useCallback, useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { addPool, listPool, type PoolItem, removePool } from "@/lib/api";
import { useAiPage } from "@/lib/ai-page-context";

export function StockPoolPage() {
  const [items, setItems] = useState<PoolItem[]>([]);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [tags, setTags] = useState("");
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const refresh = useCallback(() => {
    listPool()
      .then(setItems)
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(refresh, [refresh]);

  useAiPage({
    key: `stock-pool:${items.map((i) => i.code).join(",")}`,
    title: "股票池",
    context: { count: items.length, codes: items.map((i) => i.code) },
    suggestions: ["这些标的的相关性如何？", "股票池里哪些属于同一板块？"],
  });

  const onAdd = async () => {
    setError(null);
    try {
      await addPool({ code: code.trim(), name: name.trim(), tags: tags.trim() });
      setCode("");
      setName("");
      setTags("");
      refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  const onRemove = async (c: string) => {
    await removePool(c);
    refresh();
  };

  return (
    <div className="flex h-full flex-col gap-3 overflow-auto p-1">
      <div className="glass flex flex-wrap items-end gap-3 rounded-lg p-3">
        <h2 className="w-full text-base font-semibold text-foreground">股票池</h2>
        <input
          aria-label="代码"
          placeholder="6 位代码"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          className="glass w-28 rounded-md px-2 py-1 text-sm text-foreground"
        />
        <input
          aria-label="名称"
          placeholder="名称"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="glass w-32 rounded-md px-2 py-1 text-sm text-foreground"
        />
        <input
          aria-label="标签"
          placeholder="标签"
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          className="glass w-32 rounded-md px-2 py-1 text-sm text-foreground"
        />
        <button
          type="button"
          onClick={onAdd}
          className="glass rounded-md px-4 py-1.5 text-sm text-primary hover:text-accent"
        >
          加入
        </button>
      </div>

      {error && <div className="glass rounded-lg p-3 text-sm text-destructive">{error}</div>}

      <div className="glass overflow-x-auto rounded-lg p-3">
        {items.length === 0 ? (
          <div className="p-4 text-center text-sm text-muted-foreground">股票池为空，先加入标的。</div>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>
                {["代码", "名称", "标签", "操作"].map((h) => (
                  <th key={h} className="border border-border px-2 py-1 text-left text-muted-foreground">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <tr key={it.id}>
                  <td className="border border-border px-2 py-1">
                    <button
                      type="button"
                      className="text-primary hover:text-accent"
                      onClick={() => navigate(`/pages/correlation`)}
                      title="到相关性分析"
                    >
                      {it.code}
                    </button>
                  </td>
                  <td className="border border-border px-2 py-1">{it.name}</td>
                  <td className="border border-border px-2 py-1">{it.tags}</td>
                  <td className="border border-border px-2 py-1">
                    <button
                      type="button"
                      aria-label={`移除 ${it.code}`}
                      onClick={() => onRemove(it.code)}
                      className="text-muted-foreground hover:text-destructive"
                    >
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
