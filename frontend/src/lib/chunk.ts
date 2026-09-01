/** 从 dsh assistant/chunk 事件提取增量文本（形状：data.chunk.{type:text-delta,text}）。 */
export function extractChunkText(data: Record<string, unknown>): string {
  const d = data.data as Record<string, unknown> | undefined;
  const chunk = d?.chunk as Record<string, unknown> | undefined;
  if (chunk && chunk.type === "text-delta" && typeof chunk.text === "string") {
    return chunk.text;
  }
  return "";
}
