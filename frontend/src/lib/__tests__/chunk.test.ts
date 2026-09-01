import { describe, it, expect } from "vitest";
import { extractChunkText } from "@/lib/chunk";

describe("extractChunkText", () => {
  it("提取 text-delta 的文本", () => {
    const ev = { type: "assistant/chunk", data: { chunk: { type: "text-delta", text: "茅" } } };
    expect(extractChunkText(ev)).toBe("茅");
  });

  it("block-start/end 无文本返回空", () => {
    expect(extractChunkText({ data: { chunk: { type: "block-start" } } })).toBe("");
    expect(extractChunkText({ data: { chunk: { type: "block-end", block: { text: "茅台" } } } })).toBe("");
  });

  it("形状缺失返回空", () => {
    expect(extractChunkText({})).toBe("");
    expect(extractChunkText({ data: {} })).toBe("");
  });
});
