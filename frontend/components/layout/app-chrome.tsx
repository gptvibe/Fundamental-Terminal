"use client";

import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { CompanyAutocompleteMenu } from "@/components/search/company-autocomplete-menu";
import { resolveCompanyIdentifier, searchCompanies } from "@/lib/api";
import { APP_TOAST_EVENT, type AppToastDetail, showAppToast } from "@/lib/app-toast";
import { getPreferredSuggestion, normalizeSearchText } from "@/lib/company-search";
import type { CompanyPayload } from "@/lib/types";

interface AppChromeProps {
  children: ReactNode;
}

type ThemeMode = "dark" | "light";

const AUTOCOMPLETE_DEBOUNCE_MS = 180;

export function AppChrome({ children }: AppChromeProps) {
  const router = useRouter();
  const pathname = usePathname();
  const inputRef = useRef<HTMLInputElement>(null);
  const searchFormRef = useRef<HTMLFormElement>(null);
  const [searchText, setSearchText] = useState(deriveTicker(pathname));
  const [theme, setTheme] = useState<ThemeMode>("dark");
  const [autocompleteResults, setAutocompleteResults] = useState<CompanyPayload[]>([]);
  const [autocompleteOpen, setAutocompleteOpen] = useState(false);
  const [autocompleteLoading, setAutocompleteLoading] = useState(false);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(0);
  const [invalidMessage, setInvalidMessage] = useState<string | null>(null);
  const [toast, setToast] = useState<AppToastDetail | null>(null);
  const searchRequestId = useRef(0);
  const toastTimeoutRef = useRef<number | null>(null);
  const workspace = useMemo(() => deriveWorkspace(pathname), [pathname]);
  const isCompanyRoute = pathname?.startsWith("/company/") ?? false;
  const normalizedSearchText = useMemo(() => normalizeSearchText(searchText), [searchText]);
  const trimmedSearchText = normalizedSearchText.trim();
  const showAutocomplete = autocompleteOpen && trimmedSearchText.length > 0;

  useEffect(() => {
    setSearchText(deriveTicker(pathname));
    setAutocompleteOpen(false);
    setAutocompleteResults([]);
    setActiveSuggestionIndex(0);
    setInvalidMessage(null);
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

  useEffect(() => {
    function showToast(event: Event) {
      const customEvent = event as CustomEvent<AppToastDetail>;
      const detail = customEvent.detail;
      if (!detail?.message) {
        return;
      }

      if (toastTimeoutRef.current !== null) {
        window.clearTimeout(toastTimeoutRef.current);
      }

      setToast(detail);
      toastTimeoutRef.current = window.setTimeout(() => {
        setToast(null);
        toastTimeoutRef.current = null;
      }, 3000);
    }

    window.addEventListener(APP_TOAST_EVENT, showToast as EventListener);
    return () => {
      window.removeEventListener(APP_TOAST_EVENT, showToast as EventListener);
      if (toastTimeoutRef.current !== null) {
        window.clearTimeout(toastTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    function onPointerDown(event: MouseEvent) {
      if (!searchFormRef.current?.contains(event.target as Node)) {
        setAutocompleteOpen(false);
      }
    }

    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, []);

  useEffect(() => {
    if (!trimmedSearchText) {
      setAutocompleteResults([]);
      setAutocompleteLoading(false);
      setActiveSuggestionIndex(0);
      return;
    }

    const timer = window.setTimeout(async () => {
      const requestId = ++searchRequestId.current;

      try {
        setAutocompleteLoading(true);
        const response = await searchCompanies(trimmedSearchText, { refresh: false });
        if (requestId !== searchRequestId.current) {
          return;
        }

        setAutocompleteResults(response.results);
        setActiveSuggestionIndex(0);
      } catch {
        if (requestId !== searchRequestId.current) {
          return;
        }

        setAutocompleteResults([]);
      } finally {
        if (requestId === searchRequestId.current) {
          setAutocompleteLoading(false);
        }
      }
    }, AUTOCOMPLETE_DEBOUNCE_MS);

    return () => window.clearTimeout(timer);
  }, [trimmedSearchText]);

  function goToTicker(nextTicker: string) {
    const normalized = nextTicker.trim().toUpperCase();
    if (!normalized) {
      return;
    }

    setSearchText(normalized);
    setAutocompleteOpen(false);
    setInvalidMessage(null);
    router.push(`/company/${encodeURIComponent(normalized)}`);
  }

  function selectSuggestion(result: CompanyPayload) {
    goToTicker(result.ticker);
  }

  async function submitSearch() {
    const selectedSuggestion = getPreferredSuggestion(autocompleteResults, trimmedSearchText, activeSuggestionIndex);
    if (selectedSuggestion) {
      selectSuggestion(selectedSuggestion);
      return;
    }

    if (!trimmedSearchText) {
      return;
    }

    const resolution = await resolveCompanyIdentifier(trimmedSearchText);
    if (resolution.resolved && resolution.ticker) {
      goToTicker(resolution.ticker);
      return;
    }

    const message = resolution.error === "lookup_failed" ? "SEC lookup unavailable" : "Wrong ticker or company";
    setAutocompleteOpen(false);
    setInvalidMessage(message);
    showAppToast({ message, tone: "danger" });
  }

  function handleSearchKeyDown(event: ReactKeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      setAutocompleteOpen(false);
      return;
    }

    if (!autocompleteResults.length) {
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setAutocompleteOpen(true);
      setActiveSuggestionIndex((current) => (autocompleteOpen ? Math.min(current + 1, autocompleteResults.length - 1) : 0));
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      setAutocompleteOpen(true);
      setActiveSuggestionIndex((current) => (autocompleteOpen ? Math.max(current - 1, 0) : 0));
      return;
    }

    if (event.key === "Enter" && showAutocomplete) {
      event.preventDefault();
      void submitSearch();
    }
  }

  return (
    <div className={`app-shell${isCompanyRoute ? " is-company-route" : ""}`}>
      {toast ? (
        <div className="app-toast-stack" aria-live="assertive" aria-atomic="true">
          <div className={`app-toast is-${toast.tone ?? "info"}`} role="alert">
            {toast.message}
          </div>
        </div>
      ) : null}

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
            ref={searchFormRef}
            onSubmit={(event) => {
              event.preventDefault();
              void submitSearch();
            }}
            className={`app-topbar-search${invalidMessage ? " is-invalid" : ""}`}
          >
            <div className="app-topbar-search-copy">
              <span className="app-topbar-search-label">
                $TICKER or company
                <span className="app-keycap">/</span>
                to focus
              </span>
              <input
                ref={inputRef}
                value={searchText}
                onChange={(event) => {
                  setSearchText(event.target.value);
                  setAutocompleteOpen(true);
                  setInvalidMessage(null);
                }}
                onFocus={() => {
                  if (trimmedSearchText) {
                    setAutocompleteOpen(true);
                  }
                }}
                onKeyDown={handleSearchKeyDown}
                placeholder="AAPL or Apple"
                className={`app-topbar-search-input${invalidMessage ? " is-invalid" : ""}`}
                aria-label="Search company or ticker"
                role="combobox"
                aria-autocomplete="list"
                aria-haspopup="listbox"
                aria-expanded={showAutocomplete}
                aria-controls="app-topbar-autocomplete"
                aria-invalid={Boolean(invalidMessage)}
              />

              {showAutocomplete ? (
                <CompanyAutocompleteMenu
                  id="app-topbar-autocomplete"
                  results={autocompleteResults}
                  loading={autocompleteLoading}
                  activeIndex={activeSuggestionIndex}
                  onHover={setActiveSuggestionIndex}
                  onSelect={selectSuggestion}
                />
              ) : null}

              {invalidMessage ? <div className="company-search-feedback is-invalid">{invalidMessage}</div> : null}
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
