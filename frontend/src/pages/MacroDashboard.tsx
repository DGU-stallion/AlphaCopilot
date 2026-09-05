import { useEffect, useState } from "react";
import { RefreshCw, Globe, Fuel, Landmark, DollarSign, Bitcoin, TrendingUp } from "lucide-react";
import { pctColor } from "@/lib/colors";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { Caliber } from "@/components/ui/Caliber";
import { Disclaimer } from "@/components/ui/Disclaimer";
import {
  api, type IndexQuote, type OverseasSnapshot, type OverseasRow,
  type MacroSnapshot, type MacroRates,
} from "@/lib/api";
import { cn } from "@/lib/utils";

// A 股惯例：红涨绿跌（pctColor），全站一致，与国际绿涨相反是有意选择。
const pct = (v: number | null | undefined) =>
  v == null ? "—" : `${v > 0 ? "+" : ""}${v}%`;

/** 单只行情卡：名称 + 现价 + 涨跌幅（红涨绿跌）。ticker 作副标。 */
function Quote({ name, price, change_pct, sub }: {
  name: string; price: number | null; change_pct: number | null; sub?: string;
}) {
  return (
    <GlassCard className="p-3">
      <p className="truncate text-xs text-muted-foreground">
        {name}
        {sub && <span className="ml-1 font-mono text-[10px] text-muted-foreground/40">{sub}</span>}
      </p>
      <p className={cn("mt-1 font-mono text-lg font-bold", pctColor(change_pct))}>
        {price == null ? "—" : price}
      </p>
      <p className={cn("text-xs", pctColor(change_pct))}>{pct(change_pct)}</p>
    </GlassCard>
  );
}

/** 一组区块：标题 + 口径说明 + 卡片网格。整组不可用时如实占位。 */
function Section({ icon: Icon, title, caliber, extra, children }: {
  icon: typeof Globe; title: string; caliber?: string;
  extra?: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <section className="mb-6">
      <div className="mb-3 flex flex-wrap items-baseline gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold text-muted-foreground">
          <Icon className="h-4 w-4" /> {title}
        </h3>
        {caliber && <Caliber text={caliber} />}
        {extra}
      </div>
      {children}
    </section>
  );
}

/** 数据源不可用时的占位卡（降级如实展示，不伪造）。 */
function Unavailable({ reason }: { reason?: string }) {
  return (
    <GlassCard className="p-3">
      <p className="text-xs text-muted-foreground/60">
        {reason || "暂不可用：数据源暂时取不到"}
      </p>
    </GlassCard>
  );
}

export function MacroDashboard() {
  // 股市：A 股大盘指数（复用 /api/indices）+ 隔夜外围（复用 /api/market/overseas）
  const [indices, setIndices] = useState<IndexQuote[]>([]);
  const [oversea, setOversea] = useState<OverseasSnapshot | null>(null);
  const [commodities, setCommodities] = useState<MacroSnapshot | null>(null);
  const [forex, setForex] = useState<MacroSnapshot | null>(null);
  const [rates, setRates] = useState<MacroRates | null>(null);
  const [crypto, setCrypto] = useState<MacroSnapshot | null>(null);
  const [loading, setLoading] = useState(false);

  const load = () => {
    setLoading(true);
    Promise.allSettled([
      api.indices().then(setIndices),
      api.overseas().then(setOversea),
      api.macroCommodities().then(setCommodities),
      api.macroForex().then(setForex),
      api.macroRates().then(setRates),
      api.macroCrypto().then(setCrypto),
    ]).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const usRows: OverseasRow[] = oversea?.available ? (oversea.indices ?? []).filter((r) => r.region === "美股") : [];
  const hkRows: OverseasRow[] = oversea?.available ? (oversea.indices ?? []).filter((r) => r.region !== "美股") : [];
  const mag7 = oversea?.available ? (oversea.mag7 ?? []) : [];

  return (
    <div>
      <PageHeader
        title="宏观看板"
        subtitle="股市 / 大宗商品 / 债市 / 汇率 / 加密货币 —— 一屏看全宏观脸色（红涨绿跌）"
        actions={
          <button
            onClick={load}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-primary"
            title="刷新全部"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} /> 刷新
          </button>
        }
      />

      {/* 1. 股市：A 股大盘 + 隔夜外围（美股/港股 + 七姐妹） */}
      <Section
        icon={TrendingUp}
        title="股市指数"
        caliber={"A 股大盘为实时延时行情；美股/港股涨跌幅对比各自前一交易日收盘。"}
        extra={<>
          {oversea?.us_label && <span className="text-[11px] text-warning">{oversea.us_label}</span>}
          {oversea?.hk_label && <span className="text-[11px] text-warning">{oversea.hk_label}</span>}
        </>}
      >
        <div className="mb-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {indices.length === 0
            ? <Unavailable reason="大盘指数暂不可用" />
            : indices.map((i) => <Quote key={i.name} name={i.name} price={i.price} change_pct={i.change_pct} />)}
        </div>
        {usRows.length > 0 && (
          <div className="mb-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
            {usRows.map((r) => <Quote key={r.name} name={r.name} price={r.price} change_pct={r.change_pct} />)}
          </div>
        )}
        {mag7.length > 0 && (
          <>
            <p className="mb-2 text-[11px] text-muted-foreground/60">美股七姐妹 · 权重股带指数走</p>
            <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
              {mag7.map((r) => <Quote key={r.name} name={r.name} price={r.price} change_pct={r.change_pct} sub={r.ticker} />)}
            </div>
          </>
        )}
        {hkRows.length > 0 && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {hkRows.map((r) => <Quote key={r.name} name={r.name} price={r.price} change_pct={r.change_pct} />)}
          </div>
        )}
      </Section>

      {/* 2. 大宗商品 */}
      <Section icon={Fuel} title="大宗商品" caliber={"原油 / 黄金 / 白银等国际报价，涨跌幅对比前一交易日。"}>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {commodities?.available
            ? (commodities.items ?? []).map((r) => <Quote key={r.name} name={r.name} price={r.price} change_pct={r.change_pct} />)
            : <Unavailable reason={commodities?.reason} />}
        </div>
      </Section>

      {/* 3. 债市：美债收益率曲线关键期限 */}
      <Section
        icon={Landmark}
        title="债市 · 美债收益率"
        caliber={"美国财政部每日收益率曲线，单位为收益率百分数（非涨跌）。"}
        extra={rates?.available && rates.date && <span className="text-[11px] text-muted-foreground/50">{rates.date}</span>}
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {rates?.available
            ? (rates.items ?? []).map((r) => (
                <GlassCard key={r.name} className="p-3">
                  <p className="truncate text-xs text-muted-foreground">{r.name}</p>
                  <p className="mt-1 font-mono text-lg font-bold">{r.yield_pct}%</p>
                </GlassCard>
              ))
            : <Unavailable reason={rates?.reason} />}
        </div>
      </Section>

      {/* 4. 汇率 */}
      <Section icon={DollarSign} title="汇率" caliber={"主要货币对现价，涨跌幅对比前一交易日。"}>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {forex?.available
            ? (forex.items ?? []).map((r) => <Quote key={r.name} name={r.name} price={r.price} change_pct={r.change_pct} />)
            : <Unavailable reason={forex?.reason} />}
        </div>
      </Section>

      {/* 5. 加密货币（BTC）：暂无靠谱免费现货源 → 如实占位 */}
      <Section icon={Bitcoin} title="加密货币">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {crypto?.available
            ? (crypto.items ?? []).map((r) => <Quote key={r.name} name={r.name} price={r.price} change_pct={r.change_pct} />)
            : <Unavailable reason={crypto?.reason} />}
        </div>
      </Section>

      <Disclaimer />
    </div>
  );
}
