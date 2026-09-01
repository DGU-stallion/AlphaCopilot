import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import { ThemeProvider, useTheme } from "@/theme";

function Probe() {
  const { theme, toggle } = useTheme();
  return (
    <button onClick={toggle} data-theme={theme}>
      toggle
    </button>
  );
}

describe("ThemeProvider", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove("light");
  });

  it("默认暗色，切换后给 documentElement 加 .light 类", () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    const btn = screen.getByText("toggle");
    // 默认暗色：无 .light
    expect(btn.getAttribute("data-theme")).toBe("dark");
    expect(document.documentElement.classList.contains("light")).toBe(false);

    fireEvent.click(btn);
    expect(btn.getAttribute("data-theme")).toBe("light");
    expect(document.documentElement.classList.contains("light")).toBe(true);

    fireEvent.click(btn);
    expect(btn.getAttribute("data-theme")).toBe("dark");
    expect(document.documentElement.classList.contains("light")).toBe(false);
  });
});
