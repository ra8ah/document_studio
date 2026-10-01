import { createContext, useContext, useEffect, useState } from "react";

const ThemeContext = createContext(null);

export function ThemeProvider({ children }) {
  // first visit: follow the OS (prefers-color-scheme); afterwards the saved choice wins
  const [dark, setDark] = useState(() => {
    try {
      const saved = localStorage.getItem("app-theme");
      if (saved) return saved === "dark";
    } catch { /* storage disabled */ }
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches || false;
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);
  const toggle = () => setDark((d) => { try { localStorage.setItem("app-theme", d ? "light" : "dark"); } catch { /* ignore */ } return !d; });

  return <ThemeContext.Provider value={{ dark, toggle }}>{children}</ThemeContext.Provider>;
}

export const useTheme = () => useContext(ThemeContext);
