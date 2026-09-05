import { useState } from "react";
import { pctColor } from "@/lib/colors";
import { TrendingDown, Loader2, RefreshCw, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { api, type BacktestData, type SampleStats, type SampleDay } from "@/lib/api";
import { useCachedResource } from "@/lib/cache";

// 涨停样本统计（缝合搬运自 vibe-astock Backtest.tsx）。确定性统计，非 AI。
// 定位改造：接 useCachedResource（按天数缓存，切页不重取，刷新按钮 POST 重算）；
// vibe-astock 专有的 ArchiveNote/DriftNote（依赖 /api/archive /api/drift 端点）本仓库
// 暂无，先不搬；分情绪环境 RegimeRow 依赖 emotion 缓存层，MVP 暂不展示。
// ⚠️ CAVEAT / DISCLAIMER 原文风险提示不得删、不得弱化。

const DISCLAIMER =
  "回测是对「一条规则」在历史上的统计，不是对任何个股的推荐，也不产出前瞻标的。历史统计不代表未来表现。";

// ⚠️ 这段警告不能删也不能弱化。样本是"事后知道封住了"的名单 ——
// 实测某日 141 只票冲过板、只有 116 只封住，18% 的失败样本完全不在统计里。
// 把这里的数字当成"打板这套打法的期望"是会亏钱的误读。
const CAVEAT =
  "这是「市场现象统计」，不是策略回测。样本 = 昨日收盘留在涨停池里的票（事后名单）——"
  + "冲板没封住的、排队没成交的、一字板买不进的都不在内（实测某日 141 只冲板仅 116 只封住，"
  + "18% 失败样本没算）。真实打板的期望必然低于这里的数字。";

const EMPTY: SampleStats = {
  sample: 0, win_rate: null, avg: null, median: null, best: null, worst: null, limit_up_rate: null,
};

// ⚠️ 一律先过 finite()：NaN / Infinity 会溜过 `v == null`，显示成 "NaN%" 或灌进 CSS 宽高
function finite(v?: number | null): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}
function pctOf(v?: number | null): string {
  const n = finite(v);
  return n === null ? "—" : `${Math.round(n * 100)}%`;
}
function signed(v?: number | null): string {
  const n = finite(v);
  return n === null ? "—" : `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
}
function tone(v?: number | null): string {
  const n = finite(v);
  if (n === null) return "text-muted-foreground";
  return pctColor(n);
}

export function LimitUpStats() {
  // 默认 30：数据源对更早的日期留存有限，拉 60/90 会有大量必然失败的请求空等
  const [days, setDays] = useState(30);
  const res = useCachedResource<BacktestData>(`bt:${days}`, () => api.backtest(days));
  const data = res.data;
  const loading = res.loading;

  const strategies = Object.entries(data?.strategies ?? {});
  const curve = (data?.seal_curve ?? []).filter((b) => b.sample > 0);
  // 「全体涨停」是基准线，其它策略对照它才知道有没有超额
  const base = data?.strategies?.["全体涨停"]?.overall.avg ?? null;

  const refresh = () => {
    // 强制刷新走 POST：它会访问外网、算一两分钟、写盘，后端只认 POST（防跨站 GET 触发）
    api.backtestRefresh(days).catch(() => {}).finally(() => res.refresh());
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-glow">
            <TrendingDown className="h-6 w-6 text-primary" /> 涨停样本统计
          </h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            昨日涨停样本在次日的历史表现 · 不是策略回测
            {data?.available && ` · ${data.date_from} ~ ${data.date_to} · ${data.days_used} 个交易日`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}
            className="rounded-lg border border-border bg-card px-3 py-2 text-sm">
            {[20, 30, 60, 90].map((d) => <option key={d} value={d}>近 {d} 个交易日</option>)}
          </select>
          <button onClick={refresh} disabled={loading}
            className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50">
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            {loading ? "统计中" : "重新统计"}
          </button>
        </div>
      </div>

      <div className="flex items-start gap-2 rounded-xl border border-warning/30 bg-warning/10 px-4 py-2.5 text-[12px] leading-relaxed text-warning">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {CAVEAT}
      </div>

      {res.error != null && (
        <div className="glass rounded-xl border-danger/30 px-4 py-3 text-sm text-danger">
          出错：请求失败，后端（8900）是否已启动？
        </div>
      )}
      {data && !data.available && (
        <div className="rounded-xl border border-border bg-muted/20 px-4 py-3 text-[13px] leading-relaxed text-muted-foreground">
          暂不可用：{data.reason || "数据源不可达"}
        </div>
      )}
      {!!data?.missing_days?.length && (
        <div className="rounded-xl border border-border bg-muted/20 px-4 py-2.5 text-[12px] leading-relaxed text-muted-foreground">
          请求 {data.days_requested} 天，实际可用 <b className="text-foreground">{data.days_used}</b> 天：
          有 {data.missing_days.length} 个交易日取数失败已剔除
          （{data.missing_days.slice(0, 6).join("、")}{data.missing_days.length > 6 ? " …" : ""}）。
          <br />
          数据源只留最近约 15 个交易日，<b className="text-foreground">过期不候</b>。
        </div>
      )}

      {loading && !data && (
        <div className="glass rounded-2xl py-16 text-center text-muted-foreground">
          正在逐日取数统计…<div className="mt-1 text-xs">首次约 1-2 分钟，之后走缓存很快</div>
        </div>
      )}

      {/* 封板时间曲线：首板里最强的单一过滤变量，把悬崖位置直接摆出来 */}
      {!!curve.length && (
        <div className="glass rounded-2xl p-5">
          <h3 className="text-base font-bold">首板 · 最后封板时间曲线</h3>
          <p className="mb-4 text-[11px] leading-relaxed text-muted-foreground/70">
            同样是首板，什么时候把板<b>最终封住</b>决定了期望是正是负。数据源给的是<b>最后封板时间</b>，
            所以"晚"同时意味着封得晚、或中途炸开过又回封——两者都指向同一件事：这个板不稳。
            只统计首板，连板股的封板时间含义不同、混在一起会污染结论。
          </p>
          <div className="space-y-2">
            {curve.map((b) => {
              const w = Math.min(100, Math.abs(b.avg ?? 0) * 30);
              return (
                <div key={b.bucket} className="flex items-center gap-3 text-[12px]">
                  <span className="w-24 shrink-0 text-muted-foreground">{b.bucket}</span>
                  {/* 以 0 为中轴，左红右绿 */}
                  <div className="flex flex-1 items-center">
                    <div className="flex h-4 w-1/2 justify-end">
                      {(b.avg ?? 0) < 0 && <div className="h-full rounded-l bg-success/70" style={{ width: `${w}%` }} />}
                    </div>
                    <div className="h-4 w-px bg-border" />
                    <div className="flex h-4 w-1/2">
                      {(b.avg ?? 0) > 0 && <div className="h-full rounded-r bg-danger/70" style={{ width: `${w}%` }} />}
                    </div>
                  </div>
                  <span className={cn("w-16 shrink-0 text-right font-bold tabular-nums", tone(b.avg))}>{signed(b.avg)}</span>
                  <span className="w-28 shrink-0 text-right tabular-nums text-muted-foreground">
                    胜 {pctOf(b.win_rate)} · 再涨停 {pctOf(b.limit_up_rate)}
                  </span>
                  <span className="w-14 shrink-0 text-right tabular-nums text-muted-foreground/60">n={b.sample}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {strategies.map(([name, s]) => {
          // ⚠️ 单条策略的嵌套结构也可能缺（旧缓存 schema），不能假定完整
          const o = s?.overall ?? EMPTY;
          const daily: SampleDay[] = Array.isArray(s?.daily) ? s.daily : [];
          const isBase = name === "全体涨停";
          const excess = !isBase && base != null && o.avg != null ? o.avg - base : null;
          return (
            <div key={name} className={cn("glass rounded-2xl p-5", isBase && "border border-dashed border-border")}>
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <h3 className="text-base font-bold">{name}</h3>
                {isBase && <span className="rounded bg-muted px-2 py-0.5 text-[10px] font-bold text-muted-foreground">基准</span>}
                {excess != null && (
                  <span className={cn("rounded px-2 py-0.5 text-[10px] font-bold",
                    excess > 0 ? "bg-danger/15 text-danger" : "bg-success/15 text-success")}>
                    超额 {signed(excess)}
                  </span>
                )}
                {!!o.sample && o.sample < 60 && (
                  <span className="rounded bg-warning/15 px-2 py-0.5 text-[10px] font-bold text-warning">样本偏小</span>
                )}
              </div>
              <p className="mb-3 text-[11px] leading-relaxed text-muted-foreground/70">{s.desc}</p>

              {o.sample ? (
                <>
                  <div className="flex items-end gap-6">
                    <div>
                      <div className={cn("text-2xl font-extrabold tabular-nums", tone(o.avg))}>{signed(o.avg)}</div>
                      <div className="text-[11px] text-muted-foreground">期望（均值）</div>
                    </div>
                    <div>
                      <div className={cn("text-2xl font-extrabold tabular-nums", tone(o.median))}>{signed(o.median)}</div>
                      <div className="text-[11px] text-muted-foreground">中位数</div>
                    </div>
                    <div>
                      <div className="text-2xl font-extrabold tabular-nums">{pctOf(o.win_rate)}</div>
                      <div className="text-[11px] text-muted-foreground">胜率</div>
                    </div>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 border-t border-dashed border-border pt-2 text-[12px] text-muted-foreground">
                    <span>样本 {o.sample}</span>
                    <span>再涨停 <b className="text-foreground">{pctOf(o.limit_up_rate)}</b></span>
                    <span>最好 <b className="text-success">{signed(o.best)}</b></span>
                    <span>最差 <b className="text-danger">{signed(o.worst)}</b></span>
                  </div>

                  {/* 日均收益柱：一眼看出赚亏集中在哪几天 */}
                  <div className="mt-3 flex h-9 items-stretch gap-px border-t border-dashed border-border pt-2">
                    {daily.map((d) => (
                      <div key={d.date} title={`${d.date}｜均涨 ${signed(d.avg)}｜样本 ${d.sample}`}
                        className="flex flex-1 flex-col justify-center">
                        <div className="flex h-1/2 items-end">
                          {(d.avg ?? 0) > 0 && (
                            <div className="w-full bg-danger/70"
                              style={{ height: `${Math.min(100, Math.abs(d.avg!) * 10)}%` }} />
                          )}
                        </div>
                        <div className="flex h-1/2 items-start">
                          {(d.avg ?? 0) < 0 && (
                            <div className="w-full bg-success/70"
                              style={{ height: `${Math.min(100, Math.abs(d.avg!) * 10)}%` }} />
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-1 text-[11px] text-muted-foreground/60">逐日均收益（上红下绿 · 红涨绿跌）</div>
                </>
              ) : (
                <p className="text-[13px] text-muted-foreground">该策略在此窗口内无样本</p>
              )}
            </div>
          );
        })}
      </div>

      {data && (
        <p className="border-t border-border pt-4 text-xs text-muted-foreground/70">
          <Info className="mr-1 inline h-3 w-3" /> {DISCLAIMER}
        </p>
      )}
    </div>
  );
}
