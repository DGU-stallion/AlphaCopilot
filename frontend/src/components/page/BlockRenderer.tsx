/**
 * 通用 block 渲染器（ADR-0016 决定 2）。
 *
 * 输入是后端 `POST /api/pages/{slug}/render` 回的单个 block，输出是一块 UI。
 * 它是「页面由 spec 拼装」这条链路的**最后一公里**：再往上一层是 PageCanvas
 * （摆栅格 + 参数控件），再往下就是具体的图组件。
 *
 * 分派规则（**不猜**）：
 *   kind=metric      → 指标项列表
 *   kind=table       → 表格
 *   kind=markdown    → 文本
 *   kind=chart
 *     + renderer=lwc     → EquityChart / PriceChart / MultiLineChart
 *     + renderer=echarts → EChart
 *     + 缺 renderer      → 提示（不兜底猜 ECharts）
 *
 * 为什么「缺 renderer 不兜底」：兜底会造成同一图形两套实现（ADR-0014 §6 图表分工
 * 反对的正是这个）。后端 `validate_spec` 已保证新 spec 必带 renderer，
 * 缺的只可能是老数据 —— 老数据宁可显示提示，也不要让它悄悄用错渲染器。
 */
import { Panel } from "@/components/ui/Panel";
import { Num } from "@/components/Num";
import { EChart } from "@/components/ui/EChart";
import { EquityChart } from "@/components/charts/EquityChart";
import { PriceChart } from "@/components/charts/PriceChart";
import { MultiLineChart } from "@/components/charts/MultiLineChart";
import { lwcToBars } from "./lwc-bars";
import type { MetricItem, RenderBlock } from "@/lib/research";
import { pctColor } from "@/lib/colors";
import { cn } from "@/lib/utils";

const toneCls = (t?: MetricItem["tone"]) =>
  t === "up" ? pctColor(1) : t === "down" ? pctColor(-1) : "text-foreground";

/** 无数据时的统一提示。白屏会被读成「应用坏了」，必须给一句话。 */
function Empty({ what }: { what: string }) {
  return (
    <p className="py-8 text-center text-[12px] text-muted-foreground/60">
      {what}数据暂不可用
    </p>
  );
}

/** 剥掉 ECharts option 里的 title —— 外层 h3 已经显示了标题，再画一遍就重复了。 */
function stripTitle(opt: Record<string, unknown> | null | undefined) {
  if (!opt) return null;
  const { title: _t, ...rest } = opt as Record<string, unknown>;
  return rest;
}

function MetricBlock({ block }: { block: RenderBlock }) {
  const items = block.metric?.items ?? [];
  if (items.length === 0) return <Empty what="指标" />;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {items.map((it) => (
        <div
          key={it.label}
          className="rounded-[4px] border border-border px-3 py-2"
        >
          <p className="truncate text-[11px] text-muted-foreground">{it.label}</p>
          <p
            className={cn("mt-1 font-mono text-[16px] font-semibold", toneCls(it.tone))}
            style={{ fontVariantNumeric: "tabular-nums" }}
          >
            {String(it.value)}
          </p>
          {it.hint && (
            <p className="mt-0.5 truncate text-[11px] text-muted-foreground/50">{it.hint}</p>
          )}
        </div>
      ))}
    </div>
  );
}

function TableBlock({ block }: { block: RenderBlock }) {
  const t = block.table;
  if (!t || t.columns.length === 0) return <Empty what="表格" />;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="border-b border-border text-left text-[11px] text-muted-foreground">
            {t.columns.map((c) => (
              <th key={c} className="px-2 py-1.5 font-medium">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {t.rows.map((row, i) => (
            <tr key={i} className="border-b border-border/40">
              {row.map((cell, j) => (
                <td
                  key={j}
                  className="px-2 py-1.5"
                  style={typeof cell === "number" ? { fontVariantNumeric: "tabular-nums" } : undefined}
                >
                  {/* 数字走 Num：等宽 + 涨跌色，不裸写 toFixed（AGENTS 硬规则 7） */}
                  {typeof cell === "number" ? <Num v={cell} digits={2} colorBySign /> : String(cell ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ChartBlock({ block }: { block: RenderBlock }) {
  // lwc 分派：**按载荷形状，不按 series 条数**。
  //
  // 曾经按「series > 1 就上 EquityChart」分派，结果是错的：`backtest.equity`
  // 本身就是 2 条 series（策略 vs 买入持有），于是净值图被当成「净值+回撤」，
  // EquityChart 又自动加了一个空回撤 pane；紧接着后面的 `backtest.drawdown`
  // 块再画一遍回撤 —— 同一屏两份回撤，且第一份是空线（实测截图发现）。
  //
  // 真正的判别符是 `payload.drawdown` 有没有值：只有当 lwc 载荷自带回撤数组时，
  // 才该用 EquityChart 的单实例多 pane（ADR-0014 §6）。
  //
  // ROUND3 D5：**在「没有 drawdown」这条分支里**再分单条 / 多条 ——
  //   1 条 → PriceChart（单线折线，现状）
  //   >1 条 → MultiLineChart（多线同 pane，相关性叠加走势）
  // 注意这里不是把上面的判定改成「按条数」：drawdown 判别仍然优先，
  // 否则会重新踩「净值 vs 买入持有被当成净值 vs 回撤」的老坑。
  if (block.renderer === "lwc") {
    const payload = block.lwc;
    const series = payload?.series ?? [];
    if (series.length === 0) return <Empty what="序列" />;

    const hasDrawdownPayload = Array.isArray(payload?.drawdown) && payload!.drawdown!.length > 0;
    if (hasDrawdownPayload) {
      return <EquityChart payload={payload!} height={300} />;
    }

    // 多条线量纲相同（起点=100 的相对走势 / 相关系数），同 pane 叠画不分区。
    if (series.length > 1) {
      return <MultiLineChart payload={payload!} height={260} />;
    }

    const bars = lwcToBars(payload!);
    if (bars.length === 0) return <Empty what="序列" />;
    return (
      <div style={{ height: 220 }}>
        <PriceChart bars={bars} mode="line" />
      </div>
    );
  }

  if (block.renderer === "echarts") {
    const opt = stripTitle(block.option);
    if (!opt) return <Empty what="图表" />;
    return <EChart option={opt} height={220} />;
  }

  // 缺 renderer：老数据。不猜 —— 猜错就是同一图形两套实现。
  return (
    <p className="py-8 text-center text-[12px] text-muted-foreground/60">
      未知渲染器（这条数据缺少 renderer 判别符）
    </p>
  );
}

/**
 * 渲染一个 block。
 *
 * `span` 由 PageCanvas 消费（放进栅格），这里不管布局 —— 一个组件只做一件事。
 * 标题用外层 panel 的 h3，不交给图表自己画（重复标题是实测踩过的）。
 */
export function BlockRenderer({ block }: { block: RenderBlock }) {
  const body =
    block.kind === "metric" ? <MetricBlock block={block} />
    : block.kind === "table" ? <TableBlock block={block} />
    : block.kind === "markdown" ? (
        <p className="whitespace-pre-wrap text-[12px] leading-[1.6] text-foreground/90">
          {block.text || ""}
        </p>
      )
    : <ChartBlock block={block} />;

  return (
    <Panel>
      {block.title && block.kind !== "metric" && (
        <h3 className="mb-2 text-[12px] font-semibold">{block.title}</h3>
      )}
      {body}
    </Panel>
  );
}
