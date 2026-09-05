/**
 * PortfoliosPage — 模拟组合专用页（S4，雪球式调仓事件）。
 * 创建组合 + 记录调仓事件（生效日期 + 权重）+ 查看净值 vs 基准。不涉及真实下单。
 * 显式声明假设：第一版不计手续费；权重不足 100% 视为现金。
 */

import { useCallback, useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { ChartBlock } from "@/components/blocks/ChartBlock";
import {
  addRebalance,
  createPortfolio,
  deletePortfolio,
  listPortfolios,
  type Portfolio,
  portfolioNav,
} from "@/lib/api";
import { useAiPage } from "@/lib/ai-page-context";

export function PortfoliosPage() {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [name, setName] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [navOption, setNavOption] = useState<Record<string, unknown> | null>(null);
  const [effectiveOn, setEffectiveOn] = useState("");
  const [weightsText, setWeightsText] = useState("");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    listPortfolios()
      .then(setPortfolios)
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(refresh, [refresh]);

  useAiPage({
    key: `portfolios:${selected ?? "none"}`,
    title: "模拟组合",
    context: { count: portfolios.length, selected },
    suggestions: ["这个组合的相关性风险如何？", "组合相对基准的超额收益怎样？"],
  });

  const onCreate = async () => {
    setError(null);
    try {
      await createPortfolio({ name: name.trim() });
      setName("");
      refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  const onViewNav = async (id: string) => {
    setSelected(id);
    setNavOption(null);
    try {
      setNavOption(await portfolioNav(id));
    } catch (e) {
      setError(String(e));
    }
  };

  const onAddRebalance = async () => {
    if (!selected) return;
    setError(null);
    try {
      // 权重文本："600519:0.6,000858:0.4"
      const weights: Record<string, number> = {};
      for (const part of weightsText.split(",")) {
        const [code, w] = part.split(":").map((s) => s.trim());
        if (code && w) weights[code] = Number(w);
      }
      await addRebalance(selected, { effective_on: effectiveOn, weights });
      setWeightsText("");
      setEffectiveOn("");
      refresh();
      onViewNav(selected);
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div className="flex h-full flex-col gap-3 overflow-auto p-1">
      <div className="glass flex flex-wrap items-end gap-3 rounded-lg p-3">
        <h2 className="w-full text-base font-semibold text-foreground">模拟组合</h2>
        <input
          aria-label="组合名"
          placeholder="新组合名称"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="glass w-40 rounded-md px-2 py-1 text-sm text-foreground"
        />
        <button type="button" onClick={onCreate}
          className="glass rounded-md px-4 py-1.5 text-sm text-primary hover:text-accent">
          创建组合
        </button>
        <span className="text-xs text-muted-foreground">
          假设：不计手续费；权重不足 100% 视为现金；基准默认沪深300。
        </span>
      </div>

      {error && <div className="glass rounded-lg p-3 text-sm text-destructive">{error}</div>}

      <div className="grid grid-cols-12 gap-3">
        <div className="glass col-span-4 rounded-lg p-3">
          <div className="mb-2 text-sm font-medium text-foreground">组合列表</div>
          {portfolios.length === 0 ? (
            <div className="p-2 text-sm text-muted-foreground">暂无组合。</div>
          ) : (
            <ul className="flex flex-col gap-1">
              {portfolios.map((pf) => (
                <li key={pf.id} className="flex items-center justify-between rounded-md bg-muted/20 px-2 py-1">
                  <button type="button" onClick={() => onViewNav(pf.id)}
                    className={`text-sm ${selected === pf.id ? "text-primary" : "text-foreground"}`}>
                    {pf.name}（{pf.rebalances.length} 次调仓）
                  </button>
                  <button type="button" aria-label={`删除 ${pf.name}`}
                    onClick={() => deletePortfolio(pf.id).then(refresh)}
                    className="text-muted-foreground hover:text-destructive">
                    <Trash2 size={14} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="col-span-8 flex flex-col gap-3">
          {selected && (
            <div className="glass flex flex-wrap items-end gap-2 rounded-lg p-3">
              <div className="w-full text-sm font-medium text-foreground">新增调仓事件</div>
              <input aria-label="生效日期" type="date" value={effectiveOn}
                onChange={(e) => setEffectiveOn(e.target.value)}
                className="glass rounded-md px-2 py-1 text-sm text-foreground" />
              <input aria-label="权重" placeholder="600519:0.6,000858:0.4" value={weightsText}
                onChange={(e) => setWeightsText(e.target.value)}
                className="glass flex-1 rounded-md px-2 py-1 text-sm text-foreground" />
              <button type="button" onClick={onAddRebalance}
                className="glass rounded-md px-4 py-1.5 text-sm text-primary hover:text-accent">
                记录调仓
              </button>
            </div>
          )}
          {navOption && <ChartBlock option={navOption} />}
        </div>
      </div>
    </div>
  );
}
