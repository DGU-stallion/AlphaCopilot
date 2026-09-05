import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, beforeEach } from "vitest";
import { Sidebar } from "@/components/Sidebar";

const STORAGE_KEY = "alphacopilot-sidebar-collapsed";

function renderSidebar() {
  return render(
    <MemoryRouter>
      <Sidebar />
    </MemoryRouter>,
  );
}

describe("Sidebar 收展", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("默认展开（w-56），点击收起变 w-16 并写 localStorage", () => {
    renderSidebar();
    const aside = screen.getByRole("complementary");
    expect(aside.className).toContain("w-56");
    expect(aside.getAttribute("data-collapsed")).toBe("false");

    fireEvent.click(screen.getByLabelText("收起侧边栏"));

    expect(aside.className).toContain("w-16");
    expect(aside.getAttribute("data-collapsed")).toBe("true");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("1");
  });

  it("从 localStorage 恢复收起状态", () => {
    localStorage.setItem(STORAGE_KEY, "1");
    renderSidebar();
    const aside = screen.getByRole("complementary");
    expect(aside.className).toContain("w-16");
    expect(screen.getByLabelText("展开侧边栏")).toBeTruthy();
  });

  it("展示 builtin 占位 tab", () => {
    renderSidebar();
    expect(screen.getByText("复盘看板")).toBeTruthy();
    expect(screen.getByText("盘面数据")).toBeTruthy();
    expect(screen.getByText("涨停样本统计")).toBeTruthy();
    expect(screen.getByText("相关性分析")).toBeTruthy();
  });
});
