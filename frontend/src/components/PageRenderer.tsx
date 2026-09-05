/**
 * PageRenderer — 通用展示页渲染器（ADR-0007：页面数据驱动，AGENTS 硬规则 6）。
 *
 * slug → GET /api/pages/{slug} 拿 spec → 据 spec.params 自动生成控件 → 用 default 初值 →
 * on_open 自动 render 一次 → 改参或点“刷新/计算” POST /{slug}/render → 按 span 网格渲染 blocks。
 * 复用现有 ChartBlock/MarkdownBlock，不改其内部。
 */

import { useCallback, useEffect, useState } from "react";
import { ChartBlock } from "@/components/blocks/ChartBlock";
import { MarkdownBlock } from "@/components/blocks/MarkdownBlock";
import {
  getPage,
  renderPage,
  type PageBlock,
  type PageParam,
  type PageSpec,
} from "@/lib/api";

const DATE_RANGE_CHOICES = ["1y", "6m", "3m"];

type ParamValues = Record<string, unknown>;

function initialValues(params: PageParam[]): ParamValues {
  const v: ParamValues = {};
  for (const p of params) {
    if (p.default !== undefined) v[p.name] = p.default;
    else if (p.type === "symbol_list") v[p.name] = [];
    else if (p.type === "int" || p.type === "float") v[p.name] = p.min ?? 0;
    else if (p.type === "date_range") v[p.name] = DATE_RANGE_CHOICES[0];
    else if (p.type === "enum") v[p.name] = p.choices?.[0] ?? "";
    else v[p.name] = "";
  }
  return v;
}

function ParamControl({
  param,
  value,
  onChange,
}: {
  param: PageParam;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const id = `param-${param.name}`;
  const label = (
    <label htmlFor={id} className="mb-1 block text-xs text-muted-foreground">
      {param.label}
    </label>
  );

  switch (param.type) {
    case "symbol_list": {
      // 多值输入：逗号分隔 → 字符串数组；标签展示当前值。
      const list = Array.isArray(value) ? (value as string[]) : [];
      return (
        <div>
          {label}
          <input
            id={id}
            type="text"
            className="glass w-full rounded-md px-2 py-1 text-sm text-foreground"
            value={list.join(",")}
            onChange={(e) =>
              onChange(
                e.target.value
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
              )
            }
          />
          <div className="mt-1 flex flex-wrap gap-1">
            {list.map((s) => (
              <span key={s} className="rounded bg-primary/15 px-1.5 py-0.5 text-xs text-primary">
                {s}
              </span>
            ))}
          </div>
        </div>
      );
    }
    case "int":
    case "float":
      return (
        <div>
          {label}
          <input
            id={id}
            type="number"
            min={param.min}
            max={param.max}
            step={param.type === "int" ? 1 : "any"}
            className="glass w-full rounded-md px-2 py-1 text-sm text-foreground"
            value={value as number}
            onChange={(e) =>
              onChange(param.type === "int" ? Number(e.target.value) | 0 : Number(e.target.value))
            }
          />
        </div>
      );
    case "date_range":
      return (
        <div>
          {label}
          <select
            id={id}
            className="glass w-full rounded-md px-2 py-1 text-sm text-foreground"
            value={value as string}
            onChange={(e) => onChange(e.target.value)}
          >
            {DATE_RANGE_CHOICES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      );
    case "enum":
      return (
        <div>
          {label}
          <select
            id={id}
            className="glass w-full rounded-md px-2 py-1 text-sm text-foreground"
            value={value as string}
            onChange={(e) => onChange(e.target.value)}
          >
            {(param.choices ?? []).map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      );
    default:
      return (
        <div>
          {label}
          <input
            id={id}
            type="text"
            maxLength={param.max_len}
            className="glass w-full rounded-md px-2 py-1 text-sm text-foreground"
            value={value as string}
            onChange={(e) => onChange(e.target.value)}
          />
        </div>
      );
  }
}

function BlockGridItem({ block }: { block: PageBlock }) {
  const span = block.span ?? 12;
  const style = { gridColumn: `span ${Math.min(Math.max(span, 1), 12)}` };
  if (block.kind === "chart") {
    return (
      <div style={style}>
        <ChartBlock option={block.option ?? {}} />
      </div>
    );
  }
  if (block.kind === "markdown") {
    return (
      <div style={style}>
        <MarkdownBlock payload={{ text: block.text ?? "" }} />
      </div>
    );
  }
  return (
    <div style={style} className="glass rounded-lg p-3 text-sm text-muted-foreground">
      暂不支持的 block：{block.kind}
    </div>
  );
}

export function PageRenderer({ slug }: { slug: string }) {
  const [spec, setSpec] = useState<PageSpec | null>(null);
  const [values, setValues] = useState<ParamValues>({});
  const [blocks, setBlocks] = useState<PageBlock[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const doRender = useCallback(
    async (params: ParamValues) => {
      setLoading(true);
      setError(null);
      try {
        setBlocks(await renderPage(slug, params));
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    },
    [slug],
  );

  // slug 变更：拉 spec、置初值、首次自动 render 一次（on_open）。
  useEffect(() => {
    let alive = true;
    setSpec(null);
    setBlocks([]);
    getPage(slug)
      .then((s) => {
        if (!alive) return;
        const init = initialValues(s.params ?? []);
        setSpec(s);
        setValues(init);
        void doRender(init);
      })
      .catch((e) => alive && setError(String(e)));
    return () => {
      alive = false;
    };
  }, [slug, doRender]);

  if (!spec) {
    return (
      <div className="glass flex h-full items-center justify-center rounded-lg text-sm text-muted-foreground">
        {error ?? "加载中…"}
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col gap-3 overflow-auto p-1">
      <div className="glass flex flex-wrap items-end gap-3 rounded-lg p-3">
        <h2 className="w-full text-base font-semibold text-foreground">{spec.title}</h2>
        {(spec.params ?? []).map((p) => (
          <div key={p.name} className="min-w-40 flex-1">
            <ParamControl
              param={p}
              value={values[p.name]}
              onChange={(v) => setValues((prev) => ({ ...prev, [p.name]: v }))}
            />
          </div>
        ))}
        <button
          type="button"
          onClick={() => void doRender(values)}
          disabled={loading}
          className="glass rounded-md px-4 py-1.5 text-sm text-primary transition-colors hover:text-accent disabled:opacity-50"
        >
          {loading ? "计算中…" : "刷新"}
        </button>
      </div>

      {error && <div className="glass rounded-lg p-3 text-sm text-destructive">{error}</div>}

      <div className="grid grid-cols-12 gap-3" data-testid="block-grid">
        {blocks.map((b, i) => (
          <BlockGridItem key={i} block={b} />
        ))}
      </div>
    </div>
  );
}
