import { useEffect, useState } from "react";

function getEffectiveDark(): boolean {
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr === "dark") return true;
  if (attr === "light") return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export function ThemeToggle() {
  const [isDark, setIsDark] = useState(getEffectiveDark);

  useEffect(() => {
    setIsDark(getEffectiveDark());
  }, []);

  function toggle() {
    const next = !isDark;
    document.documentElement.setAttribute("data-theme", next ? "dark" : "light");
    setIsDark(next);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      className="flex items-center gap-1.5 rounded-md border border-line-strong bg-raised px-3 py-1.5 text-xs text-ink-dim hover:border-accent hover:text-ink"
    >
      <span>{isDark ? "☀" : "☽"}</span>
      <span>{isDark ? "Light" : "Dark"}</span>
    </button>
  );
}
