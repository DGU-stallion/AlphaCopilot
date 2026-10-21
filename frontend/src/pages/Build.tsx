import { useState } from "react";
import { Check, FileCode2, X } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { Button, TextArea, Field } from "@/components/ui/Form";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { EChart } from "@/components/ui/EChart";
import { PriceChart } from "@/components/charts/PriceChart";
import { runsApi } from "@/lib/api";
import { rendererOf, renderPage, type RenderBlock } from "@/lib/research";
import { useAiPage } from "@/lib/ai-page";
import { cn } from "@/lib/utils";

/**
 * Build 模式（M5-2）：把一段 page spec 粘进来 → 校验 → 预览 → 确认发布。
 *
 * ## 为什么这个页面是「确认环节」而不是「生成环节」
 *
 * agent 在当前架构里已经能写文件、能调工具，它生成 spec 不需要一个专门的页面。
 * 真正缺的是**确认环节**：agent 写出来的东西长什么样？会不会白屏？
 * 发出去之后能不能收回来？
 *
 * 所以这一页的职责是：
 *   1. 粘 spec（agent 的输出，或自己写的）
 *   2. **用真实渲染路径预览**（不是另一套简化渲染 —— 那样预览会骗人）
 *   3. 只有校验通过才能发布；发布后能撤回
 *
 * ## 一个刻意的限制
 *
 * 发布是**用户动作**。agent 能产 draft，但它的权限边界到此为止。
 * 如果让 agent 自己发布，page_spec 的全部白名单校验就形同虚设 ——
 * 那套校验存在的全部意义就是「未经审阅的结构不进产品页面」。
 */

const EXAMPLE_SPEC = `{
  "slug": "my-view",
  "title": "我的视图",
  "kind": "user",
  "status": "draft",
  "layout": "grid",
  "params": [],
  "blocks": [
    { "kind": "chart", "span": 2, "renderer": "lwc",
      "analysis_ref": { "fn": "backtest.equity" } }
  ]
}`;

export function Build() {
  const [raw, setRaw] = useState(EXAMPLE_SPEC);
  const [spec, setSpec] = useState<Record<string, unknown> | null>(null);
  const [draftId, setDraftId] = useState<string | null>(null);
  const [blocks, setBlocks] = useState<RenderBlock[]>([]);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useAiPage({
    key: "build",
    title: "Build 模式",
    context: spec
      ? `正在预览一个 page spec：slug=${String(spec.slug)} title=${String(spec.title)}，` +
        `含 ${Array.isArray(spec.blocks) ? spec.blocks.length : 0} 个 block。` +
        `当前状态：${draftId ? "已存为草稿" : "尚未落地"}。`
      : "还没有粘入 spec",
    suggestions: ["帮我写一个看相关性矩阵的 spec", "这个 spec 有什么问题", "哪些 analysis fn 可以用"],
  });

  /** 校验 + 预览。用真实的 render 端点 —— 预览与上线是同一套渲染。 */
  const preview = async () => {
    setMsg(null);
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(raw);
    } catch (e) {
      setMsg({ ok: false, text: `JSON 解析失败：${e instanceof Error ? e.message : e}` });
      return;
    }
    setBusy(true);
    try {
      // 存草稿 = 走完整校验（schema + fn 白名单 + renderer 一致性 + slug 冲突）
      const d = await runsApi.createDraft(parsed);
      setDraftId(d.id);
      setSpec(parsed);
      // 再用真实渲染路径算一遍，看它到底长什么样
      const rendered = await renderPage(String(parsed.slug), {});
      setBlocks(rendered.blocks);
      setMsg({ ok: true, text: `校验通过，已存为草稿（${String(parsed.slug)}）。下面是真实渲染效果。` });
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "校验失败" });
      setSpec(null); setBlocks([]); setDraftId(null);
    } finally { setBusy(false); }
  };

  const publish = async () => {
    if (!draftId) return;
    setBusy(true);
    try {
      await runsApi.publishPage(draftId);
      setMsg({ ok: true, text: "已发布。如果发现问题，点「撤回」就能改回来。" });
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "发布失败" });
    } finally { setBusy(false); }
  };

  const unpublish = async () => {
    if (!draftId) return;
    setBusy(true);
    try {
      await runsApi.unpublishPage(draftId);
      setMsg({ ok: true, text: "已撤回为草稿。" });
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "撤回失败" });
    } finally { setBusy(false); }
  };

  return (
    <div>
      <PageHeader
        title="Build 模式"
        subtitle="粘入 page spec → 校验 → 用真实渲染路径预览 → 确认发布。发布可撤回。"
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel className="flex flex-col">
          <h3 className="mb-2 flex items-center gap-1.5 text-[13px] font-semibold">
            <FileCode2 className="h-3.5 w-3.5 text-[hsl(var(--primary))]" /> page spec
          </h3>
          <Field label="JSON" hint="agent 的输出可以直接粘进来">
            <TextArea
              value={raw}
              onChange={(e) => setRaw(e.target.value)}
              rows={22}
              spellCheck={false}
              className="font-mono text-[12px]"
            />
          </Field>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button onClick={() => void preview()} disabled={busy}>
              {busy ? "校验中…" : "校验并预览"}
            </Button>
            {draftId && (
              <>
                <Button variant="ghost" onClick={() => void publish()} disabled={busy}>
                  <Check className="h-3.5 w-3.5" /> 发布
                </Button>
                <Button variant="ghost" onClick={() => void unpublish()} disabled={busy}>
                  <X className="h-3.5 w-3.5" /> 撤回
                </Button>
              </>
            )}
          </div>
          {msg && (
            <p className={cn(
              "mt-2 rounded-[4px] border px-2 py-1.5 text-[12px]",
              msg.ok
                ? "border-[hsl(var(--success))]/40 text-[hsl(var(--success))]"
                : "border-[hsl(var(--danger))]/40 text-danger",
            )}>
              {msg.text}
            </p>
          )}
        </Panel>

        <Panel>
          <h3 className="mb-2 text-[13px] font-semibold">
            预览{spec ? `：${String(spec.title)}` : ""}
          </h3>
          {!spec ? (
            <p className="py-16 text-center text-[12px] text-muted-foreground/60">
              校验通过后这里显示真实渲染结果（与上线后完全一致，不是另一套简化渲染）。
            </p>
          ) : blocks.length === 0 ? (
            <p className="py-16 text-center text-[12px] text-muted-foreground/60">
              这个 spec 没有可渲染的 block。
            </p>
          ) : (
            <div className="space-y-3">
              {blocks.map((b, i) => (
                <PreviewBlock key={i} block={b} />
              ))}
            </div>
          )}
        </Panel>
      </div>

      <Disclaimer />
    </div>
  );
}

function PreviewBlock({ block }: { block: RenderBlock }) {
  if (block.kind === "markdown") {
    return (
      <div className="rounded-[4px] border border-border p-2 text-[13px] leading-relaxed">
        {block.text || "（空）"}
      </div>
    );
  }
  if (block.kind === "metric" && block.metric) {
    return (
      <div className="flex flex-wrap gap-3">
        {block.metric.items.map((it) => (
          <div key={it.label} className="rounded-[4px] border border-border px-3 py-1.5">
            <p className="text-[10px] text-muted-foreground">{it.label}</p>
            <p className="font-mono text-[15px]">{String(it.value)}</p>
          </div>
        ))}
      </div>
    );
  }
  if (block.kind === "chart") {
    if (rendererOf(block) === "lwc") {
      const series = block.lwc?.series?.[0]?.points ?? [];
      const bars = series.map((p) => ({
        datetime: p.time, open: p.value, close: p.value, high: p.value, low: p.value, vol: 0,
      }));
      return bars.length
        ? <div className="h-[240px]"><PriceChart bars={bars} mode="line" /></div>
        : <p className="py-6 text-center text-[12px] text-muted-foreground/60">无可绘制数据</p>;
    }
    return <EChart option={block.option ?? null} height={240} />;
  }
  return (
    <p className="rounded-[4px] border border-border p-2 text-[12px] text-muted-foreground">
      {block.kind}（预览暂不支持此类型）
    </p>
  );
}
