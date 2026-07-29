"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

import { Moon, Sun } from "./icons";

export type AppearanceMode = "light" | "dark";

const STORAGE_KEY = "anchor-appearance";

/**
 * Runs before first paint so the document never renders in the wrong mode.
 * It sets `color-scheme` on the root, which is what resolves every
 * `light-dark()` token in the stylesheet; `data-theme` is only there so CSS
 * can key on the mode (the appearance toggle's icons) without React state.
 */
export const THEME_SCRIPT = `(function(){try{var s=localStorage.getItem(${JSON.stringify(
  STORAGE_KEY,
)});var m=(s==="light"||s==="dark")?s:(window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light");var r=document.documentElement;r.dataset.theme=m;r.style.colorScheme=m;}catch(e){}})();`;

function readMode(): AppearanceMode {
  if (typeof document === "undefined") {
    return "light";
  }
  // Read `color-scheme` rather than `data-theme`: it is an inline style that
  // React never manages, so it survives hydration intact.
  return document.documentElement.style.colorScheme === "dark"
    ? "dark"
    : "light";
}

function applyMode(mode: AppearanceMode) {
  const root = document.documentElement;
  root.dataset.theme = mode;
  root.style.colorScheme = mode;
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    // A blocked storage quota must not break the toggle.
  }
}

type ThemeContextValue = {
  mode: AppearanceMode;
  setMode: (mode: AppearanceMode) => void;
  toggleMode: () => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  // Both the prerendered HTML and the first client render use "light" so
  // hydration matches. The blocking script has already painted the real mode;
  // this only catches React up to it.
  const [mode, setModeState] = useState<AppearanceMode>("light");

  useEffect(() => {
    setModeState(readMode());
  }, []);

  const setMode = useCallback((next: AppearanceMode) => {
    applyMode(next);
    setModeState(next);
  }, []);

  const toggleMode = useCallback(() => {
    setModeState((current) => {
      const next = current === "dark" ? "light" : "dark";
      applyMode(next);
      return next;
    });
  }, []);

  return (
    <ThemeContext.Provider value={{ mode, setMode, toggleMode }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useAppearance(): ThemeContextValue {
  const value = useContext(ThemeContext);
  if (!value) {
    throw new Error("useAppearance must be used inside ThemeProvider");
  }
  return value;
}

/**
 * The 32px toggle used in the landing header and the console sidebar footer.
 * Both icons are always in the DOM and CSS picks one from `data-theme`, so the
 * right icon is on screen from the first paint rather than after hydration.
 */
export function AppearanceToggle() {
  const { toggleMode } = useAppearance();

  return (
    <button
      type="button"
      className="icon-btn appearance-toggle"
      onClick={toggleMode}
      aria-label="Switch appearance"
    >
      <Sun size={16} className="appearance-icon appearance-icon-dark" />
      <Moon size={16} className="appearance-icon appearance-icon-light" />
    </button>
  );
}
