/**
 * A3 — 设置页模型选择器（ROUND3）。
 *
 * 之前「模型端点」只是一行「由本机 Pi 配置决定」的静态文案——用户改不了。
 * 后端 `GET/PUT /api/settings/ai` 已经写完（34 个模型、现读注册表），
 * 本页职责：让用户真能选、真能保存，并且**不撒谎**：
 *
 *   1. 不做 baseURL/apiKey 输入框 —— PiProvider 不消费这两个字段
 *      （backend/agent/provider.py:81），做了等于让人填无效。
 *   2. `known: false`（保存过的模型已不在注册表里）必须醒目提示，
 *      不能静默换成第一个选项让用户误以为还是自己选的那个。
 *   3. 保存成功提示「下一条消息生效」——不是立即生效，别写「已应用」。
 *
 * 这里测行为，不测样式。
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ModelOption } from "@/lib/api";

const { aiMock, setModelMock } = vi.hoisted(() => ({
  aiMock: vi.fn(),
  setModelMock: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...mod,
    settingsApi: { ai: aiMock, setModel: setModelMock },
  };
});

import { Settings } from "@/pages/Settings";

function opt(id: string, provider: string): ModelOption {
  const model = id.startsWith(provider + "/") ? id.slice(provider.length + 1) : id;
  return {
    id,
    provider,
    model,
    label: `${provider} / ${model}`,
    vision: false,
  };
}

// 4 个模型、3 个 provider（含一个多模型的分组），足够验证分组而不啰嗦。
const OPTIONS: ModelOption[] = [
  opt("deepseek/deepseek-flash", "deepseek"),
  opt("magpie/workbuddy/glm-5.3-flash", "magpie"),
  opt("magpie/workbuddy/glm-5.3", "magpie"),
  opt("openrouter/z-ai/glm-5", "openrouter"),
];

async function renderPage(loaded: { current: string; known: boolean; options: ModelOption[] }) {
  aiMock.mockResolvedValue(loaded);
  render(<Settings />);
  await waitFor(() => expect(screen.getByLabelText("模型")).toBeTruthy());
}

describe("A3 模型选择器", () => {
  beforeEach(() => {
    aiMock.mockReset();
    setModelMock.mockReset();
  });

  it("按 provider 分组（optgroup）且显示 label", async () => {
    await renderPage({ current: OPTIONS[0]!.id, known: true, options: OPTIONS });

    const groups = screen.getAllByRole("group");
    const labels = groups.map((g) => (g as HTMLOptGroupElement).label);
    // 注册表里有 3 家 provider，分组必须与之一一对应，顺序稳定
    expect(labels).toEqual(["deepseek", "magpie", "openrouter"]);

    // magpie 组里有 2 个模型，label 来自后端的 `label` 字段
    const magpie = groups[1]!;
    expect(magpie.querySelectorAll("option").length).toBe(2);
    expect(magpie.textContent).toContain("magpie / workbuddy/glm-5.3-flash");

    // 选择器的当前值 = 后端回的 current，不静默换
    const select = screen.getByLabelText("模型") as HTMLSelectElement;
    expect(select.value).toBe(OPTIONS[0]!.id);
  });

  it("选择模型并保存 → 调 settingsApi.setModel(选项 id)，成功提示下一条消息生效", async () => {
    setModelMock.mockResolvedValue({ current: OPTIONS[3]!.id });
    await renderPage({ current: OPTIONS[0]!.id, known: true, options: OPTIONS });

    fireEvent.change(screen.getByLabelText("模型"), { target: { value: OPTIONS[3]!.id } });
    fireEvent.click(screen.getByRole("button", { name: /保存/ }));

    await waitFor(() => expect(setModelMock).toHaveBeenCalledWith(OPTIONS[3]!.id));
    expect(await screen.findByText(/已切换，下一条消息生效/)).toBeTruthy();
  });

  it("保存失败（如模型已下线 400）→ 如实报错，不假装成功", async () => {
    setModelMock.mockRejectedValue(new Error("400 模型不在注册表里"));
    await renderPage({ current: OPTIONS[0]!.id, known: true, options: OPTIONS });

    fireEvent.click(screen.getByRole("button", { name: /保存/ }));
    expect(await screen.findByText(/模型不在注册表里/)).toBeTruthy();
    expect(screen.queryByText(/已切换，下一条消息生效/)).toBeNull();
  });

  it("known=false：提示当前模型不在注册表里，且不静默替换当前值", async () => {
    await renderPage({ current: "ghost/legacy-model", known: false, options: OPTIONS });

    expect(screen.getByText(/当前模型不在注册表里/)).toBeTruthy();
    const select = screen.getByLabelText("模型") as HTMLSelectElement;
    // 关键：仍然回显保存过的那个模型，让用户看到现状，而不是悄悄换成第一个
    expect(select.value).toBe("ghost/legacy-model");
    // 不在该把它算进正常分组
    expect(aiMock).toHaveBeenCalledTimes(1);
  });

  it("模型清单读不到：如实显示失败，页面不崩", async () => {
    aiMock.mockRejectedValue(new Error("后端挂了"));
    render(<Settings />);
    expect(await screen.findByText(/读不到模型清单/)).toBeTruthy();
  });

  it("保留原有的连通自检与合规边界两块", async () => {
    await renderPage({ current: OPTIONS[0]!.id, known: true, options: OPTIONS });
    expect(screen.getByRole("button", { name: /检查后端连通/ })).toBeTruthy();
    expect(screen.getByText("合规边界")).toBeTruthy();
  });
});
