import { useState } from "react";
import { FileText, Trash2, Loader2, FolderOpen, Plus } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { AskAiButton } from "@/components/ui/AskAiButton";
import { useCachedResource, dropCache } from "@/lib/cache";
import { listReports, addReport, deleteReport, type ResearchReport } from "@/lib/research";
import { ApiError } from "@/lib/api";

// 我的研报 —— 归档文本研报/结论到后端 doc 表（复用 /api/reports）。
// 注：AlphaCopilot 后端研报库存标题 + 正文文本（不做文件上传/正文提取，那是另一条能力）；
// 这里如实呈现「标题 + 正文」的录入/列表/删除。缓存切页不重取，改动后 dropCache 重取。AI 占位(S5)。

const fmtDate = (ts: number) =>
  new Date(ts * 1000).toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });

export function MyReports() {
  const list = useCachedResource<ResearchReport[]>("reports:list", () => listReports());
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const reports = list.data ?? [];

  const reload = () => { dropCache("reports:list"); list.refresh(); };

  const add = async () => {
    if (!title.trim()) { setErr("标题不能为空"); return; }
    setBusy(true); setErr(null);
    try {
      await addReport(title.trim(), text);
      setTitle(""); setText("");
      reload();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "归档失败");
    } finally { setBusy(false); }
  };

  const remove = async (r: ResearchReport) => {
    if (!confirm(`删除「${r.title}」？`)) return;
    try {
      await deleteReport(r.id);
      reload();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "删除失败"); }
  };

  return (
    <div>
      <PageHeader
        title="我的研报"
        subtitle="归档研报结论与要点到本地研报库；后续可被 Agent 检索引用（S5）"
        actions={<AskAiButton context="研报库检索" label="问 AI" />}
      />

      {/* 录入 */}
      <GlassCard className="mb-4">
        <h3 className="mb-3 text-sm font-semibold">归档一份研报</h3>
        <div className="space-y-2">
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="标题，如 白酒行业 2025 年报对比"
            className="w-full rounded-lg border border-border bg-black/20 px-3 py-2 text-sm outline-none focus:border-primary/50" />
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} placeholder="正文 / 结论要点（可选）"
            className="w-full resize-y rounded-lg border border-border bg-black/20 px-3 py-2 text-sm outline-none focus:border-primary/50" />
          <button onClick={add} disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary/15 px-4 py-2 text-sm font-medium text-primary shadow-glow hover:bg-primary/25 disabled:opacity-50">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} 归档
          </button>
        </div>
      </GlassCard>

      {err && <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{err}</div>}

      {/* 列表 */}
      {list.loading && reports.length === 0 ? (
        <GlassCard><p className="py-8 text-center text-sm text-muted-foreground/60">加载中…</p></GlassCard>
      ) : reports.length === 0 ? (
        <GlassCard>
          <div className="flex flex-col items-center gap-2 py-10 text-center text-sm text-muted-foreground">
            <FolderOpen className="h-8 w-8 text-muted-foreground/40" />
            还没有归档的研报。用上面的表单记一份结论或要点。
          </div>
        </GlassCard>
      ) : (
        <GlassCard glow>
          <div className="divide-y divide-border/30">
            {reports.map((r) => (
              <div key={r.id} className="flex items-center gap-3 py-2.5">
                <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{r.title}</p>
                  <p className="text-[11px] text-muted-foreground/60">{r.source_path} · {fmtDate(r.created_at)}</p>
                </div>
                <button onClick={() => remove(r)} className="shrink-0 text-muted-foreground/50 hover:text-destructive" title="删除">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        </GlassCard>
      )}

      <Disclaimer />
    </div>
  );
}
