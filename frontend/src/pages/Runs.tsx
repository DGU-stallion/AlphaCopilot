import { useState } from "react";
import { GitCompare, RefreshCw, RotateCcw, Star, Trash2, X } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { Num } from "@/components/Num";
import { Button } from "@/components/ui/Form";
import { useCachedResource } from "@/lib/cache";
import { useAiPage } from "@/lib/ai-page";
import { useDataAsOfAuto } from "@/lib/data-asof";
import { runsApi, type RunRow, type RunDiff, type ViewRow } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Run 记录 / 对比（M3-1 + M3-4）。
 *
 * 为什么需要这一页：回测跑完只看到一条曲线和几个指标，**下次想对比就没了**。
 * Run registry 把每次计算的 params / codeHash / dataAsOf / metrics 都留档，
 * 于是「这次比上次好在哪」「是参数变了还是数据变了」才回答得出来。
 *
 * 这一页刻意不画曲线 —— 曲线在回测页。这里只回答「哪次、什么参数、什么数据、
 * 指标多少、和另一次差多少」。
 */

const KIND_LABEL: Record<string, string> = {
  backtest: "回测",
  factor: "因子",
  correlation: "相关性",
};

/** 时间戳 → "MM-DD HH:MM"（等宽显示用，不显示年份省宽度）。 */
function fmtTime(sec: number): string {
  const d = new Date(sec * 1000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** metric 名排序稳定，否则每次渲染列顺序会跳。 */
function metricKeys(a: RunRow | null, b: RunRow | null): string[] {
  const keys = new Set<string>();
  for (const r of [a, b]) if (r) Object.keys(r.metrics ?? {}).forEach((k) => keys.add(k));
  return [...keys].sort();
}

/** RunRow 暂无 note 字段的类型声明（api.ts 契约不动），后端 GET /runs 已返回 note。 */
type RunRowWithNote = RunRow & { note?: string };

export function Runs() {
  const [picked, setPicked] = useState<string[]>([]);
  const [tab, setTab] = useState<"runs" | "views">("runs");

  // 不用 `runs:${reload}` 做刷新：每点一次刷新就在缓存 Map 里永久多一条
  // （旧 key 没人 drop）。缓存自带 refresh()，直接用它。
  const runsRes = useCachedResource<RunRow[]>(
    "runs",
    () => runsApi.runs({ limit: 50 }),
    { ttlMs: 5_000 },
  );
  const viewsRes = useCachedResource<ViewRow[]>("views", () => runsApi.views());

  const runs = runsRes.data ?? [];
  const views = viewsRes.data ?? [];

  // 选中两个才做对比。多于两个就取前两个（对比是二元操作，选三个没有意义）。
  const [aId, bId] = picked;
  const a = runs.find((r) => r.id === aId) ?? null;
  const b = runs.find((r) => r.id === bId) ?? null;
  const diffRes = useCachedResource<RunDiff | null>(
    aId && bId ? `rundiff:${aId}:${bId}` : "rundiff:none",
    () => (aId && bId ? runsApi.runDiff(aId, bId) : Promise.resolve(null)),
    { ttlMs: 5_000 },
  );

  // 用 auto 版：取数时刻由 hook 自己记录（key 变化时记一次）。
  // 手写 fetchedAt: Date.now() 是无限重渲染的经典错法，已在这页踩过一次。
  useDataAsOfAuto(
    runs.length
      ? { dataAsOf: runs[0].data_as_of, label: "Run 记录" }
      : { dataAsOf: "", label: "Run 记录" },
  );

  useAiPage({
    key: "runs",
    title: "Run 记录",
    context: runs.length
      ? `共 ${runs.length} 条 Run（最近 ${fmtTime(runs[0].created_at)}）：\n` +
        runs.slice(0, 10).map((r) =>
          `${fmtTime(r.created_at)} ${KIND_LABEL[r.kind] ?? r.kind} ` +
          `params=${JSON.stringify(r.params)} dataAsOf=${r.data_as_of} ` +
          `metrics=${JSON.stringify(r.metrics)}`).join("\n")
      : "还没有 Run 记录（跑一次回测后会出现）",
    suggestions: ["我最近几次回测的差异主要是什么", "哪些指标在变好", "数据时点有没有变化"],
  });

  const toggle = (id: string) => {
    setPicked((cur) => {
      if (cur.includes(id)) return cur.filter((x) => x !== id);
      // 最多两个：再点第三个就把最早的挤掉
      return [...cur, id].slice(-2);
    });
  };

  // M3-4 Rerun：用同一条 Run 的输入快照再跑一次。
  // 409/501 要如实说出来（「没有快照」「没启用队列」），不能静默失败。
  const [rerunMsg, setRerunMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const doRerun = async (r: RunRow) => {
    setRerunMsg(null);
    try {
      const res = await runsApi.rerun(r.id);
      setRerunMsg({ ok: true, text: `已提交重跑（job ${res.job_id}）` });
      // 数据会变 —— 重跑的意义就在于看「同样的输入、不同的结果」
      setTimeout(refresh, 1500);
    } catch (e) {
      setRerunMsg({ ok: false, text: e instanceof Error ? e.message : "重跑失败" });
    }
  };

  const refresh = () => {
    // refresh() 走 force 路径，不产生新 key
    runsRes.refresh();
    viewsRes.refresh();
  };

  // ---------- B3：软删 + 撤销（硬规则 14）----------
  // 交互与页面删除完全同一套（Layout.tsx）：**不弹确认框** —— 确认弹窗能防
  // 「手滑」，防不了「确认了才发现想错了」；撤销能防后者，且不打断操作流。
  const [undo, setUndo] = useState<{ id: string; label: string } | null>(null);
  const [deleteErr, setDeleteErr] = useState<string | null>(null);

  const doDelete = async (r: RunRowWithNote) => {
    setDeleteErr(null);
    try {
      await runsApi.deleteRun(r.id);
      setUndo({ id: r.id, label: `${KIND_LABEL[r.kind] ?? r.kind}（${fmtTime(r.created_at)}）` });
      refresh();
    } catch (e) {
      setDeleteErr(e instanceof Error ? e.message : "删除失败");
    }
  };

  const undoDelete = async () => {
    if (!undo) return;
    try {
      await runsApi.restoreRun(undo.id);
      setUndo(null);
      refresh();
    } catch {
      // 恢复失败时保留提示条，让人看到「还撤销不掉」而不是静默失败。
    }
  };

  // ---------- B3：行内备注（失焦保存）----------
  // 点开 → 输入框 → 失焦/回车保存，Esc 取消。noteNotify 只记本地改动：
  // 等 refresh() 回来再覆盖一次会闪烁，先就地放进去。
  const [noteEdit, setNoteEdit] = useState<{ id: string; value: string } | null>(null);
  const [noteSaved, setNoteSaved] = useState<Record<string, string>>({});

  const noteOf = (r: RunRowWithNote) =>
    noteSaved[r.id] ?? r.note ?? "";

  const saveNote = async (rid: string, note: string) => {
    setNoteSaved((m) => ({ ...m, [rid]: note })); // 就地更新，不等 refresh 回来（会闪烁）
    try {
      await runsApi.setRunNote(rid, note); // 空串也允许（清除备注）
      refresh();
    } catch {
      setDeleteErr("备注保存失败（服务端返回错误）");
    }
  };

  return (
    <div>
      <PageHeader
        title="Run 记录"
        subtitle="每次确定性计算都留档：参数、代码指纹、数据时点、指标。选两条可对比。"
        actions={
          <Button variant="ghost" onClick={refresh}>
            <RefreshCw className={cn("h-3.5 w-3.5", runsRes.loading && "animate-spin")} /> 刷新
          </Button>
        }
      />

      <div className="mb-3 flex items-center gap-3 border-b border-border">
        {([["runs", `Run（${runs.length}）`], ["views", `已保存的视图（${views.length}）`]] as const).map(([k, label]) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={cn(
              "-mb-px border-b-2 px-1 pb-1.5 text-[13px] transition-colors",
              tab === k
                ? "border-[hsl(var(--primary))] text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {rerunMsg && (
        <div className={cn(
          "mb-3 rounded-[4px] border px-3 py-1.5 text-[12px]",
          rerunMsg.ok
            ? "border-[hsl(var(--success))]/40 text-[hsl(var(--success))]"
            : "border-[hsl(var(--danger))]/40 text-danger",
        )}>
          {rerunMsg.text}
        </div>
      )}

      {deleteErr && (
        <div className="mb-3 rounded-[4px] border border-[hsl(var(--danger))]/40 px-3 py-1.5 text-[12px] text-danger">
          {deleteErr}
        </div>
      )}

      {/* 软删后的撤销提示条（B3，硬规则 14）：确认弹窗防不了「确认完才发现想错了」，
          撤销能防后者且不打断操作流。与 Layout 的页面删除提示完全同一套。 */}
      {undo && (
        <div
          role="status"
          className="fixed bottom-10 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-[4px] border border-border bg-[hsl(var(--card))] px-3 py-2 text-[12px]"
        >
          <span className="text-muted-foreground">已删除 {undo.label}，可撤销</span>
          <button
            onClick={() => void undoDelete()}
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

      {tab === "runs" ? (
        <>
          {runsRes.loading && runs.length === 0 ? (
            <Panel><p className="py-10 text-center text-sm text-muted-foreground/60">加载中…</p></Panel>
          ) : runs.length === 0 ? (
            <Panel>
              <p className="py-10 text-center text-sm text-muted-foreground/60">
                还没有 Run 记录。去「回测」页跑一次，结果会自动留档。
              </p>
            </Panel>
          ) : (
            <Panel className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="border-b border-border text-left text-[11px] text-muted-foreground">
                    <th className="w-8 px-2 py-1.5 font-medium"><GitCompare className="h-3 w-3" /></th>
                    <th className="px-2 py-1.5 font-medium">时间</th>
                    <th className="px-2 py-1.5 font-medium">类型</th>
                    <th className="px-2 py-1.5 font-medium">参数</th>
                    <th className="w-40 px-2 py-1.5 font-medium">备注</th>
                    <th className="px-2 py-1.5 font-medium">数据时点</th>
                    <th className="px-2 py-1.5 font-medium">代码指纹</th>
                    <th className="px-2 py-1.5 text-right font-medium">关键指标</th>
                    <th className="w-10 px-2 py-1.5 font-medium" />
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => {
                    const on = picked.includes(r.id);
                    return (
                      <tr
                        key={r.id}
                        onClick={() => toggle(r.id)}
                        className={cn(
                          "group cursor-pointer border-b border-border/40 transition-colors hover:bg-[hsl(var(--muted))]",
                          on && "bg-[hsl(var(--muted))]",
                        )}
                      >
                        <td className="px-2 py-1.5">
                          <span className={cn(
                            "inline-block h-3 w-3 rounded-[2px] border",
                            on ? "border-[hsl(var(--primary))] bg-[hsl(var(--primary))]" : "border-border",
                          )} />
                        </td>
                        <td className="whitespace-nowrap px-2 py-1.5 text-muted-foreground" style={{ fontFamily: "var(--font-mono, monospace)" }}>
                          {fmtTime(r.created_at)}
                        </td>
                        <td className="px-2 py-1.5">{KIND_LABEL[r.kind] ?? r.kind}</td>
                        <td className="max-w-[240px] truncate px-2 py-1.5 text-muted-foreground" style={{ fontFamily: "var(--font-mono, monospace)" }}>
                          {JSON.stringify(r.params)}
                        </td>
                        <td className="max-w-[160px] px-2 py-1.5">
                          <NoteCell
                            note={noteOf(r as RunRowWithNote)}
                            editing={noteEdit?.id === r.id ? noteEdit.value : null}
                            onStart={() => setNoteEdit({ id: r.id, value: noteOf(r as RunRowWithNote) })}
                            onChange={(v) => setNoteEdit({ id: r.id, value: v })}
                            onSubmit={() => {
                              if (!noteEdit) return;
                              const { id, value } = noteEdit;
                              setNoteEdit(null);
                              if (value !== noteOf(r as RunRowWithNote)) void saveNote(id, value);
                            }}
                            onCancel={() => setNoteEdit(null)}
                          />
                        </td>
                        <td className="whitespace-nowrap px-2 py-1.5 text-muted-foreground" style={{ fontFamily: "var(--font-mono, monospace)" }}>
                          {r.data_as_of || "—"}
                        </td>
                        <td className="px-2 py-1.5 text-muted-foreground" style={{ fontFamily: "var(--font-mono, monospace)" }}>
                          {r.code_hash || "—"}
                        </td>
                        <td className="whitespace-nowrap px-2 py-1.5 text-right" style={{ fontFamily: "var(--font-mono, monospace)" }}>
                          {Object.entries(r.metrics ?? {}).slice(0, 2).map(([k, v]) => (
                            <span key={k} className="ml-2 text-muted-foreground">
                              {k} <Num v={v} digits={2} colorBySign />
                            </span>
                          ))}
                        </td>
                        <td className="px-2 py-1.5">
                          <div className="flex items-center gap-1">
                            <button
                              onClick={(e) => { e.stopPropagation(); void doRerun(r); }}
                              disabled={Object.keys(r.inputs ?? {}).length === 0}
                              title={Object.keys(r.inputs ?? {}).length === 0
                                ? "这条 Run 没有输入快照，无法重跑"
                                : "用同样的输入重跑一次"}
                              className="text-muted-foreground/60 hover:text-[hsl(var(--primary))] disabled:cursor-not-allowed disabled:opacity-30"
                            >
                              <RotateCcw className="h-3.5 w-3.5" />
                            </button>
                            {/* 软删（可撤销，见提示条）。悬停才显示：不挡选中点击流 */}
                            <button
                              onClick={(e) => { e.stopPropagation(); void doDelete(r as RunRowWithNote); }}
                              title={`删除 Run ${r.id}`}
                              aria-label={`删除 Run ${r.id}`}
                              className="text-muted-foreground/60 opacity-0 transition-opacity hover:text-danger group-hover:opacity-100 focus-visible:opacity-100"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </td>
                        <td className="px-2 py-1.5">
                          <button
                            onClick={(e) => { e.stopPropagation(); void doRerun(r); }}
                            disabled={Object.keys(r.inputs ?? {}).length === 0}
                            title={Object.keys(r.inputs ?? {}).length === 0
                              ? "这条 Run 没有输入快照，无法重跑"
                              : "用同样的输入重跑一次"}
                            className="text-muted-foreground/60 hover:text-[hsl(var(--primary))] disabled:cursor-not-allowed disabled:opacity-30"
                          >
                            <RotateCcw className="h-3.5 w-3.5" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </Panel>
          )}

          {/* 对比：选了两条才出现 */}
          {a && b && (
            <Panel className="mt-4">
              <h3 className="mb-2 text-[13px] font-semibold">对比</h3>
              {diffRes.loading && !diffRes.data ? (
                <p className="py-6 text-center text-sm text-muted-foreground/60">对比计算中…</p>
              ) : diffRes.error ? (
                <p className="py-6 text-center text-sm text-danger">对比失败：{String((diffRes.error as Error).message || diffRes.error)}</p>
              ) : diffRes.data ? (
                <div className="space-y-3">
                  {/* 参数差异：先看这个 —— 参数不同说明是两次不同的实验 */}
                  <div>
                    <p className="mb-1 text-[11px] text-muted-foreground">参数差异</p>
                    {Object.keys(diffRes.data.params).length === 0 ? (
                      <p className="text-[13px] text-muted-foreground">参数完全相同</p>
                    ) : (
                      <table className="w-full text-[13px]">
                        <tbody>
                          {Object.entries(diffRes.data.params).map(([k, v]) => (
                            <tr key={k} className="border-b border-border/40">
                              <td className="px-2 py-1.5 text-muted-foreground">{k}</td>
                              <td className="px-2 py-1.5" style={{ fontFamily: "var(--font-mono, monospace)" }}>
                                {String(v.a)} → {String(v.b)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>

                  {/* 指标差异 */}
                  <div>
                    <p className="mb-1 text-[11px] text-muted-foreground">指标差异</p>
                    <table className="w-full text-[13px]">
                      <thead>
                        <tr className="border-b border-border text-left text-[11px] text-muted-foreground">
                          <th className="px-2 py-1.5 font-medium">指标</th>
                          <th className="px-2 py-1.5 text-right font-medium">A</th>
                          <th className="px-2 py-1.5 text-right font-medium">B</th>
                          <th className="px-2 py-1.5 text-right font-medium">变化</th>
                        </tr>
                      </thead>
                      <tbody>
                        {metricKeys(a, b).map((k) => {
                          const m = diffRes.data!.metrics[k];
                          if (!m) return null;
                          return (
                            <tr key={k} className="border-b border-border/40">
                              <td className="px-2 py-1.5 text-muted-foreground">{k}</td>
                              <td className="px-2 py-1.5 text-right"><Num v={m.a} digits={2} /></td>
                              <td className="px-2 py-1.5 text-right"><Num v={m.b} digits={2} /></td>
                              <td className="px-2 py-1.5 text-right">
                                {/* delta 为 null 表示「只有一侧有」—— 显示「—」而不是 0，
                                    否则会被读成「没变化」 */}
                                {m.delta == null
                                  ? <span className="text-muted-foreground/60">—</span>
                                  : <Num v={m.delta} digits={2} signed colorBySign />}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}
            </Panel>
          )}
        </>
      ) : (
        <ViewsPanel views={views} onChanged={refresh} />
      )}

    </div>
  );
}

/** 行内备注：点开 → 输入框 → 失焦保存（B3）。Esc 取消。 */
function NoteCell({ note, editing, onStart, onChange, onSubmit, onCancel }: {
  note: string;
  editing: string | null;
  onStart: () => void;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
}) {
  if (editing !== null) {
    return (
      <input
        autoFocus
        aria-label="Run 备注"
        value={editing}
        onClick={(e) => e.stopPropagation()}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onSubmit}
        onKeyDown={(e) => {
          if (e.key === "Escape") { e.preventDefault(); onCancel(); }
          if (e.key === "Enter") { e.preventDefault(); (e.target as HTMLInputElement).blur(); }
        }}
        className="w-full rounded-[4px] border border-border bg-transparent px-1.5 py-0.5 text-[12px] text-foreground outline-none focus:border-[hsl(var(--primary))]"
      />
    );
  }
  if (note) {
    return (
      <button
        title="写备注"
        onClick={(e) => { e.stopPropagation(); onStart(); }}
        className="block max-w-full truncate text-left text-[12px] text-foreground/90 hover:text-foreground"
      >
        {note}
      </button>
    );
  }
  return (
    <button
      title="写备注"
      onClick={(e) => { e.stopPropagation(); onStart(); }}
      className="text-[12px] text-muted-foreground/40 hover:text-foreground"
    >
      写备注…
    </button>
  );
}

function ViewsPanel({ views, onChanged }: { views: ViewRow[]; onChanged: () => void }) {
  const [busy, setBusy] = useState<string | null>(null);

  const pin = async (v: ViewRow) => {
    setBusy(v.id);
    try { await runsApi.pinView(v.id, !v.pinned); onChanged(); } finally { setBusy(null); }
  };
  const del = async (v: ViewRow) => {
    setBusy(v.id);
    try { await runsApi.deleteView(v.id); onChanged(); } finally { setBusy(null); }
  };

  if (views.length === 0) {
    return (
      <Panel>
        <p className="py-10 text-center text-sm text-muted-foreground/60">
          还没有保存的视图。视图 = 「看什么」的组合（标的一篮、窗口、区间），
          保存后可以 Pin 到常用位置。
        </p>
      </Panel>
    );
  }

  return (
    <Panel>
      <table className="w-full text-[13px]">
        <thead>
          <tr className="border-b border-border text-left text-[11px] text-muted-foreground">
            <th className="px-2 py-1.5 font-medium">名称</th>
            <th className="px-2 py-1.5 font-medium">类型</th>
            <th className="px-2 py-1.5 font-medium">参数</th>
            <th className="w-24 px-2 py-1.5 font-medium">操作</th>
          </tr>
        </thead>
        <tbody>
          {views.map((v) => (
            <tr key={v.id} className="border-b border-border/40">
              <td className="px-2 py-1.5">
                <span className="flex items-center gap-1.5">
                  {v.pinned && <Star className="h-3 w-3 fill-current text-[hsl(var(--warning))]" />}
                  {v.name}
                </span>
              </td>
              <td className="px-2 py-1.5 text-muted-foreground">{KIND_LABEL[v.kind] ?? v.kind}</td>
              <td className="max-w-[300px] truncate px-2 py-1.5 text-muted-foreground" style={{ fontFamily: "var(--font-mono, monospace)" }}>
                {JSON.stringify(v.params)}
              </td>
              <td className="px-2 py-1.5">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => void pin(v)}
                    disabled={busy === v.id}
                    title={v.pinned ? "取消 Pin" : "Pin"}
                    className="text-muted-foreground/60 hover:text-[hsl(var(--warning))] disabled:opacity-40"
                  >
                    <Star className={cn("h-3.5 w-3.5", v.pinned && "fill-current")} />
                  </button>
                  <button
                    onClick={() => void del(v)}
                    disabled={busy === v.id}
                    title="删除"
                    className="text-muted-foreground/60 hover:text-danger disabled:opacity-40"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}
