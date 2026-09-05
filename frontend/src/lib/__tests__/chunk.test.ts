import { describe, it, expect } from "vitest";
import { extractDeltaText } from "@/lib/chunk";

describe("extractDeltaText", () => {
  it("提取 text_delta 的文本", () => {
    expect(extractDeltaText({ text: "茅" })).toBe("茅");
  });

  it("无 text 字段返回空", () => {
    expect(extractDeltaText({})).toBe("");
    expect(extractDeltaText({ text: 123 })).toBe("");
  });
});
