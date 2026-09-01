/**
 * 主题：默认暗色（暖橙），.light 切亮色。主题只影响 index.css 里的 HSL token，
 * 一处改 token 即全站变色（PLAN 规范：颜色只写在 index.css token + chart-theme.ts）。
 */

import { createContext, useCallback, useContext, useEffect, useState } from "react";

type Theme = "dark" | "light";
type Ctx = { theme: Theme; toggle: () => void };

const ThemeContext = createContext<Ctx | null>(null);
const STORAGE_KEY = "alphacopilot-theme";

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved === "light" ? "light" : "dark";
  });

  useEffect(() => {
    document.documentElement.classList.toggle("light", theme === "light");
    localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  const toggle = useCallback(
    () => setTheme((t) => (t === "dark" ? "light" : "dark")),
    [],
  );

  return (
    <ThemeContext.Provider value={{ theme, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): Ctx {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme 必须在 ThemeProvider 内使用");
  return ctx;
}
