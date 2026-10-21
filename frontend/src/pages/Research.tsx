import { useState } from "react";
import { GitBranch, NotebookPen, Plus, RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { Num } from "@/components/Num";
import { Button, TextArea, TextInput, Field } from "@/components/ui/Form";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { useCachedResource } from "@/lib/cache";
import { useAiPage } from "@/lib/ai-page";
import { useDataAsOfAuto } from "@/lib/data-asof";
import { runsApi, type NoteRow, type NoteThread } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * 研究线（M5-3）：Note → Run → View → 复盘。
 *
 * 这一页要回答的问题只有一个：**半年前我为什么这么判断，后来对了吗。**
 *
 * 为什么这三件事必须在同一页：
 * 现在的状态是「笔记在研报页、回测在回测页、视图在 Run 页」——
 * 时间一长，你只记得「我好像研究过白酒」，但**想不起当时的理由**。
 * 把判断与它的证据放在一起，才能复盘「是我错了，还是运气不好」。
 *
 * 刻意不做的事：
 *   - 不做富文本编辑器（markdown 就够，重点是「当时的理由」不是排版）
 *   - 不强制每条回测都挂笔记（强制的结果是没人写笔记）
 *   - 不自动生成「AI 复盘」（那是替你下结论；这一页只呈现你当时写的和算的）
 */

function fmtTime(sec: number): string {
  const d = new Date(sec * 1000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function Research() {
  const notesRes = useCachedResource<NoteRow[]>("notes", () => runsApi.notes());
  const notes = notesRes.data ?? [];
  const [activeId, setActiveId] = useState<string | null>(null);
  const active = activeId ?? notes[0]?.id ?? null;

  const threadRes = useCachedResource<NoteThread | null>(
    active ? `thread:${active}` : "thread:none",
    () => (active ? runsApi.noteThread(active) : Promise.resolve(null)),
    { ttlMs: 5_000 },
  );
  const thread = threadRes.data;

  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useDataAsOfAuto(
    notes.length ? { dataAsOf: "", label: "研究笔记（本机 SQLite）" } : null,
  );

  useAiPage({
    key: "research",
    title: "研究线",
    context: thread
      ? `研究笔记「${thread.note.title}」（${fmtTime(thread.note.created_at)}）：\n` +
        `判断：${thread.note.text || "（未写正文）"}\n` +
        `关联 ${thread.runs.length} 次计算、${thread.views.length} 个视图。\n` +
        thread.runs.slice(0, 5).map((r) =>
          `  ${fmtTime(r.created_at)} ${r.kind} metrics=${JSON.stringify(r.metrics)}`).join("\n")
      : "还没有研究笔记",
    suggestions: ["帮我梳理当时的判断与结果哪里不一致", "这些计算能验证我的判断吗", "我该怎么复盘才对"],
  });

  const addNote = async () => {
    if (!title.trim()) { setMsg("请填标题 —— 半年后你靠它认出这条判断"); return; }
    setBusy(true);
    try {
      const r = await runsApi.createNote({ title: title.trim(), text });
      setTitle(""); setText(""); setMsg("已保存");
      notesRes.refresh();
      setActiveId(r.id);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "保存失败");
    } finally { setBusy(false); }
  };

  return (
    <div>
      <PageHeader
        title="研究线"
        subtitle="把当时的判断、算过的依据、看的角度串成一条线。半年后回看，才知道是自己错了还是运气不好。"
        actions={
          <Button variant="ghost" onClick={() => { notesRes.refresh(); threadRes.refresh(); }}>
            <RefreshCw className={cn("h-3.5 w-3.5", notesRes.loading && "animate-spin")} /> 刷新
          </Button>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[300px_1fr]">
        {/* 左：笔记列表 + 新建 */}
        <div className="space-y-4">
          <Panel>
            <h3 className="mb-2 flex items-center gap-1.5 text-[13px] font-semibold">
              <Plus className="h-3.5 w-3.5 text-[hsl(var(--primary))]" /> 新判断
            </h3>
            <div className="space-y-2">
              <Field label="标题">
                <TextInput
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="如 白酒估值到底部了吗"
                />
              </Field>
              <Field label="当时的理由" hint="写清前提 —— 半年后你会需要它">
                <TextArea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  rows={4}
                  placeholder="我看到什么、据此判断什么、什么情况下这个判断会错"
                />
              </Field>
              <Button onClick={() => void addNote()} disabled={busy}>保存</Button>
              {msg && <p className="text-[11px] text-muted-foreground">{msg}</p>}
            </div>
          </Panel>

          <Panel>
            <h3 className="mb-2 flex items-center gap-1.5 text-[13px] font-semibold">
              <NotebookPen className="h-3.5 w-3.5" /> 全部判断（{notes.length}）
            </h3>
            {notes.length === 0 ? (
              <p className="py-6 text-center text-[12px] text-muted-foreground/60">
                还没有研究笔记
              </p>
            ) : (
              <ul className="space-y-0.5">
                {notes.map((n) => (
                  <li key={n.id}>
                    <button
                      onClick={() => setActiveId(n.id)}
                      className={cn(
                        "w-full truncate rounded-[4px] px-2 py-1.5 text-left text-[13px] transition-colors",
                        n.id === active
                          ? "bg-[hsl(var(--muted))] text-foreground"
                          : "text-muted-foreground hover:bg-[hsl(var(--muted))] hover:text-foreground",
                      )}
                    >
                      <span className="block truncate">{n.title}</span>
                      <span className="block text-[10px] text-muted-foreground/60">
                        {fmtTime(n.created_at)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>

        {/* 右：研究线详情 */}
        <div>
          {!thread ? (
            <Panel>
              <p className="py-16 text-center text-sm text-muted-foreground/60">
                选一条判断，或者先写一条。
              </p>
            </Panel>
          ) : (
            <div className="space-y-4">
              <Panel>
                <h3 className="mb-1 text-[15px] font-semibold">{thread.note.title}</h3>
                <p className="mb-2 text-[11px] text-muted-foreground">
                  {fmtTime(thread.note.created_at)}
                </p>
                <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-foreground/90">
                  {thread.note.text || "（这条判断没有写正文）"}
                </p>
              </Panel>

              <Panel>
                <h3 className="mb-2 flex items-center gap-1.5 text-[13px] font-semibold">
                  <GitBranch className="h-3.5 w-3.5 text-[hsl(var(--primary))]" />
                  验证过的计算（{thread.runs.length}）
                </h3>
                {thread.runs.length === 0 ? (
                  <p className="py-6 text-center text-[12px] text-muted-foreground/60">
                    这条判断还没有跑过计算。去「回测」页跑一次，本页会按 note 关联。
                  </p>
                ) : (
                  <table className="w-full text-[13px]">
                    <thead>
                      <tr className="border-b border-border text-left text-[11px] text-muted-foreground">
                        <th className="px-2 py-1.5 font-medium">时间</th>
                        <th className="px-2 py-1.5 font-medium">类型</th>
                        <th className="px-2 py-1.5 font-medium">数据时点</th>
                        <th className="px-2 py-1.5 text-right font-medium">指标</th>
                      </tr>
                    </thead>
                    <tbody>
                      {thread.runs.map((r) => (
                        <tr key={r.id} className="border-b border-border/40">
                          <td className="whitespace-nowrap px-2 py-1.5 text-muted-foreground">{fmtTime(r.created_at)}</td>
                          <td className="px-2 py-1.5">{r.kind}</td>
                          <td className="px-2 py-1.5 text-muted-foreground">{r.data_as_of || "—"}</td>
                          <td className="px-2 py-1.5 text-right">
                            {Object.entries(r.metrics ?? {}).slice(0, 3).map(([k, v]) => (
                              <span key={k} className="ml-2 text-muted-foreground">
                                {k} <Num v={v} digits={2} colorBySign />
                              </span>
                            ))}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Panel>

              <Panel>
                <h3 className="mb-2 text-[13px] font-semibold">
                  当时在看的角度（{thread.views.length}）
                </h3>
                {thread.views.length === 0 ? (
                  <p className="py-4 text-center text-[12px] text-muted-foreground/60">
                    这条判断没有关联视图
                  </p>
                ) : (
                  <ul className="space-y-1">
                    {thread.views.map((v) => (
                      <li key={v.id} className="flex items-center gap-2 text-[13px]">
                        <span className="text-muted-foreground">{v.kind}</span>
                        <span>{v.name}</span>
                        <span className="ml-auto text-[10px] text-muted-foreground/60" style={{ fontFamily: "var(--font-mono, monospace)" }}>
                          {JSON.stringify(v.params)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
            </div>
          )}
        </div>
      </div>

      <Disclaimer />
    </div>
  );
}
