import { useState, useEffect, Fragment } from "react";
import { Num } from "@/components/Num";
import { RefreshCw, Gauge, ArrowDownUp, TrendingUp, Flame, BarChart3 } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { Caliber } from "@/components/ui/Caliber";
import { finite } from "@/lib/coerce";
import { api, type Quote, type MarketOverview, type ShortTermEmotion, type TurnoverTop, type MarketSession, type LiveEmotion, type EmotionHistoryRow } from "@/lib/api";
import { ztDtZbOption, maxBoardsOption, sealBreakOption, ladderOption } from "@/lib/emotion-charts";
import { sectorFlowOption } from "@/lib/market-charts";
import { EChart } from "@/components/ui/EChart";
import { ToneLegend, ChartLegend } from "@/components/ui/ChartLegend";
import { cn } from "@/lib/utils";
import { getCache, setCache, hasCache } from "@/lib/cache";
import { LimitUpStats } from "./LimitUpStats";
import { useAiPage } from "@/lib/ai-page";
import { useDataAsOfAuto } from "@/lib/data-asof";

// A股红涨绿跌。全球市场（美股/港股指数）**也沿用红涨**——与整个看板及东财等中国平台一致，
// A 股惯例：红涨绿跌。与国际绿涨惯例相反，是有意选择，全站必须一致，勿改。

const AUTO_KEY = "alphacopilot-auto-refresh";
const LIVE_MS = 5_000;      // 轻量行情：腾讯批量，5 秒
const HEAVY_MS = 60_000;    // 板块资金 / 成交额榜：东财+akshare，60 秒

const yiV = (v: number | null | undefined) => (v == null ? null : v / 1e8); // 元 → 亿（供 <Num>）

export function DailyReview() {
  const [overview, setOverview] = useState<MarketOverview | null>(() => getCache<MarketOverview>("dr:overview") ?? null);
  const [emotion, setEmotion] = useState<ShortTermEmotion | null>(() => getCache<ShortTermEmotion>("dr:emotion") ?? null);
  // 情绪历史（ROUND2 阶段 1/2）：画趋势图用。空数组 = 还没回填/数据源不可用。
  const [emoHist, setEmoHist] = useState<EmotionHistoryRow[]>([]);
  const [turnover, setTurnover] = useState<TurnoverTop | null>(() => getCache<TurnoverTop>("dr:turnover") ?? null);
  // 实时行情属于哪一场：盘前接口返回的是上一场收盘，不标出来会被当成今天的
  const [session, setSession] = useState<MarketSession | null>(() => getCache<MarketSession>("dr:session") ?? null);
  // 今日实时打板情绪。与下面那块「昨日短线情绪」是两回事：
  // 这块随盘变，那块是已收盘那一场的定稿。
  const [liveEmo, setLiveEmo] = useState<LiveEmotion | null>(() => getCache<LiveEmotion>("dr:liveEmo") ?? null);
  // 昨日连板股的**今日**实时行情。昨日那份的「涨停%」全是 +10%（都涨停了，
  // 没信息量），换成今天的实时涨跌才回答「昨天的高标今天怎么样」。
  const [lianbanQuotes, setLianbanQuotes] = useState<Record<string, Quote>>({});
  // 自动刷新开关：**默认关**（别替用户决定要不要一直打请求），选择记在本地
  const [autoRefresh, setAutoRefresh] = useState<boolean>(
    () => localStorage.getItem(AUTO_KEY) === "1");

  // 各数据块请求是否已结束：区分「加载中」与「数据源暂不可用」（非交易时段/被限流时后端返回空）
  const [ovDone, setOvDone] = useState(() => hasCache("dr:overview"));
  const [emoDone, setEmoDone] = useState(() => hasCache("dr:emotion"));
  const [toDone, setToDone] = useState(() => hasCache("dr:turnover"));

  /** 拉这批代码的实时行情（昨日连板股用）。空名单直接返回，别打空请求。
   *  ⚠️ 必须定义在 `loadLive` **之前**：`const` 箭头函数没有提升，
   *  写在后面 `loadLive()` 首次调用就会 ReferenceError（TDZ）。 */
  const refreshLianban = (codes: string[]) => {
    if (!codes.length) return;
    api.quote(codes.join(",")).then((q) => { setCache("dr:lianbanQuotes", q); setLianbanQuotes(q); }).catch(() => {});
  };

  // 轻量实时组：全是腾讯批量行情，一次一个请求，5 秒一刷不吃力
  const loadLive = () => {
    api.marketSession().then((d) => { setCache("dr:session", d); setSession(d); }).catch(() => {});
    api.liveEmotion().then((d) => { setCache("dr:liveEmo", d); setLiveEmo(d); }).catch(() => {});
    // 连板股名单来自「昨日」那份，这里只刷它们的实时价
    refreshLianban((emotion?.lianban_stocks ?? []).map((s) => s.code));
  };
  // 重量组：板块资金走 akshare + JS 引擎（90 个行业）、成交额榜走东财 clist。
  // **不能跟着 5 秒刷** —— 会撞限流，而且这两样本身变化慢。
  const loadHeavy = () => {
    api.marketOverview().then((d) => { setCache("dr:overview", d); setOverview(d); }).catch(() => {}).finally(() => setOvDone(true));
    api.turnoverTop().then((d) => { setCache("dr:turnover", d); setTurnover(d); }).catch(() => {}).finally(() => setToDone(true));
  };

  // 短线情绪锚在已收盘那一场，只在进页面时取一次，不参与任何轮询
  const loadSettled = () => {
    api.emotion().then((d) => { setCache("dr:emotion", d); setEmotion(d); }).catch(() => {}).finally(() => setEmoDone(true));
    // 情绪历史（ROUND2 阶段 1）：只在进页时取。历史一天只变一次，
    // 跟 5 秒轮询毫无意义。
    api.emotionHistory(30).then((rows) => setEmoHist(rows ?? [])).catch(() => setEmoHist([]));
  };

  const loadIndices = () => { loadLive(); loadHeavy(); loadSettled(); };

  // 数据块占位：请求没回来 = 加载中；回来了但为空 = 数据源暂不可用（别让用户干等）
  const pending = (done: boolean) => (
    <p className="py-4 text-center text-sm text-muted-foreground/60">
      {done ? "暂无数据：可能是非交易时段或数据源暂时不可用，可点「大盘指数」旁的刷新重试" : "加载中…"}
    </p>
  );

  useEffect(() => {
    // 切页回来不重取：已缓存过就直接用内存里的，只有手动点刷新（loadIndices）才重拉。
    if (!hasCache("dr:overview")) loadIndices();
  }, []);

  // 连板股名单是异步来的，首次 loadLive 时它还没回来 —— 名单一到补拉一次
  useEffect(() => {
    refreshLianban((emotion?.lianban_stocks ?? []).map((s) => s.code));
  }, [emotion?.date, emotion?.lianban_stocks?.length]);

  // ⭐ 自动刷新。三条不能写错的地方：
  //  ① **交易时段用后端给的 `session.phase` 判断**，不要用 `new Date().getHours()`
  //     —— 那是本机时区，人在海外会盘中不刷、半夜狂刷。后端算的是北京时间。
  //  ② 收盘 / 非交易日**不刷** —— 数字不会动，白打请求还可能撞限流。
  //  ③ cleanup 必须把两个句柄都清掉，且**句柄只属于这一次 effect**。
  //     共享句柄或忘了清，旧的定时器会活下来跟新的并行 → 实际频率翻倍。
  useEffect(() => {
    const live = session?.phase === "盘中" || session?.phase === "集合竞价";
    if (!autoRefresh || !live) return;

    const liveTimer = setInterval(() => {
      loadLive();
    }, LIVE_MS);
    const heavyTimer = setInterval(loadHeavy, HEAVY_MS);
    return () => { clearInterval(liveTimer); clearInterval(heavyTimer); };
  }, [autoRefresh, session?.phase]);

  const toggleAuto = () => {
    const next = !autoRefresh;
    setAutoRefresh(next);
    localStorage.setItem(AUTO_KEY, next ? "1" : "0");
  };

  const today = new Date().toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });
  // 是否处在会动的时段（后端判定，避免本机时区坑）
  const liveNow = session?.phase === "盘中" || session?.phase === "集合竞价";

  const dataSummary = overview?.sentiment?.breadth
    ? `大盘宽度「${overview.sentiment.breadth}」、题材投机「${overview.sentiment.speculation}」；` +
      `涨停 ${overview.sentiment.zt ?? "—"}、跌停 ${overview.sentiment.dt ?? "—"}`
    : "（盘面数据未取到）";

  const sentiment = overview?.sentiment;
  const sectors = overview?.sectors || [];
  const sentCells = sentiment ? [
    { k: "上涨家数", v: sentiment.up, up: true },
    { k: "下跌家数", v: sentiment.down, up: false },
    { k: "平盘", v: sentiment.flat, up: null },
    { k: "涨停", v: sentiment.zt, up: true },
    { k: "真实涨停", v: sentiment.zt_real, up: true },
    { k: "跌停", v: sentiment.dt, up: false },
    { k: "真实跌停", v: sentiment.dt_real, up: false },
    { k: "活跃度", v: sentiment.active == null ? null : Number(sentiment.active), up: null },
  ] : [];

  // 向全局 AI 浮标登记本页确定性数据快照（S5 接后端后用作对话上下文；现仅展示）
  useAiPage({
    key: `daily-review:${session?.label ?? today}`,
    title: "复盘看板",
    context:
      `日期：${session?.label ?? today}\n盘面概览：${dataSummary}\n` +
      (sentiment?.breadth
        ? `市场情绪：大盘宽度「${sentiment.breadth}」、题材投机「${sentiment.speculation}」；` +
          `涨停 ${sentiment.zt ?? "—"}（真实 ${sentiment.zt_real ?? "—"}）、跌停 ${sentiment.dt ?? "—"}`
        : "市场情绪：暂未取到") +
      (emotion?.max_boards != null ? `\n昨日连板：最高 ${emotion.max_boards} 板、连板 ${emotion.lianban_count} 家` : ""),
    suggestions: ["今天大盘怎么走", "哪些板块资金在流入", "连板梯队说明什么"],
  });

  // M5-4：把本页数据的真实时点报给底栏。
  // 用实时打板情绪的 date/as_of（这是唯一带精确到分钟时点的接口）；
  // 取不到就报「有数据但时点未知」，而不是装作没问题 —— 未知的时间戳
  // 和不显示时间戳一样危险。
  // auto 版：取数时刻由 hook 按 key 变化自己记录。
  // 手动写 fetchedAt: Date.now() 会无限重渲染（这页踩过）。
  useDataAsOfAuto(
    liveEmo?.available && liveEmo.date
      ? { dataAsOf: liveEmo.date, label: "打板情绪快照" }
      : { dataAsOf: "", label: "盘面数据" },
  );

  return (
    <div>
      <PageHeader
        title="复盘看板"
        subtitle={`${session?.label ?? today} · 指数 / 外围 / 板块资金一屏看全`}
        actions={
          <div className="flex items-center gap-2">
            {/* 开着但不在交易时段时要说清「为什么不动」——否则会被当成坏了 */}
            <button
              onClick={toggleAuto}
              title={autoRefresh
                ? `已开：指数/外围/自选每 ${LIVE_MS / 1000} 秒、板块资金与成交额榜每 ${HEAVY_MS / 1000} 秒。只在盘中生效`
                : "开启后在交易时段自动刷新行情"}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm transition-colors",
                autoRefresh
                  ? "bg-primary/15 text-primary hover:bg-primary/25"
                  : "text-muted-foreground hover:text-primary",
              )}
            >
              <RefreshCw className={cn("h-3.5 w-3.5", autoRefresh && liveNow && "animate-spin")} />
              {autoRefresh ? (liveNow ? `每 ${LIVE_MS / 1000} 秒自动刷新` : "自动刷新（非交易时段暂停）") : "自动刷新"}
            </button>
          </div>
        }
      />

      {/* 4. 市场情绪 */}
      <div className="mb-3 flex items-center gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold text-muted-foreground"><Gauge className="h-4 w-4" /> 市场情绪</h3>
        <Caliber text={
          "涨停 / 真实涨停 / 跌停 / 真实跌停 / 活跃度这几个数取自乐咕乐股，不是我们算的。\n" +
          "「真实」与普通涨跌停的差额由它自己的口径决定，具体算法未公开。\n" +
          "活跃度同样是它的算法，**不能按上涨家数占比来理解**（今天 1786/5197 = 34.4%，它给的是 34.33%）。\n" +
          "大盘宽度按涨跌家数机械分档：上涨不足 600 家为冰点，其余看 上涨÷下跌 的比值\n" +
          "（<0.7 偏弱 / 0.7-1.2 中性 / 1.2-2.5 偏强 / ≥2.5 普涨）。\n" +
          "题材投机只按真实涨停家数分档：<30 冰点 / 30-59 普通 / 60-99 活跃 / ≥100 亢奋。"
        } />
        {sentiment?.date && <span className="text-[11px] text-muted-foreground/50">{sentiment.date}</span>}
      </div>
      {/* ROUND2 §9：这块原来是两个 2xl 大字卡 + 8 个数字格，占掉半屏却只给 8 个数。
          用户反复说「留白太多」，而这是最典型的例子：容器很大、信息很少。
          改成一行紧凑摘要 —— 分档结论用徽标、8 个数并排；
          真正的「看趋势」交给下面的情绪趋势图（那里才有历史可比）。 */}
      <Panel className="mb-6">
        {!sentiment?.breadth ? (
          pending(ovDone)
        ) : (
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
            {[
              { k: "大盘宽度", v: sentiment.breadth },
              { k: "题材投机", v: sentiment.speculation },
            ].map((m) => (
              <span key={m.k} className="inline-flex items-baseline gap-1.5">
                <span className="text-[11px] text-muted-foreground">{m.k}</span>
                <span className="rounded-[2px] bg-muted/40 px-1.5 py-0.5 text-[13px] font-semibold text-primary">
                  {m.v}
                </span>
              </span>
            ))}
            <span className="h-4 w-px bg-border" />
            {sentCells.map((c) => (
              <span key={c.k} className="inline-flex items-baseline gap-1.5">
                <span className="text-[11px] text-muted-foreground">{c.k}</span>
                <span className={cn(
                  "font-mono text-[13px] font-semibold",
                  c.up === null ? "text-foreground" : c.up ? "text-danger" : "text-success",
                )}>
                  <Num v={c.v} digits={0} inheritColor />
                </span>
              </span>
            ))}
          </div>
        )}
      </Panel>

      {/* 4b. 情绪趋势（ROUND2 阶段 2）—— 把孤立数字变成可比对的曲线。

          用户原话：「单纯的独立的数字是看不出来什么的，需要跟之前的数据进行
          比对才知道」。上面那些面板全是当日快照，看不出「今天是变好还是变差」。

          四张图的分工：
            · 涨停/跌停/炸板 —— 同一件事的三个侧面，必须并排
            · 最高连板     —— 短线情绪最关键的一条线（高度 = 接力意愿）
            · 封板率/炸板率 —— 互补值，一起看才知道是强是弱
            · 连板梯队     —— 阶梯形状本身就是信息（有没有高标孤挂）

          全部走 EChart；不传 legend（窄容器会压绘图区）。 */}
      <div className="mb-3 flex flex-wrap items-baseline gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold text-muted-foreground">
          <TrendingUp className="h-4 w-4" /> 情绪趋势
        </h3>
        {emoHist.length > 0 && (
          <span className="text-[11px] text-muted-foreground/50">
            {emoHist.length} 个交易日（{emoHist[0].date} ~ {emoHist[emoHist.length - 1].date}）
          </span>
        )}
        <Caliber text={
          "数据来自东财涨停板四池（涨停/炸板/跌停/昨涨停），按交易日聚合。\n" +
          "上游只保留约 28 天历史，所以左侧起点不会是「30 天前」，而是能取到的最早一天；\n" +
          "之后靠每日落库慢慢向前延伸。\n" +
          "封板率 = 涨停 ÷（涨停 + 炸板）；炸板率是它的补数。\n" +
          "空白的点是当天取不到该字段，不是 0（补 0 会在图上造出假的断崖）。"
        } />
      </div>
      <Panel className="mb-6">
        {emoHist.length === 0 ? (
          <p className="py-6 text-center text-[12px] text-muted-foreground/60">
            还没有情绪历史。跑一次 <code className="font-mono">python3 scripts/backfill-emotion.py</code> 回填，
            之后每天自动积累。
          </p>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <p className="mb-1 text-[11px] text-muted-foreground">涨停 / 跌停 / 炸板（家）</p>
              <ToneLegend
                items={[
                  { label: "涨停", tone: "up" },
                  { label: "跌停", tone: "down" },
                  { label: "炸板", tone: "neutral" },
                ]}
              />
              <EChart option={ztDtZbOption(emoHist as never)} height={190} />
            </div>
            <div>
              <p className="mb-1 text-[11px] text-muted-foreground">最高连板（板）</p>
              <EChart option={maxBoardsOption(emoHist as never)} height={190} />
            </div>
            <div>
              <p className="mb-1 text-[11px] text-muted-foreground">封板率 / 炸板率</p>
              <ChartLegend items={["封板率", "炸板率"]} />
              <EChart option={sealBreakOption(emoHist as never)} height={190} />
            </div>
            <div>
              <p className="mb-1 text-[11px] text-muted-foreground">连板梯队（家）</p>
              <EChart option={ladderOption((emotion?.ladder ?? []) as never)} height={190} />
            </div>
          </div>
        )}
      </Panel>

      {/* 4a/4b 合并：打板情绪（实时 vs 收盘定稿）—— ROUND2 §9 续。

          原来这里是**两个几乎一样的面板**：各 4 个大数字卡 + 3~4 个比率卡，
          同样的 7 个指标写两遍，吃掉将近两屏。这是「留白多」和「数字多」
          最典型的一处。

          合并成一张对照表，还有额外好处：**两源的差异本身就是信息**。
          实测 2026-10-22 实时跌停 0 家、收盘定稿 49 家 —— 并排放才看得出
          「实时源那一路没在跟跌停」，而不是让人在两张卡之间来回对。 */}
      <div className="mb-3 flex flex-wrap items-baseline gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold text-muted-foreground">
          <Flame className="h-4 w-4" /> 打板情绪
        </h3>
        <Caliber text={
          "左列是**实时**（随盘变化），右列是**已收盘定稿**（复盘口径）。\n" +
          "两列来自不同数据源，数值不一致是正常的 —— 并排是为了让你看见差异，\n" +
          "不是为了「取哪个更准」。\n" +
          "封板率 = 最终封住家数 ÷ 摸板家数；炸板率 = 炸板未回封家数 ÷ 摸板家数。\n" +
          "摸板家数 = 涨停 + 炸板，**按家数算，不按炸板次数算**。"
        } />
        {liveEmo?.available && (
          <span className="text-[11px] text-warning">
            实时 {liveEmo.date} {liveEmo.as_of} · {liveEmo.phase}
          </span>
        )}
        {emotion?.date && (
          <span className="ml-auto text-[11px] text-muted-foreground/50">
            定稿 {emotion.date} 收盘
          </span>
        )}
      </div>
      <Panel className="mb-6">
        {!emotion || emotion.zt_count === undefined ? (
          pending(emoDone)
        ) : (
          (() => {
            // 每行 = 一个指标；live 缺值就留 —，**不要**用定稿值顶替
            // （顶替会让人以为实时源也是这个数）。
            const rows: { k: string; live: number | null | undefined; settled: number | null | undefined;
                          tone: "up" | "down" | "neutral"; pct?: boolean; unit?: string }[] = [
              { k: "涨停", live: liveEmo?.zt_count, settled: emotion.zt_count, tone: "up", unit: " 家" },
              { k: "跌停", live: liveEmo?.dt_count, settled: emotion.dt_count, tone: "down", unit: " 家" },
              { k: "炸板", live: liveEmo?.zb_count, settled: emotion.zb_count, tone: "neutral", unit: " 家" },
              { k: "最高连板", live: liveEmo?.max_boards, settled: emotion.max_boards, tone: "up", unit: " 板" },
              { k: "连板（2板+）", live: liveEmo?.lianban_count, settled: emotion.lianban_count, tone: "up", unit: " 家" },
              { k: "封板率", live: liveEmo?.seal_rate, settled: emotion.seal_rate, tone: "up", pct: true },
              { k: "炸板率", live: liveEmo?.break_rate, settled: emotion.break_rate, tone: "down", pct: true },
              { k: "晋级率", live: liveEmo?.promotion_rate, settled: emotion.promotion_rate, tone: "up", pct: true },
            ];
            const toneCls = (t: string) => t === "up" ? "text-danger" : t === "down" ? "text-success" : "text-foreground";
            return (
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="border-b border-border text-left text-[11px] text-muted-foreground">
                    <th className="px-2 py-1.5 font-medium">指标</th>
                    <th className="px-2 py-1.5 text-right font-medium">实时</th>
                    <th className="px-2 py-1.5 text-right font-medium">收盘定稿</th>
                    <th className="px-2 py-1.5 text-right font-medium">差异</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const l = r.live, st = r.settled;
                    const diff = (typeof l === "number" && typeof st === "number") ? l - st : null;
                    // 差异显著才标色：小差异（如晋级率 18.0% vs 17.6%）只是取整，不是信号
                    const notable = diff != null && (r.pct ? Math.abs(diff) >= 0.02 : Math.abs(diff) >= 3);
                    return (
                      <tr key={r.k} className="border-b border-border/40">
                        <td className="px-2 py-1.5 text-muted-foreground">{r.k}</td>
                        <td className={cn("px-2 py-1.5 text-right font-mono", toneCls(r.tone))}>
                          {typeof l === "number"
                            ? (r.pct ? <Num v={l} rate digits={1} inheritColor />
                                     : <Num v={l} digits={0} suffix={r.unit} inheritColor />)
                            : <span className="text-muted-foreground/40">—</span>}
                        </td>
                        <td className={cn("px-2 py-1.5 text-right font-mono", toneCls(r.tone))}>
                          {typeof st === "number"
                            ? (r.pct ? <Num v={st} rate digits={1} inheritColor />
                                     : <Num v={st} digits={0} suffix={r.unit} inheritColor />)
                            : <span className="text-muted-foreground/40">—</span>}
                        </td>
                        <td className="px-2 py-1.5 text-right font-mono text-[11px]">
                          {diff == null ? (
                            <span className="text-muted-foreground/40">—</span>
                          ) : notable ? (
                            /* 差异列**不按正负上色**：它表达的是「两源不一致」，
                               不是市场方向。曾经按正负染色，结果跌停差 −49 被染成
                               绿色（看着像好事），而它其实只是实时源没在跟跌停。
                               用 warning 色明确标「这一行要留意」。 */
                            <span className="text-[hsl(var(--warning))]">
                              <Num v={r.pct ? diff * 100 : diff} digits={r.pct ? 1 : 0}
                                   signed inheritColor suffix={r.pct ? "%" : ""} />
                            </span>
                          ) : (
                            <span className="text-muted-foreground/50">
                              <Num v={r.pct ? diff * 100 : diff} digits={r.pct ? 1 : 0}
                                   signed inheritColor suffix={r.pct ? "%" : ""} />
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            );
          })()
        )}
      </Panel>

      {/* 4c. 连板股清单（原在「昨日短线情绪」面板内，独立成块） */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold text-muted-foreground">
          <Flame className="h-4 w-4" /> 连板股
        </h3>
        <Caliber text={
          "表里的「行业 / 概念」经常只有四个字（像「互联网电」「汽车零部」）——是上游把名字截到四字，\n" +
          "不是这里显示不全；怕猜错所以不替它补全称。\n" +
          "只有标（实时）的两列随盘刷新，其余是上一场收盘的数据。"
        } />
        <span className="text-[11px] text-muted-foreground/50">2 板以上 · 客观公开榜单，非推荐 / 非预测</span>
      </div>
      <Panel className="mb-6">
        {!emotion || emotion.zt_count === undefined ? (
          pending(emoDone)
        ) : (
          <>
            <div>
              {emotion.lianban_stocks.length === 0 ? (
                <p className="text-xs text-muted-foreground/50">今日无 2 板以上个股</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border/50 text-left text-xs text-muted-foreground">
                        {["名称", "连板", "现价（实时）", "今日涨跌（实时）", "昨日成交额", "流通市值", "涨停原因", "概念"].map((h) => (
                          <th key={h} className="whitespace-nowrap px-2 py-2 font-medium">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {emotion.lianban_stocks.map((s) => (
                        <Fragment key={s.code}>
                          <tr className="border-b border-border/30">
                            <td className="px-2 py-2"><span className="font-medium">{s.name}</span> <span className="text-xs text-muted-foreground/50">{s.code}</span></td>
                            <td className="whitespace-nowrap px-2 py-2 font-bold text-primary"><Num v={s.boards} digits={0} suffix=" 板" inheritColor /></td>
                            <td className="px-2 py-2">
                              {lianbanQuotes[s.code]?.price != null ? (
                                <Num v={lianbanQuotes[s.code].price} />
                              ) : (
                                <span className="text-muted-foreground/50 font-mono" title="实时行情未取到，显示昨收">
                                  <Num v={s.price} inheritColor />
                                </span>
                              )}
                            </td>
                            <td className="px-2 py-2">
                              {finite(lianbanQuotes[s.code]?.change_pct) !== null
                                ? <Num v={lianbanQuotes[s.code].change_pct} pct />
                                : <span className="text-muted-foreground/50" title="实时行情未取到">—</span>}
                            </td>
                            <td className="whitespace-nowrap px-2 py-2 text-muted-foreground"><Num v={yiV(s.amount)} digits={2} suffix=" 亿" inheritColor /></td>
                            <td className="whitespace-nowrap px-2 py-2 text-muted-foreground"><Num v={yiV(s.float_cap)} digits={2} suffix=" 亿" inheritColor /></td>
                            <td className="max-w-56 px-2 py-2 text-xs">
                              {s.reason ? <span className="text-foreground">{s.reason}</span> : <span className="text-muted-foreground/50">—</span>}
                            </td>
                            <td className="whitespace-nowrap px-2 py-2 text-xs text-muted-foreground">{s.industry}</td>
                          </tr>
                        </Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}
      </Panel>

      {}
      <div className="mb-3 flex items-center gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold text-muted-foreground"><BarChart3 className="h-4 w-4" /> 全市场成交额 TOP20</h3>
        <Caliber text={
          "沪深京 A 股按当日累计成交额从大到小排。\n" +
          "盘中看到的成交额是「到刷新那一刻为止」的累计值，不是收盘值；总市值按当前价算。\n" +
          "名字前面带 C 的是上市不满一年的次新股标记，不是名字的一部分。"
        } />
        <span className="text-[11px] text-muted-foreground/50">客观公开榜单，非推荐 / 非预测 / 不构成投资建议</span>
        {turnover?.updated && <span className="ml-auto text-[11px] text-muted-foreground/50">更新于 {turnover.updated}</span>}
      </div>
      <Panel className="mb-6">
        {!turnover || turnover.stocks.length === 0 ? (
          pending(toDone)
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/50 text-left text-xs text-muted-foreground">
                  {["#", "名称", "现价", "涨跌%", "成交额", "总市值", "行业"].map((h) => (
                    <th key={h} className="whitespace-nowrap px-2 py-2 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {turnover.stocks.map((s, i) => (
                  <tr key={s.code} className="border-b border-border/30">
                    <td className="px-2 py-2 text-xs text-muted-foreground/50"><Num v={i + 1} digits={0} inheritColor /></td>
                    <td className="px-2 py-2"><span className="font-medium">{s.name}</span> <span className="text-xs text-muted-foreground/50">{s.code}</span></td>
                    <td className="px-2 py-2"><Num v={s.price} /></td>
                    <td className="px-2 py-2">
                      <Num v={s.pct} pct />
                    </td>
                    <td className="whitespace-nowrap px-2 py-2"><Num v={yiV(s.amount)} digits={2} suffix=" 亿" /></td>
                    <td className="whitespace-nowrap px-2 py-2 text-muted-foreground"><Num v={yiV(s.mcap)} digits={2} suffix=" 亿" inheritColor /></td>
                    <td className="whitespace-nowrap px-2 py-2 text-xs text-muted-foreground">{s.industry}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {/* 5. 板块资金趋势榜（行业） */}
      <div className="mb-3 flex items-center gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold text-muted-foreground"><TrendingUp className="h-4 w-4" /> 板块资金趋势榜</h3>
        <Caliber text={
          "净流入 / 流入 / 流出取自同花顺行业资金流的**盘中即时值**，单位亿元，净流入 = 流入 − 流出。\n" +
          "⚠️ 那边没说明这是主力资金还是全部成交资金，所以**不能当作主力净流入**来读。\n" +
          "涨跌% 是行业整体涨幅；成分股数是这个行业的公司总数，不是上涨家数、也不是涨停家数。"
        } />
        <span className="text-[11px] text-muted-foreground/50">行业 · 按今日净流入排序</span>
      </div>
      <Panel className="mb-6">
        {sectors.length === 0 ? (
          pending(ovDone)
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/50 text-left text-xs text-muted-foreground">
                  {["行业", "涨跌%", "今日净流入", "流入(亿)", "流出(亿)", "成分股数"].map((h) => (
                    <th key={h} className="whitespace-nowrap px-2 py-2 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sectors.slice(0, 15).map((s) => (
                  <tr key={s.name} className="border-b border-border/30">
                    <td className="px-2 py-2 font-medium">{s.name}</td>
                    <td className="px-2 py-2"><Num v={s.pct} pct size="sm" /></td>
                    <td className="px-2 py-2"><Num v={s.net} signed colorBySign digits={2} suffix=" 亿" size="sm" /></td>
                    <td className="px-2 py-2 text-muted-foreground"><Num v={s.inflow} digits={2} size="sm" inheritColor /></td>
                    <td className="px-2 py-2 text-muted-foreground"><Num v={s.outflow} digits={2} size="sm" inheritColor /></td>
                    <td className="px-2 py-2 text-muted-foreground"><Num v={s.firms} digits={0} size="sm" inheritColor /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {/* 6. 资金轮动 —— 改为正负双向柱状图（ROUND2 阶段 2）。

          原来这里是两个列表（流入 Top 6 / 流出 Top 6），内容与上面那张表
          的头部完全重复，等于同一份数据抄了两遍。换成双向柱之后：
            · 流入流出在同一根轴上，正负方向一眼可辨（列表要读符号）
            · 长短直接可比（列表要比较数字大小）
            · 不再和上面那张表重复 —— 表留明细，图给形状
          用户原话：「资金流入流出可以做成面积图或者 whatever」。 */}
      <div className="mb-3 flex items-center gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold text-muted-foreground"><ArrowDownUp className="h-4 w-4" /> 资金轮动</h3>
        <Caliber text={
          "就是上面那张榜的两头：净流入为正的向上、为负的向下，按金额排序取前 15 个行业。\n" +
          "口径同上：同花顺行业资金流盘中即时值，不能当主力净流入读。"
        } />
        <span className="text-[11px] text-muted-foreground/50">板块级净流入（亿）</span>
      </div>
      <Panel className="mb-6">
        {sectors.length === 0 ? (
          pending(ovDone)
        ) : (
          <EChart option={sectorFlowOption(sectors as never, 15)} height={360} />
        )}
      </Panel>

      {/* 7. 涨停样本统计（原独立页并入：确定性市场现象统计，非策略回测） */}
      <div className="mt-8 border-t border-border/50 pt-6">
        <LimitUpStats />
      </div>

    </div>
  );
}
