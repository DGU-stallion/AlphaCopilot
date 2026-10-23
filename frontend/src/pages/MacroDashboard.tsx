import { useEffect, useState } from "react";
import { RefreshCw, Globe, Fuel, Landmark, DollarSign, Bitcoin, TrendingUp } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { Caliber } from "@/components/ui/Caliber";
import {
  api, macroApi, type IndexQuote, type OverseasSnapshot, type OverseasRow,
  type MacroSnapshot, type MacroRates, type MacroSeries, type MacroCurve,
} from "@/lib/api";
import { EChart } from "@/components/ui/EChart";
// 这一节的图都是**单系列**（社融柱、PMI 线、曲线、LPR、FR001、两融），
// 单系列不需要图例 —— 加一行「社融增量」的色块只是噪音。
// 多系列的情绪图才需要 ChartLegend/ToneLegend（见 DailyReview）。
import {
  latestPeriod, latestValue, levelSeriesOption, netFlowOption, pmiOption,
  socialFinancingOption, yieldCurveOption,
} from "@/lib/macro-charts";
import { cn } from "@/lib/utils";
import { Num } from "@/components/Num";
import { usePalette } from "@/theme/usePalette";
import { useAiPage } from "@/lib/ai-page";

// A 股惯例：红涨绿跌，全站一致，与国际绿涨相反是有意选择；界面经由 <Num> / palette，字符串快照用 pct()
const pct = (v: number | null | undefined) =>
  v == null ? "—" : `${v > 0 ? "+" : ""}${v}%`;

/** 单只行情卡：名称 + 现价 + 涨跌幅。颜色按涨跌符号走 palette（口径可切：
 *  A 股红涨绿跌 ↔ 国际绿涨红跌），不写死 text-danger —— 硬规则 7 + M2-8 一致性。 */
function Quote({ name, price, change_pct, sub }: {
  name: string; price: number | null; change_pct: number | null; sub?: string;
}) {
  const p = usePalette();
  const tone =
    change_pct == null || change_pct === 0 ? p.textSecondary : change_pct > 0 ? p.up : p.down;
  return (
    <Panel className="p-3">
      <p className="truncate text-xs text-muted-foreground">
        {name}
        {sub && <span className="ml-1 font-mono text-[11px] text-muted-foreground/40">{sub}</span>}
      </p>
      <p className="mt-1 text-lg font-bold" style={{ color: tone }}>
        <Num v={price} digits={2} inheritColor />
      </p>
      <p className="text-xs"><Num v={change_pct} pct /></p>
    </Panel>
  );
}

/** 一组区块：标题 + 口径说明 + 卡片网格。整组不可用时如实占位。 */
function Section({ icon: Icon, title, caliber, extra, children }: {
  icon: typeof Globe; title: string; caliber?: string;
  extra?: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <section className="mb-4">
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
    <Panel className="p-3">
      <p className="text-xs text-muted-foreground/60">
        {reason || "暂不可用：数据源暂时取不到"}
      </p>
    </Panel>
  );
}


/**
 * 一块「图 + 当前读数」的宏观 panel（D4）。
 *
 * 为什么每块都要一句当前读数：图回答「处于历史什么位置」，读数回答
 * 「现在是多少」。只给图要读者自己去找最后一个点；只给数字就是用户
 * 判定为「内容不足」的那个旧版。两者并排才算把话说完。
 *
 * 取不到时**不画空轴**：空轴会被读成「数据是 0」，比明说「暂不可用」更误导。
 */
function MacroPanel({
  icon: Icon, title, caliber, unit, point, value, option, available, reason, extra,
}: {
  icon: typeof Globe; title: string; caliber: string; unit?: string;
  point?: string | null; value: number | null; option: Record<string, unknown> | null;
  available: boolean; reason?: string; extra?: React.ReactNode;
}) {
  return (
    <Panel className="flex h-full min-w-0 flex-col">
      <div className="mb-2 flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <h3 className="flex items-center gap-1.5 text-[12px] font-semibold">
          <Icon className="h-3.5 w-3.5 text-muted-foreground" /> {title}
        </h3>
        {available && value !== null && (
          <span className="font-mono text-[16px] font-semibold" style={{ fontVariantNumeric: "tabular-nums" }}>
            <Num v={value} digits={2} suffix={unit === "%" ? "%" : undefined} />
          </span>
        )}
        {available && point && (
          <span className="font-mono text-[11px] text-muted-foreground">{point}</span>
        )}
        {extra}
      </div>
      <Caliber text={caliber} />
      <div className="mt-2 flex min-h-[168px] flex-1 flex-col justify-center">
        {available && option
          ? <EChart option={option} height={168} />
          : (
            <p className="py-8 text-center text-[11px] text-muted-foreground/60">
              {reason || "暂不可用：数据源取不到"}
            </p>
          )}
      </div>
    </Panel>
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
  // 宏观序列（D4）：能画成时间序列的东西，独立于上面的「快照」。
  // 每个都是 MacroSeries/MacroCurve，自带 available + reason —— 取不到就如实显示。
  const [sf, setSf] = useState<MacroSeries | null>(null);
  const [pmi, setPmi] = useState<MacroSeries | null>(null);
  const [yields, setYields] = useState<MacroCurve | null>(null);
  const [lpr, setLpr] = useState<MacroSeries | null>(null);
  const [repo, setRepo] = useState<MacroSeries | null>(null);
  const [northbound, setNorthbound] = useState<MacroSeries | null>(null);
  const [margin, setMargin] = useState<MacroSeries | null>(null);
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
      macroApi.socialFinancing().then(setSf),
      macroApi.pmi().then(setPmi),
      macroApi.cnYields().then(setYields),
      macroApi.lpr().then(setLpr),
      macroApi.repo().then(setRepo),
      macroApi.northbound().then(setNorthbound),
      macroApi.margin().then(setMargin),
    ]).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const usRows: OverseasRow[] = oversea?.available ? (oversea.indices ?? []).filter((r) => r.region === "美股") : [];
  const hkRows: OverseasRow[] = oversea?.available ? (oversea.indices ?? []).filter((r) => r.region !== "美股") : [];
  const mag7 = oversea?.available ? (oversea.mag7 ?? []) : [];

  // 向全局 AI 浮标登记本页确定性数据快照，作对话上下文（红涨绿跌口径）。
  const idxLine = indices.length
    ? indices.map((i) => `${i.name} ${i.price ?? "—"}(${pct(i.change_pct)})`).join("、")
    : "暂未取到";
  const usLine = usRows.length ? usRows.map((r) => `${r.name} ${pct(r.change_pct)}`).join("、") : "暂未取到";
  useAiPage({
    key: "macro-dashboard",
    title: "宏观看板",
    context:
      `A 股大盘：${idxLine}\n隔夜美股：${usLine}\n` +
      `大宗商品：${commodities?.available ? "已取到" : "暂不可用"}；` +
      `汇率：${forex?.available ? "已取到" : "暂不可用"}；` +
      `债市：${rates ? "已取到" : "暂不可用"}；加密：${crypto?.available ? "已取到" : "暂不可用"}`,
    suggestions: ["隔夜外围对 A 股什么影响", "当前宏观环境怎么看", "大盘指数说明什么"],
  });

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
                <Panel key={r.name} className="p-3">
                  <p className="truncate text-xs text-muted-foreground">{r.name}</p>
                  <p className="mt-1 text-lg font-bold">
                    <Num v={r.yield_pct} suffix="%" />
                  </p>
                </Panel>
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


      {/* 6. 宏观序列（D4）—— 这一节是「内容不足」的正解：
          每块都是**时间序列**，让「现在处于历史什么位置」肉眼可见。 */}
      <Section
        icon={TrendingUp}
        title="宏观 · 政策与价格"
        caliber={"社融为月度增量（亿元）；PMI 以 50 为荣枯线；国债收益率为中债最新交易日曲线。取不到的项如实标注原因，不补零、不插值。"}
      >
        <div className="mb-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
          <MacroPanel
            icon={Landmark}
            title="社会融资规模增量"
            caliber="人民银行月度数据，近 36 个月。柱状按正负分色（净偿还为负）。"
            unit="亿元"
            point={sf?.available ? latestPeriod(sf.points) : null}
            value={latestValue(sf?.points ?? [])}
            option={sf?.available ? socialFinancingOption(sf.points) : null}
            available={!!sf?.available}
            reason={sf?.reason}
          />
          <MacroPanel
            icon={TrendingUp}
            title="制造业 PMI"
            caliber="国家统计局。50 为荣枯分界：线上扩张、线下收缩。"
            unit="%"
            point={pmi?.available ? latestPeriod(pmi.points) : null}
            value={latestValue(pmi?.points ?? [])}
            option={pmi?.available ? pmiOption(pmi.points) : null}
            available={!!pmi?.available}
            reason={pmi?.reason}
            extra={pmi?.available && pmi.reason
              ? <span className="text-[11px] text-warning">{pmi.reason}</span>
              : null}
          />
          <MacroPanel
            icon={Landmark}
            title="国债收益率曲线"
            caliber="中债最新交易日，横轴为期限（不是时间）—— 看的是曲线形状：上斜/平坦/倒挂。"
            unit="%"
            point={yields?.available ? yields.date : null}
            value={yields?.available
              ? (yields.points.find((p) => p.tenor === "10y")?.value ?? null)
              : null}
            option={yields?.available ? yieldCurveOption(yields.points) : null}
            available={!!yields?.available}
            reason={yields?.reason}
            extra={yields?.available
              ? <span className="text-[11px] text-muted-foreground/60">10Y 读数</span>
              : null}
          />
          <MacroPanel
            icon={DollarSign}
            title="LPR 贷款市场报价利率"
            caliber="1 年期 LPR，近 36 个月。"
            unit="%"
            point={lpr?.available ? latestPeriod(lpr.points) : null}
            value={latestValue(lpr?.points ?? [])}
            option={lpr?.available ? levelSeriesOption(lpr.points, { name: "LPR 1Y", unit: "%" }) : null}
            available={!!lpr?.available}
            reason={lpr?.reason}
          />
          <MacroPanel
            icon={DollarSign}
            title="银行间回购定盘利率 FR001"
            caliber="隔夜资金利率，近 60 个交易日。最能反映资金面松紧。"
            unit="%"
            point={repo?.available ? latestPeriod(repo.points) : null}
            value={latestValue(repo?.points ?? [])}
            option={repo?.available ? levelSeriesOption(repo.points, { name: "FR001", unit: "%" }) : null}
            available={!!repo?.available}
            reason={repo?.reason}
          />
          <MacroPanel
            icon={DollarSign}
            title="北向资金净流入"
            caliber="日频净流入（亿元）。正负分色。"
            unit="亿元"
            point={northbound?.available ? latestPeriod(northbound.points) : null}
            value={latestValue(northbound?.points ?? [])}
            option={northbound?.available ? netFlowOption(northbound.points) : null}
            available={!!northbound?.available}
            reason={northbound?.reason}
          />
        </div>
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          <MacroPanel
            icon={Landmark}
            title="两融余额"
            caliber="沪深两市融资融券余额（近 60 个交易日）。"
            unit="亿元"
            point={margin?.available ? latestPeriod(margin.points) : null}
            value={latestValue(margin?.points ?? [])}
            option={margin?.available ? levelSeriesOption(margin.points, { name: "两融余额", unit: "亿元" }) : null}
            available={!!margin?.available}
            reason={margin?.reason}
          />
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

    </div>
  );
}
