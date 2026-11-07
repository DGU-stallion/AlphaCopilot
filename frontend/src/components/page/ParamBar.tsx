/**
 * 参数栏（ADR-0016 决定 2）：按 spec.params 自动生成控件。
 *
 * 控件类型由后端 ParamSpec 的 type 决定，前端**不猜**。这保证了
 * 「加一个参数」只需要改 spec，不需要改前端。
 *
 * 每个控件都带 `aria-label` / label 关联 —— 不只是无障碍，也是测试的抓手：
 * 用 data-testid 定位会让人为了测试改生产代码，用 label 则顺带保证可用性。
 */
import { Select, TextInput } from "@/components/ui/Form";
import { cn } from "@/lib/utils";
import { DATE_RANGE_PRESETS, RANGE_SEP, parseIsoRange, type PageParam } from "@/lib/page-spec";

/** Date → "YYYY-MM-DD"（本地时区，不用 toISOString 免得跨时区差一天）。 */
function ymd(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

interface Props {
  params: PageParam[];
  values: Record<string, unknown>;
  onChange: (name: string, value: unknown) => void;
}

function labelOf(p: PageParam): string {
  return p.label || p.name;
}

/** 一个参数 → 一个控件。返回 null 表示该类型暂无控件（未来的 type 不至于崩掉整栏）。 */
function Control({
  p,
  value,
  onChange,
}: {
  p: PageParam;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const id = `param-${p.name}`;

  switch (p.type) {
    case "int":
      return (
        <input
          id={id}
          aria-label={labelOf(p)}
          type="number"
          step={1}
          min={p.min}
          max={p.max}
          value={value === undefined || value === null ? "" : String(value)}
          onChange={(e) => {
            const raw = e.target.value;
            // 空串要给 NaN 以外的东西：给了 0 会掩盖「没填」，给 undefined 会让
            // 受控组件变成非受控（React 警告）。这里回 0，由后端 min 兜底。
            onChange(raw === "" ? 0 : Number(raw));
          }}
          className="h-7 w-full rounded-[4px] border border-border bg-[hsl(var(--card))] px-2 text-[12px] text-foreground outline-none focus:border-[hsl(var(--primary))]"
          style={{ fontVariantNumeric: "tabular-nums" }}
        />
      );

    case "float":
      return (
        <input
          id={id}
          aria-label={labelOf(p)}
          type="number"
          step="any"
          min={p.min}
          max={p.max}
          value={value === undefined || value === null ? "" : String(value)}
          onChange={(e) => onChange(e.target.value === "" ? 0 : Number(e.target.value))}
          className="h-7 w-full rounded-[4px] border border-border bg-[hsl(var(--card))] px-2 text-[12px] text-foreground outline-none focus:border-[hsl(var(--primary))]"
          style={{ fontVariantNumeric: "tabular-nums" }}
        />
      );

    case "enum":
      return (
        <Select
          id={id}
          aria-label={labelOf(p)}
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
        >
          {(p.choices ?? []).map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </Select>
      );

    case "date_range": {
      const cur = String(value ?? "");
      const iso = parseIsoRange(cur);
      const isPreset = DATE_RANGE_PRESETS.some((o) => o.value === cur);
      // 选了「自定义」但还没填日期时 cur === ":"，要能显示成两个空输入框
      const custom = iso !== null;

      return (
        <div className="flex w-full items-center gap-1">
          <Select
            id={id}
            aria-label={labelOf(p)}
            value={isPreset ? cur : custom ? "__custom__" : "1y"}
            onChange={(e) => {
              if (e.target.value === "__custom__") {
                // 切到自定义时给一个「今天往前一年」的初值 —— 空输入框会让人
                // 不知道格式，也容易提交出 ":" 这种半成品。
                const end = new Date();
                const start = new Date(end);
                start.setFullYear(start.getFullYear() - 1);
                onChange(`${ymd(start)}${RANGE_SEP}${ymd(end)}`);
              } else {
                onChange(e.target.value);
              }
            }}
            className="w-[84px] shrink-0"
          >
            {DATE_RANGE_PRESETS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
            <option value="__custom__">自定义</option>
          </Select>

          {custom && (
            <>
              <input
                type="date"
                aria-label={`${labelOf(p)} 起`}
                value={iso?.start ?? ""}
                onChange={(e) => onChange(`${e.target.value}${RANGE_SEP}${iso?.end ?? ""}`)}
                className="h-7 min-w-0 flex-1 rounded-[4px] border border-border bg-[hsl(var(--card))] px-1 text-[11px] text-foreground outline-none focus:border-[hsl(var(--primary))]"
                style={{ fontVariantNumeric: "tabular-nums" }}
              />
              <span className="text-[11px] text-muted-foreground">~</span>
              <input
                type="date"
                aria-label={`${labelOf(p)} 止`}
                value={iso?.end ?? ""}
                onChange={(e) => onChange(`${iso?.start ?? ""}${RANGE_SEP}${e.target.value}`)}
                className="h-7 min-w-0 flex-1 rounded-[4px] border border-border bg-[hsl(var(--card))] px-1 text-[11px] text-foreground outline-none focus:border-[hsl(var(--primary))]"
                style={{ fontVariantNumeric: "tabular-nums" }}
              />
            </>
          )}
        </div>
      );
    }

    case "symbol_list": {
      const arr = Array.isArray(value) ? (value as string[]) : [];
      return (
        <TextInput
          id={id}
          aria-label={labelOf(p)}
          value={arr.join(", ")}
          placeholder="600519, 000858"
          onChange={(e) => {
            const codes = e.target.value
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean);
            onChange(codes);
          }}
          style={{ fontFamily: "var(--font-mono, monospace)" }}
        />
      );
    }

    default:
      // str 及未来新增的标量类型
      return (
        <TextInput
          id={id}
          aria-label={labelOf(p)}
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
        />
      );
  }
}

export function ParamBar({ params, values, onChange }: Props) {
  if (params.length === 0) return null;

  return (
    <div className="mb-3 flex flex-wrap items-end gap-3 rounded-[6px] border border-border bg-card px-3 py-2">
      {params.map((p) => {
        const wide = p.type === "date_range" && parseIsoRange(values[p.name]) !== null;
        return (
        <label key={p.name} htmlFor={`param-${p.name}`} className="flex flex-col gap-1">
          <span className="text-[11px] text-muted-foreground">{labelOf(p)}</span>
          {/* 宽度按控件类型给：自定义日期区间要放两个 date input + 分隔符，
              120px 会把年份截成「30/2024」看不出年份（实测截图发现）。 */}
          <span className={cn("block", wide ? "w-[320px]" : "w-[120px]")}>
            <Control p={p} value={values[p.name]} onChange={(v) => onChange(p.name, v)} />
          </span>
        </label>
        );
      })}
    </div>
  );
}
