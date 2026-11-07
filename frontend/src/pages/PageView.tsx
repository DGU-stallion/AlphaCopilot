/**
 * 通用页面视图（ADR-0016 决定 2/3）：`/p/:slug` 按 spec 渲染。
 *
 * 这一条路由是 ADR-0016 的核心 —— 它让「页面」第一次真的成为数据。
 * 在此之前所有页面都是手写 TSX 挂在 router 里，所以 agent 产出的 spec
 * 无处可去（Build 死于这一点，见 ROUND2-BRIEF §1.2）。
 *
 * 数据流：
 *   GET /api/pages/{slug}      → spec（含 params / blocks）
 *   POST /api/pages/{slug}/render + values → 各 block 的渲染载荷
 *   渲染：ParamBar（参数）→ PageCanvas（块）
 */
import { useCallback, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Form";
import { ParamBar } from "@/components/page/ParamBar";
import { PageCanvas } from "@/components/page/PageCanvas";
import { TTL, useCachedResource } from "@/lib/cache";
import { useDataAsOfAuto } from "@/lib/data-asof";
import { renderPage, type RenderResult } from "@/lib/research";
import { defaultValues, type PageRecord } from "@/lib/page-spec";
import { apiUrl } from "@/lib/base";
import { authHeaders } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * 取 spec。`renderPage` 在 research.ts 里只做 POST render，
 * GET spec 需要单独一个请求，所以这里自己写（保持 research.ts 的职责不扩大）。
 */
async function fetchPage(slug: string): Promise<PageRecord> {
  const resp = await fetch(apiUrl(`/api/pages/${encodeURIComponent(slug)}`), {
    headers: { ...authHeaders() },
  });
  if (!resp.ok) {
    throw new Error(resp.status === 404 ? `页面不存在：${slug}` : `HTTP ${resp.status}`);
  }
  return (await resp.json()) as PageRecord;
}

/**
 * 渲染器缓存键。
 *
 * **为什么不能只用 slug 做 key**：同一个页面不同参数要分别缓存；
 * 只用 slug 会在改参数后仍显示旧图（用户会以为参数没生效）。
 * 参数的插入顺序不稳定（对象字面量），所以排序后再序列化 ——
 * 否则 {a,b} 与 {b,a} 会算出两个不同的 key，缓存命中率无故减半。
 */
export function renderCacheKey(slug: string, values: Record<string, unknown>): string {
  const stable = Object.keys(values)
    .sort()
    .map((k) => `${k}=${JSON.stringify(values[k])}`)
    .join("&");
  return `page:${slug}:${stable}`;
}

export function PageView() {
  const { slug = "" } = useParams();

  const rec = useCachedResource<PageRecord>(
    `page-spec:${slug}`,
    () => fetchPage(slug),
    // spec 只在改页面时才变 → 用归档档，不用行情档。
    { ttlMs: TTL.ARCHIVE },
  );

  const spec = rec.data?.spec ?? null;
  const defaults = useMemo(() => defaultValues(spec), [spec]);
  const [overrides, setOverrides] = useState<Record<string, unknown>>({});
  const values = useMemo(() => ({ ...defaults, ...overrides }), [defaults, overrides]);

  const key = renderCacheKey(slug, values);
  const res = useCachedResource<RenderResult>(
    key,
    () => renderPage(slug, values),
    // 回测/相关性这类计算实测 5–8 秒 → COMPUTE 档（30 分钟）。
    // key 里带了全部参数，参数一改就换 key，不会串数据；跨日照样强制失效。
    { ttlMs: TTL.COMPUTE },
  );

  useDataAsOfAuto(
    rec.data ? { dataAsOf: "", label: spec?.title ?? rec.data.title } : null,
  );

  const setParam = useCallback((name: string, v: unknown) => {
    setOverrides((cur) => ({ ...cur, [name]: v }));
  }, []);

  const reset = useCallback(() => {
    setOverrides({});
    rec.refresh();
  }, [rec]);

  // ---------- 加载 / 出错 ----------
  if (rec.loading && !rec.data) {
    return (
      <div>
        <PageHeader title={slug} subtitle="加载中…" />
        <div className="space-y-3">
          <div className="h-9 animate-pulse rounded-[6px] border border-border bg-card" />
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
            <div className="col-span-2 h-[240px] animate-pulse rounded-[6px] border border-border bg-card" />
            <div className="h-[240px] animate-pulse rounded-[6px] border border-border bg-card" />
          </div>
        </div>
      </div>
    );
  }

  if (rec.error || !spec) {
    return (
      <div>
        <PageHeader title={slug} subtitle="这个页面不存在或暂时读不到" />
        <p className="py-16 text-center text-[12px] text-muted-foreground">
          {rec.error ? String((rec.error as Error).message || rec.error) : "页面不存在"}
        </p>
      </div>
    );
  }

  const blocks = res.data?.blocks ?? [];
  const renderErr = res.error ? String((res.error as Error).message || res.error) : null;

  return (
    <div>
      <PageHeader
        title={spec.title}
        subtitle={`由页面描述渲染${spec.kind === "builtin" ? "（内置）" : "（自定义）"}`}
        actions={
          <Button variant="ghost" onClick={reset}>
            <RefreshCw className={cn("h-3.5 w-3.5", res.loading && "animate-spin")} /> 重新计算
          </Button>
        }
      />

      <ParamBar params={spec.params ?? []} values={values} onChange={setParam} />

      {renderErr ? (
        <p className="py-16 text-center text-[12px] text-danger">计算失败：{renderErr}</p>
      ) : res.loading && blocks.length === 0 ? (
        // 加载骨架：A4 的病根之一是「无缓存时白屏看着像卡死」。
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          <div className="col-span-3 h-[120px] animate-pulse rounded-[6px] border border-border bg-card" />
          <div className="col-span-2 h-[240px] animate-pulse rounded-[6px] border border-border bg-card" />
          <div className="h-[240px] animate-pulse rounded-[6px] border border-border bg-card" />
        </div>
      ) : (
        <PageCanvas blocks={blocks} />
      )}
    </div>
  );
}
