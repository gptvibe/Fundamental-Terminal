"use client";

import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

interface AppChromeProps {
  children: ReactNode;
}

type ThemeMode = "dark" | "light";

export function AppChrome({ children }: AppChromeProps) {
  const router = useRouter();
  const pathname = usePathname();
  const inputRef = useRef<HTMLInputElement>(null);
  const [ticker, setTicker] = useState(deriveTicker(pathname));
  const [theme, setTheme] = useState<ThemeMode>("dark");
  const workspace = useMemo(() => deriveWorkspace(pathname), [pathname]);

  useEffect(() => {
    setTicker(deriveTicker(pathname));
  }, [pathname]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const isEditable = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
      if (event.key === "/" && !isEditable) {
        event.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    const savedTheme = window.localStorage.getItem("ft-theme");
    if (savedTheme === "dark" || savedTheme === "light") {
      setTheme(savedTheme);
      return;
    }

    const prefersLight = window.matchMedia("(prefers-color-scheme: light)").matches;
    setTheme(prefersLight ? "light" : "dark");
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("ft-theme", theme);
  }, [theme]);

  function goToTicker(nextTicker: string) {
    const normalized = nextTicker.trim().toUpperCase();
    if (!normalized) {
      return;
    }
    router.push(`/company/${encodeURIComponent(normalized)}`);
  }

  return (
    <div className="app-shell">
      <header className="app-topbar">
        <button onClick={() => router.push("/")} className="app-brand" aria-label="Go to home">
          <span className="app-brand-mark" aria-hidden="true">
            <span className="app-brand-mark-text">FT</span>
          </span>
          <span className="app-brand-copy">
            <span className="app-brand-kicker">Research Platform</span>
            <span className="app-brand-title">Fundamental Terminal</span>
            <span className="app-brand-tagline">
              {workspace.label}
              {workspace.ticker ? ` / ${workspace.ticker}` : ""}
            </span>
          </span>
        </button>

        <div className="app-topbar-center">
          <div className="app-workspace-pill" aria-label="Current workspace">
            <span className="app-workspace-pill-label">Workspace</span>
            <span className="app-workspace-pill-value">{workspace.label}</span>
          </div>

          <form
            onSubmit={(event) => {
              event.preventDefault();
              goToTicker(ticker);
            }}
            className="app-topbar-search"
          >
            <div className="app-topbar-search-copy">
              <span className="app-topbar-search-label">
                Open ticker
                <span className="app-keycap">/</span>
                to focus
              </span>
              <input
                ref={inputRef}
                value={ticker}
                onChange={(event) => setTicker(event.target.value.toUpperCase())}
                placeholder={workspace.ticker ? "Search another ticker" : "Search ticker"}
                className="app-topbar-search-input"
                aria-label="Search ticker"
              />
            </div>
            <button type="submit" className="app-topbar-search-submit">
              Open
            </button>
          </form>
        </div>

        <div className="app-topbar-tools">
          <span className="app-tools-label">Appearance</span>

          <div className="app-theme-switcher" role="group" aria-label="Color theme">
            <button
              type="button"
              className={`app-theme-option ${theme === "dark" ? "is-active" : ""}`}
              onClick={() => setTheme("dark")}
              aria-pressed={theme === "dark"}
            >
              Dark
            </button>
            <button
              type="button"
              className={`app-theme-option ${theme === "light" ? "is-active" : ""}`}
              onClick={() => setTheme("light")}
              aria-pressed={theme === "light"}
            >
              Light
            </button>
          </div>
        </div>
      </header>
      <main className="content-shell">{children}</main>
    </div>
  );
}

function deriveTicker(pathname: string | null): string {
  if (!pathname) {
    return "";
  }
  const parts = pathname.split("/").filter(Boolean);
  if (parts[0] === "company" && parts[1]) {
    return decodeURIComponent(parts[1]).toUpperCase();
  }
  return "";
}

function deriveWorkspace(pathname: string | null): { label: string; ticker: string | null } {
  if (!pathname || pathname === "/") {
    return { label: "Home", ticker: null };
  }

  const parts = pathname.split("/").filter(Boolean);
  if (parts[0] !== "company" || !parts[1]) {
    return { label: "Workspace", ticker: null };
  }

  const ticker = decodeURIComponent(parts[1]).toUpperCase();
  const section = parts[2] ?? "overview";

  switch (section) {
    case "overview":
      return { label: "Overview", ticker };
    case "financials":
      return { label: "Financials", ticker };
    case "ownership":
      return { label: "Ownership", ticker };
    case "insiders":
      return { label: "Insiders", ticker };
    case "models":
      return { label: "Models", ticker };
    default:
      return { label: "Workspace", ticker };
  }
}
