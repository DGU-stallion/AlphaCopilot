/**
 * 我的研报 —— 归档库（ROUND3 B4）。
 *
 * 从「一个能粘文本的输入框」改成归档库：收 PDF / Markdown / 图片，按 `kind`
 * 选预览器，删除走软删 + 撤销条。
 *
 * 三条设计决定写在这里，因为它们都不是显然的：
 *
 *  1. **预览器按后端给的 `kind` 分派，不按扩展名猜**（`api.ts:DocKind`）。
 *     扩展名是用户能随便改的东西；`kind` 是后端嗅探字节后盖章的结论。
 *     猜错的后果是点 PDF 得到一张碎图 / 点图片得到乱码。
 *  2. **删除不用 `window.confirm`**：研报是手写的、不可再生（AGENTS 硬规则 14）。
 *     确认弹窗能防手滑，防不了「确认完才发现想错了」，所以只做软删 + 撤销条。
 *  3. **正文按需拉**（`reportsApi.detail`）：列表接口刻意不回 `text`，
 *     一份 PDF 的 Markdown 笔记可能几百 KB，列表不需要。
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  FileImage,
  FileText,
  FileType2,
  Loader2,
  Search,
  StickyNote,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button, Field, TextArea, TextInput } from "@/components/ui/Form";
import { Panel } from "@/components/ui/Panel";
import { Num } from "@/components/Num";
import { useAiPage } from "@/lib/ai-page";
import { reportsApi, type DocKind, type DocRow } from "@/lib/api";

const KIND_LABEL: Record<DocKind, string> = {
  pdf: "PDF",
  markdown: "Markdown",
  image: "图片",
  note: "笔记",
};

const KIND_ICON: Record<DocKind, typeof FileText> = {
  pdf: FileText,
  markdown: FileType2,
  image: FileImage,
  note: StickyNote,
};

/** 上传控件接受的扩展名。真正的白名单在后端（这里只是让文件选择框好用一点）。 */
const ACCEPT = ".pdf,.md,.markdown,.png,.jpg,.jpeg,.webp,.gif";

const fmtDate = (ts: number) =>
  new Date(ts * 1000).toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });

/** 标签是逗号分隔的自由文本（后端一个 `tags` 列，不做规范化）。 */
const splitTags = (tags: string): string[] =>
  tags.split(/[,，;；/\s]+/).map((t) => t.trim()).filter(Boolean);

const isTextKind = (kind: DocKind) => kind === "markdown" || kind === "note";

export function MyReports() {
  const [docs, setDocs] = useState<DocRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);

  const [q, setQ] = useState("");
  const [activeTag, setActiveTag] = useState("");

  const [selected, setSelected] = useState<string | null>(null);
  const [body, setBody] = useState<{ id: string; text: string } | null>(null);

  const [noteTitle, setNoteTitle] = useState("");
  const [noteText, setNoteText] = useState("");
  const [noteTags, setNoteTags] = useState("");

  /** 撤销条。只记最近一次删除 —— 连续删两条时，第一条仍可用「恢复」找回（软删）。 */
  const [undo, setUndo] = useState<{ id: string; title: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setDocs(await reportsApi.list());
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "加载归档失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // 本页给 AI 的确定性快照：只有元信息（标题/形态/时间），不塞正文。
  const aiKey = `${docs.length}:${docs[0]?.id ?? ""}`;
  useAiPage(
    useMemo(
      () => ({
        key: `reports:${aiKey}`,
        title: "我的研报",
        context:
          loading && docs.length === 0
            ? "研报归档加载中…"
            : docs.length === 0
              ? "归档库还是空的"
              : `已归档 ${docs.length} 份：\n` +
                docs
                  .slice(0, 8)
                  .map((d) => `· ${d.title}（${KIND_LABEL[d.kind]}，${fmtDate(d.created_at)}）`)
                  .join("\n") +
                (docs.length > 8 ? `\n…等共 ${docs.length} 份（仅列前 8 条，正文未附）` : ""),
        suggestions: ["我归档过哪些研报", "帮我从归档里找白酒相关的", "这些研报能支撑什么结论"],
      }),
      [aiKey, loading, docs],
    ),
  );

  const allTags = useMemo(() => {
    const set = new Set<string>();
    for (const d of docs) for (const t of splitTags(d.tags)) set.add(t);
    return [...set].sort((a, b) => a.localeCompare(b, "zh-CN"));
  }, [docs]);

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return docs.filter((d) => {
      if (activeTag && !splitTags(d.tags).includes(activeTag)) return false;
      if (!needle) return true;
      return [d.title, d.source_path, d.tags].join(" ").toLowerCase().includes(needle);
    });
  }, [docs, q, activeTag]);

  const selectedDoc = docs.find((d) => d.id === selected) ?? null;

  const openDoc = (d: DocRow) => {
    setSelected(d.id);
    setBody(null);
    if (!isTextKind(d.kind)) return; // 图片/PDF 由 <img>/<iframe> 自己取字节
    reportsApi
      .detail(d.id)
      .then((full) => setBody({ id: d.id, text: full.text ?? "" }))
      .catch((e) => setErr(e instanceof Error ? e.message : "读取正文失败"));
  };

  const upload = async (files: FileList | File[] | null | undefined) => {
    const list = Array.from(files ?? []);
    if (list.length === 0) return;
    setBusy(true);
    setErr(null);
    try {
      // 逐个上传：一个失败不该把同批其余的都丢掉（错误提示里能看出是哪个）。
      for (const f of list) {
        await reportsApi.upload(f, activeTag ? { tags: activeTag } : {});
      }
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "上传失败");
    } finally {
      setBusy(false);
    }
  };

  const addNote = async () => {
    if (!noteTitle.trim()) {
      setErr("笔记标题不能为空");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await reportsApi.createNote({
        title: noteTitle.trim(),
        text: noteText,
        tags: noteTags.trim() || undefined,
      });
      setNoteTitle("");
      setNoteText("");
      setNoteTags("");
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "保存笔记失败");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (d: DocRow) => {
    try {
      await reportsApi.remove(d.id);
      setDocs((prev) => prev.filter((x) => x.id !== d.id));
      if (selected === d.id) setSelected(null);
      setUndo({ id: d.id, title: d.title });
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "删除失败");
    }
  };

  const undoRemove = async () => {
    if (!undo) return;
    try {
      await reportsApi.restore(undo.id);
      setUndo(null);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "撤销失败");
    }
  };

  return (
    <div>
      <PageHeader
        title="我的研报"
        subtitle="归档 PDF / Markdown / 图片与手写笔记；一条条留在本地，可被 agent 检索引用"
      />

      {/* ---------------- 上传 ---------------- */}
      <Panel className="mb-3">
        <div
          data-testid="doc-dropzone"
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            void upload(e.dataTransfer?.files);
          }}
          className={
            "flex flex-col items-center gap-1.5 rounded-[4px] border border-dashed py-5 text-center transition-colors " +
            (dragging ? "border-[hsl(var(--primary))] bg-[hsl(var(--muted))]" : "border-border")
          }
        >
          <Upload className="h-5 w-5 text-muted-foreground/60" />
          <p className="text-[13px] text-foreground">把文件拖到这里，或</p>
          <label className="cursor-pointer rounded-[4px] border border-border px-2.5 py-1 text-[12px] text-primary hover:bg-[hsl(var(--muted))]">
            选择文件
            <input
              data-testid="doc-file-input"
              type="file"
              multiple
              accept={ACCEPT}
              className="hidden"
              onChange={(e) => {
                void upload(e.target.files);
                // 清空 value：否则同一个文件连传两次，第二次不触发 onChange
                e.target.value = "";
              }}
            />
          </label>
          <p className="text-[11px] text-muted-foreground/60">
            只接受 PDF / Markdown / 图片，单份 ≤ 20MB
          </p>
          {busy && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
        </div>
      </Panel>

      {/* ---------------- 手写笔记 ---------------- */}
      <Panel className="mb-3">
        <h3 className="mb-2 text-sm font-semibold">记一条笔记</h3>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
          <Field label="标题">
            <TextInput
              aria-label="笔记标题"
              value={noteTitle}
              onChange={(e) => setNoteTitle(e.target.value)}
              placeholder="如 白酒 2025 年报对比的结论"
            />
          </Field>
          <Field label="标签" hint="逗号分隔，用于筛选">
            <TextInput
              aria-label="笔记标签"
              value={noteTags}
              onChange={(e) => setNoteTags(e.target.value)}
              placeholder="白酒,周报"
            />
          </Field>
        </div>
        <div className="mt-2">
          <Field label="正文">
            <TextArea
              aria-label="笔记正文"
              rows={3}
              value={noteText}
              onChange={(e) => setNoteText(e.target.value)}
              placeholder="结论、关键数据、当时的前提 —— 半年后回看才有用"
            />
          </Field>
        </div>
        <div className="mt-2">
          <Button onClick={() => void addNote()} disabled={busy}>
            存为笔记
          </Button>
        </div>
      </Panel>

      {err && (
        <div className="mb-3 rounded-[4px] border border-[hsl(var(--danger))]/30 bg-[hsl(var(--danger))]/5 p-2.5 text-sm text-danger">
          {err}
        </div>
      )}

      {/* ---------------- 筛选 ---------------- */}
      <Panel className="mb-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[180px] flex-1">
            <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground/50" />
            <TextInput
              aria-label="搜索归档"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="搜索标题 / 文件名 / 标签"
              className="pl-7"
            />
          </div>
          {allTags.length > 0 && (
            <div className="flex flex-wrap items-center gap-1">
              {allTags.map((t) => (
                <button
                  key={t}
                  onClick={() => setActiveTag(activeTag === t ? "" : t)}
                  aria-pressed={activeTag === t}
                  className={
                    "rounded-[3px] border px-1.5 py-0.5 text-[11px] transition-colors " +
                    (activeTag === t
                      ? "border-[hsl(var(--primary))] text-primary"
                      : "border-border text-muted-foreground hover:text-foreground")
                  }
                >
                  {t}
                </button>
              ))}
            </div>
          )}
          <span className="text-[11px] text-muted-foreground/60">
            <Num v={shown.length} digits={0} /> / <Num v={docs.length} digits={0} /> 份
          </span>
        </div>
      </Panel>

      {/* ---------------- 预览（按 kind 分派）---------------- */}
      {selectedDoc && (
        <Panel className="mb-3">
          <div className="mb-2 flex items-baseline justify-between gap-2">
            <div className="min-w-0">
              <h3 className="truncate text-sm font-semibold">{selectedDoc.title}</h3>
              <p className="text-[11px] text-muted-foreground/60">
                {KIND_LABEL[selectedDoc.kind]}
                {selectedDoc.bytes > 0 && (
                  <>
                    {" · "}
                    <Num v={selectedDoc.bytes / 1024} digits={0} unit=" KB" />
                  </>
                )}
                {" · "}
                {fmtDate(selectedDoc.created_at)}
              </p>
            </div>
            <button
              onClick={() => setSelected(null)}
              aria-label="关闭预览"
              className="shrink-0 text-muted-foreground/60 hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          {selectedDoc.kind === "image" && (
            <img
              data-testid="preview-image"
              src={reportsApi.fileUrl(selectedDoc.id)}
              alt={selectedDoc.title}
              className="max-h-[440px] w-auto rounded-[4px] border border-border"
            />
          )}

          {selectedDoc.kind === "pdf" && (
            <iframe
              data-testid="preview-pdf"
              title={selectedDoc.title}
              src={reportsApi.fileUrl(selectedDoc.id)}
              className="h-[480px] w-full rounded-[4px] border border-border bg-[hsl(var(--card))]"
            />
          )}

          {isTextKind(selectedDoc.kind) && (
            <div data-testid="preview-text" className="max-h-[480px] overflow-auto">
              {body?.id === selectedDoc.id ? (
                selectedDoc.kind === "markdown" ? (
                  <div className="space-y-2 text-[13px] leading-relaxed">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{body.text}</ReactMarkdown>
                  </div>
                ) : (
                  <p className="whitespace-pre-wrap text-[13px] leading-relaxed">{body.text}</p>
                )
              ) : (
                <p className="py-6 text-center text-[12px] text-muted-foreground/60">读取正文…</p>
              )}
            </div>
          )}
        </Panel>
      )}

      {/* ---------------- 列表 ---------------- */}
      {loading && docs.length === 0 ? (
        <Panel>
          <p className="py-8 text-center text-sm text-muted-foreground/60">加载中…</p>
        </Panel>
      ) : shown.length === 0 ? (
        <Panel>
          <p className="py-8 text-center text-sm text-muted-foreground">
            {docs.length === 0 ? "归档库还是空的。上传一个 PDF 或记一条笔记开始。" : "没有匹配的归档。"}
          </p>
        </Panel>
      ) : (
        <Panel>
          <div className="divide-y divide-border/30">
            {shown.map((d) => {
              const Icon = KIND_ICON[d.kind];
              return (
                <div
                  key={d.id}
                  data-testid="doc-row"
                  data-kind={d.kind}
                  className="flex items-center gap-2.5 py-2"
                >
                  <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <button
                    onClick={() => openDoc(d)}
                    className="min-w-0 flex-1 text-left"
                    title="点击预览"
                  >
                    <p className="truncate text-[13px] font-medium">{d.title}</p>
                    <p className="truncate text-[11px] text-muted-foreground/60">
                      {KIND_LABEL[d.kind]}
                      {d.bytes > 0 && (
                        <>
                          {" · "}
                          <Num v={d.bytes / 1024} digits={0} unit=" KB" />
                        </>
                      )}
                      {" · "}
                      {fmtDate(d.created_at)}
                      {d.tags ? ` · ${d.tags}` : ""}
                    </p>
                  </button>
                  <button
                    onClick={() => void remove(d)}
                    aria-label={`删除 ${d.title}`}
                    className="shrink-0 text-muted-foreground/50 hover:text-destructive"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              );
            })}
          </div>
        </Panel>
      )}

      {/* ---------------- 撤销条 ---------------- */}
      {undo && (
        <div
          role="status"
          className="fixed bottom-10 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-[4px] border border-border bg-[hsl(var(--card))] px-3 py-2 text-[12px]"
        >
          <span className="text-muted-foreground">已删除「{undo.title}」</span>
          <button
            onClick={() => void undoRemove()}
            className="font-medium text-primary hover:underline"
          >
            撤销
          </button>
          <button
            onClick={() => setUndo(null)}
            aria-label="关闭提示"
            className="text-muted-foreground/60 hover:text-foreground"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      )}
    </div>
  );
}
