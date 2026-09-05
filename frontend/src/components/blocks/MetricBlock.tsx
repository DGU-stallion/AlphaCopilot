/**
 * MetricBlock — 渲染一组指标卡（KPI）。payload 形状：
 *   { items: [{ label: string, value: string|number, hint?: string, tone?: "up"|"down"|"flat"|"muted" }] }
 * 用于复盘看板 / 盘面数据的关键数值一屏概览。纯展示，颜色走 design token。
 */

interface MetricItem {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "up" | "down" | "flat" | "muted";
}

interface MetricPayload {
  items?: MetricItem[];
}

const TONE_CLASS: Record<string, string> = {
  up: "text-danger", // A 股红涨
  down: "text-success", // 绿跌
  flat: "text-foreground",
  muted: "text-muted-foreground",
};

export function MetricBlock({ payload, title }: { payload: MetricPayload; title?: string }) {
  const items = payload.items ?? [];
  return (
    <div className="glass rounded-lg p-3" data-testid="metric-block">
      {title && <div className="mb-2 text-sm font-medium text-foreground">{title}</div>}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {items.map((m, i) => (
          <div key={i} className="rounded-md bg-muted/20 p-3">
            <div className="text-xs text-muted-foreground">{m.label}</div>
            <div className={`mt-1 text-xl font-semibold ${TONE_CLASS[m.tone ?? "flat"]}`}>
              {String(m.value)}
            </div>
            {m.hint && <div className="mt-0.5 text-xs text-muted-foreground">{m.hint}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
