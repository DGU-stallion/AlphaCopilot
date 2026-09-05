/**
 * ReportsPage — 我的研报专用页（S3，复用 doc 表）。
 * 列出研报 + 新增（标题 + 文本）。第一版为最小可用；文档解析/检索/引用留后续。
 */

import { useCallback, useEffect, useState } from "react";
import { addReport, listReports, type ReportItem } from "@/lib/api";
import { useAiPage } from "@/lib/ai-page-context";

export function ReportsPage() {
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    listReports()
      .then(setReports)
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(refresh, [refresh]);

  useAiPage({
    key: `reports:${reports.length}`,
    title: "我的研报",
    context: { count: reports.length, titles: reports.map((r) => r.title) },
    suggestions: ["总结这几份研报的核心观点", "这些研报有哪些共同结论？"],
  });

  const onAdd = async () => {
    setError(null);
    try {
      await addReport({ title: title.trim(), text });
      setTitle("");
      setText("");
      refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div className="flex h-full flex-col gap-3 overflow-auto p-1">
      <div className="glass flex flex-col gap-2 rounded-lg p-3">
        <h2 className="text-base font-semibold text-foreground">我的研报</h2>
        <input
          aria-label="标题"
          placeholder="研报标题"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="glass rounded-md px-2 py-1 text-sm text-foreground"
        />
        <textarea
          aria-label="内容"
          placeholder="研报内容/结论（可粘贴 markdown）"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={4}
          className="glass rounded-md px-2 py-1 text-sm text-foreground"
        />
        <button
          type="button"
          onClick={onAdd}
          className="glass self-start rounded-md px-4 py-1.5 text-sm text-primary hover:text-accent"
        >
          保存研报
        </button>
      </div>

      {error && <div className="glass rounded-lg p-3 text-sm text-destructive">{error}</div>}

      <div className="glass rounded-lg p-3">
        {reports.length === 0 ? (
          <div className="p-4 text-center text-sm text-muted-foreground">暂无研报，先保存一份。</div>
        ) : (
          <ul className="flex flex-col gap-2">
            {reports.map((r) => (
              <li key={r.id} className="rounded-md bg-muted/20 px-3 py-2 text-sm text-foreground">
                {r.title}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
