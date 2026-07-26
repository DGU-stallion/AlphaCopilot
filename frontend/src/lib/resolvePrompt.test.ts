/**
 * Tests for design.md Correctness Properties:
 *   3 — API Path Prefix Correctness (quant → /api/quant, research → /api/research)
 *   9 — Context Placeholder Resolution (resolvePrompt)
 */
import { describe, it, expect } from "vitest";
import { resolvePrompt } from "@/components/common/ContextualAgentEntry";

// ---------------------------------------------------------------------------
// Property 9: Context Placeholder Resolution
// ---------------------------------------------------------------------------

describe("resolvePrompt (Property 9)", () => {
  it("replaces matched placeholders with context values", () => {
    const result = resolvePrompt("分析 {code} 的走势", { code: "600519" });
    expect(result).toBe("分析 600519 的走势");
  });

  it("replaces multiple placeholders", () => {
    const result = resolvePrompt("{action} {code} 从 {start} 到 {end}", {
      action: "回测",
      code: "000001",
      start: "2024-01-01",
      end: "2024-12-31",
    });
    expect(result).toBe("回测 000001 从 2024-01-01 到 2024-12-31");
  });

  it("removes unmatched placeholders (no matching key in context)", () => {
    const result = resolvePrompt("分析 {code} 和 {sector}", { code: "600519" });
    expect(result).toBe("分析 600519 和 ");
  });

  it("removes all placeholders when context is empty", () => {
    const result = resolvePrompt("{code} {name} {date}", {});
    expect(result).toBe("  ");
  });

  it("removes all placeholders when context is undefined", () => {
    const result = resolvePrompt("{code} 分析");
    expect(result).toBe(" 分析");
  });

  it("leaves text without placeholders unchanged", () => {
    const result = resolvePrompt("普通文本无占位符", { code: "600519" });
    expect(result).toBe("普通文本无占位符");
  });

  it("handles empty prompt string", () => {
    const result = resolvePrompt("", { code: "600519" });
    expect(result).toBe("");
  });

  it("resolved result contains no remaining {key} patterns", () => {
    const result = resolvePrompt("{a} {b} {c}", { a: "x" });
    // Property 9: SHALL contain no remaining {...} patterns
    expect(result).not.toMatch(/\{\w+\}/);
  });

  it("handles special characters in context values", () => {
    const result = resolvePrompt("查询 {code}", { code: "A&B=1+2" });
    expect(result).toBe("查询 A&B=1+2");
  });

  it("handles Unicode in context values", () => {
    const result = resolvePrompt("{name} 分析", { name: "贵州茅台" });
    expect(result).toBe("贵州茅台 分析");
  });

  it("does not replace non-word characters inside braces", () => {
    // {foo-bar} should NOT match (hyphen is not \\w)
    const result = resolvePrompt("{foo-bar} test", { "foo-bar": "value" });
    expect(result).toBe("{foo-bar} test");
  });

  it("replaces same placeholder used multiple times", () => {
    const result = resolvePrompt("{code} vs {code}", { code: "600519" });
    expect(result).toBe("600519 vs 600519");
  });
});

// ---------------------------------------------------------------------------
// Property 3: API Path Prefix Correctness
// ---------------------------------------------------------------------------

describe("API Path Prefix Correctness (Property 3)", () => {
  it("quant API client uses /api/quant base", async () => {
    // Dynamically read the QUANT_BASE constant from api.ts source
    // We verify via the sseUrl function which exposes the full URL construction
    const apiModule = await import("@/lib/api");
    const sseUrl = apiModule.api.sseUrl("test-session");
    expect(sseUrl).toMatch(/^\/api\/quant\//);
  });

  it("quant SSE URL starts with /api/quant/sessions", async () => {
    const apiModule = await import("@/lib/api");
    const url = apiModule.api.sseUrl("abc123", { replay: "active" });
    expect(url.startsWith("/api/quant/sessions/abc123/events")).toBe(true);
    expect(url).toContain("replay=active");
  });

  it("research API client uses /api/research base via reportFileUrl", async () => {
    const { researchApi } = await import("@/lib/apiResearch");
    const url = researchApi.reportFileUrl("report-123");
    expect(url).toMatch(/^\/api\/research\//);
  });

  it("research reportFileUrl does not use /api/quant prefix", async () => {
    const { researchApi } = await import("@/lib/apiResearch");
    const url = researchApi.reportFileUrl("report-123");
    expect(url).not.toContain("/api/quant");
  });

  it("quant sseUrl does not use /api/research prefix", async () => {
    const apiModule = await import("@/lib/api");
    const url = apiModule.api.sseUrl("session-1");
    expect(url).not.toContain("/api/research");
  });
});

// ---------------------------------------------------------------------------
// Property 10: Prefill URL Encoding Round-trip
// ---------------------------------------------------------------------------

describe("Prefill URL Encoding Round-trip (Property 10)", () => {
  it("basic ASCII prompt survives encode/decode", () => {
    const prompt = "Analyze AAPL stock price";
    const encoded = encodeURIComponent(prompt);
    expect(decodeURIComponent(encoded)).toBe(prompt);
  });

  it("Chinese characters survive encode/decode", () => {
    const prompt = "分析贵州茅台的技术面和基本面，给出投研观点";
    const encoded = encodeURIComponent(prompt);
    expect(decodeURIComponent(encoded)).toBe(prompt);
  });

  it("special characters survive encode/decode", () => {
    const prompt = "price > 100 & volume < 5000 | ratio = 1.5 + (x - y)";
    const encoded = encodeURIComponent(prompt);
    expect(decodeURIComponent(encoded)).toBe(prompt);
  });

  it("whitespace (spaces, tabs, newlines) survives encode/decode", () => {
    const prompt = "line 1\nline 2\ttab  spaces";
    const encoded = encodeURIComponent(prompt);
    expect(decodeURIComponent(encoded)).toBe(prompt);
  });

  it("empty string survives encode/decode", () => {
    const prompt = "";
    const encoded = encodeURIComponent(prompt);
    expect(decodeURIComponent(encoded)).toBe(prompt);
  });

  it("emoji and extended Unicode survive encode/decode", () => {
    const prompt = "🚀 分析 📈 趋势 — 「涨停板」";
    const encoded = encodeURIComponent(prompt);
    expect(decodeURIComponent(encoded)).toBe(prompt);
  });

  it("resolvePrompt output with Unicode context survives URL round-trip", () => {
    const resolved = resolvePrompt("分析 {code} 的走势，关注 {indicator}", {
      code: "600519",
      indicator: "MACD & RSI > 70",
    });
    const encoded = encodeURIComponent(resolved);
    expect(decodeURIComponent(encoded)).toBe(resolved);
  });

  it("full workflow: resolve → encode → URLSearchParams → decode", () => {
    const template = "回测 {code} 从 {start} 到 {end}，初始资金 ¥100,000";
    const context = { code: "000001", start: "2024-01-01", end: "2024-12-31" };
    const resolved = resolvePrompt(template, context);

    // Simulate navigation: encode into URL
    const params = new URLSearchParams({ prefill: resolved });
    const urlFragment = params.toString();

    // Simulate reading on agent page: decode from URL
    const decoded = new URLSearchParams(urlFragment).get("prefill");
    expect(decoded).toBe(resolved);
  });
});
