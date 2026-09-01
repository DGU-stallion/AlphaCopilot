/**
 * MarkdownBlock — 渲染 markdown artifact（研报/结论）。payload 形状：{text: string}
 * 或直接传字符串。用 react-markdown + remark-gfm（表格/删除线等）。
 */

import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function MarkdownBlock({
  payload,
  title,
}: {
  payload: { text?: string } | string;
  title?: string;
}) {
  const text = typeof payload === "string" ? payload : (payload.text ?? "");
  return (
    <div className="glass rounded-lg p-3" data-testid="markdown-block">
      {title && <div className="mb-2 text-sm font-medium text-foreground">{title}</div>}
      <div className="prose prose-sm max-w-none dark:prose-invert">
        <Markdown remarkPlugins={[remarkGfm]}>{text}</Markdown>
      </div>
    </div>
  );
}
