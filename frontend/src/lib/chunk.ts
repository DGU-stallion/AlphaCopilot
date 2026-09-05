/** 从中立 text_delta 事件提取增量文本（payload 形状：{ text: string }）。 */
export function extractDeltaText(data: Record<string, unknown>): string {
  const text = data.text;
  return typeof text === "string" ? text : "";
}
