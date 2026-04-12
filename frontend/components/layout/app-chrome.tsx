"use client";

import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { AppLogo } from "@/components/layout/app-logo";
import { CompanyAutocompleteMenu } from "@/components/search/company-autocomplete-menu";
import { useLocalUserData } from "@/hooks/use-local-user-data";
import { resolveCompanyIdentifier, searchCompanies } from "@/lib/api";
import { APP_TOAST_EVENT, type AppToastDetail, showAppToast } from "@/lib/app-toast";
import { findExactSearchMatch, normalizeSearchText } from "@/lib/company-search";
import type { PerformanceAuditContext } from "@/lib/performance-audit";
import { withPerformanceAuditSource } from "@/lib/performance-audit";
import type { CompanyPayload } from "@/lib/types";

interface AppChromeProps {
  children: ReactNode;
}

type ThemeMode = "dark" | "light";
type LatestAutocompletePayload = {
  query: string;
  results: CompanyPayload[];
};

const AUTOCOMPLETE_DEBOUNCE_MS = 180;
const TOPBAR_SEARCH_AUDIT_SOURCES = {
  autocomplete: "topbar:autocomplete-search",
  submit: "topbar:submit-search",
  resolve: "topbar:resolve-company",
} as const;

export function AppChrome({ children }: AppChromeProps) {
  const router = useRouter();
  const pathname = usePathname();
  const routeTicker = useMemo(() => deriveTicker(pathname), [pathname]);
  const desktopInputRef = useRef<HTMLInputElement>(null);
  const mobileInputRef = useRef<HTMLInputElement>(null);
  const searchFormRef = useRef<HTMLFormElement>(null);
  const mobileSearchRef = useRef<HTMLDivElement>(null);
  const topbarRef = useRef<HTMLElement>(null);
  const [searchText, setSearchText] = useState(routeTicker);
  const [searchDirty, setSearchDirty] = useState(false);
  const [theme, setTheme] = useState<ThemeMode>("dark");
  const [autocompleteResults, setAutocompleteResults] = useState<CompanyPayload[]>([]);
  const [autocompleteOpen, setAutocompleteOpen] = useState(false);
  const [autocompleteLoading, setAutocompleteLoading] = useState(false);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(0);
  const [hasNavigatedSuggestions, setHasNavigatedSuggestions] = useState(false);
  const [invalidMessage, setInvalidMessage] = useState<string | null>(null);
  const [toast, setToast] = useState<AppToastDetail | null>(null);
  const [mobileSearchOpen, setMobileSearchOpen] = useState(false);
  const autocompleteAbortControllerRef = useRef<AbortController | null>(null);
  const latestAutocompleteRef = useRef<LatestAutocompletePayload | null>(null);
  const searchRequestId = useRef(0);
  const toastTimeoutRef = useRef<number | null>(null);
  const { savedCompanyCount } = useLocalUserData();
  const workspace = useMemo(() => deriveWorkspace(pathname), [pathname]);
  const isHomeRoute = pathname === "/";
  const isCompanyRoute = pathname?.startsWith("/company/") ?? false;
  const isScreenerRoute = pathname === "/screener";
  const normalizedSearchText = useMemo(() => normalizeSearchText(searchText), [searchText]);
  const trimmedSearchText = normalizedSearchText.trim();
  const allowAutocomplete = trimmedSearchText.length > 0 && (!isCompanyRoute || searchDirty || trimmedSearchText !== routeTicker);
  const showAutocomplete = autocompleteOpen && allowAutocomplete;
  const activeOptionId = showAutocomplete && autocompleteResults.length ? `app-topbar-autocomplete-option-${activeSuggestionIndex}` : undefined;
  const activeMobileOptionId = showAutocomplete && autocompleteResults.length ? `app-mobile-autocomplete-option-${activeSuggestionIndex}` : undefined;

  useEffect(() => {
    autocompleteAbortControllerRef.current?.abort();
    autocompleteAbortControllerRef.current = null;
    latestAutocompleteRef.current = null;
    setSearchText(routeTicker);
    setSearchDirty(false);
    setAutocompleteOpen(false);
    setAutocompleteResults([]);
    setActiveSuggestionIndex(0);
    setHasNavigatedSuggestions(false);
    setInvalidMessage(null);
    setMobileSearchOpen(false);
  }, [pathname, routeTicker]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const isEditable = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
      if (event.key === "/" && !isEditable) {
        event.preventDefault();
        desktopInputRef.current?.focus();
        desktopInputRef.current?.select();
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
    const el = topbarRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      const h = Math.round(entry.borderBoxSize?.[0]?.blockSize ?? entry.target.getBoundingClientRect().height);
      document.documentElement.style.setProperty("--command-height", `${h}px`);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

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

  const fetchAutocompleteResults = useCallback(async (
    searchQuery: string,
    controller = new AbortController(),
    source: keyof typeof TOPBAR_SEARCH_AUDIT_SOURCES = "autocomplete"
  ): Promise<CompanyPayload[]> => {
    if (!searchQuery) {
      latestAutocompleteRef.current = null;
      setAutocompleteResults([]);
      setAutocompleteLoading(false);
      setActiveSuggestionIndex(0);
      setHasNavigatedSuggestions(false);
      return [];
    }

    autocompleteAbortControllerRef.current?.abort();
    autocompleteAbortControllerRef.current = controller;
    const requestId = ++searchRequestId.current;
    try {
      setAutocompleteLoading(true);
      const response = await withPerformanceAuditSource(
        buildTopbarSearchAuditContext(TOPBAR_SEARCH_AUDIT_SOURCES[source], pathname),
        () => searchCompanies(searchQuery, { refresh: false, signal: controller.signal })
      );
      if (controller.signal.aborted || requestId !== searchRequestId.current) {
        return [];
      }

      latestAutocompleteRef.current = { query: searchQuery, results: response.results };
      setAutocompleteResults(response.results);
      setActiveSuggestionIndex(0);
      setHasNavigatedSuggestions(false);
      return response.results;
    } catch {
      if (controller.signal.aborted || requestId !== searchRequestId.current) {
        return [];
      }

      latestAutocompleteRef.current = { query: searchQuery, results: [] };
      if (requestId === searchRequestId.current) {
        setAutocompleteResults([]);
      }
      return [];
    } finally {
      if (autocompleteAbortControllerRef.current === controller) {
        autocompleteAbortControllerRef.current = null;
      }

      if (!controller.signal.aborted && requestId === searchRequestId.current) {
        setAutocompleteLoading(false);
      }
    }
  }, [pathname]);

  useEffect(() => {
    function onPointerDown(event: MouseEvent) {
      const target = event.target as Node;
      const clickedDesktopSearch = searchFormRef.current?.contains(target);
      const clickedMobileSearch = mobileSearchRef.current?.contains(target);
      if (!clickedDesktopSearch && !clickedMobileSearch) {
        setAutocompleteOpen(false);
      }
    }

    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, []);

  useEffect(() => {
    if (!allowAutocomplete) {
      autocompleteAbortControllerRef.current?.abort();
      autocompleteAbortControllerRef.current = null;
      latestAutocompleteRef.current = null;
      setAutocompleteResults([]);
      setAutocompleteLoading(false);
      setActiveSuggestionIndex(0);
      setHasNavigatedSuggestions(false);
      return;
    }

    const timer = window.setTimeout(async () => {
      void fetchAutocompleteResults(trimmedSearchText, new AbortController(), "autocomplete");
    }, AUTOCOMPLETE_DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timer);
      autocompleteAbortControllerRef.current?.abort();
    };
  }, [allowAutocomplete, fetchAutocompleteResults, trimmedSearchText]);

  useEffect(() => {
    if (!mobileSearchOpen) {
      return;
    }

    const focusHandle = window.requestAnimationFrame(() => {
      mobileInputRef.current?.focus();
      mobileInputRef.current?.select();
    });

    return () => window.cancelAnimationFrame(focusHandle);
  }, [mobileSearchOpen]);

  function goToTicker(nextTicker: string) {
    const normalized = nextTicker.trim().toUpperCase();
    if (!normalized) {
      return;
    }

    setSearchText(normalized);
    setSearchDirty(false);
    setAutocompleteOpen(false);
    setHasNavigatedSuggestions(false);
    setMobileSearchOpen(false);
    setInvalidMessage(null);
    router.push(`/company/${encodeURIComponent(normalized)}`);
  }

  function selectSuggestion(result: CompanyPayload) {
    goToTicker(result.ticker);
  }

  async function submitSearch() {
    const selectedSuggestion = hasNavigatedSuggestions
      ? (autocompleteResults[activeSuggestionIndex] ?? null)
      : findExactSearchMatch(autocompleteResults, trimmedSearchText);
    if (selectedSuggestion) {
      selectSuggestion(selectedSuggestion);
      return;
    }

    if (!trimmedSearchText) {
      return;
    }

    const latestAutocompleteResults = latestAutocompleteRef.current?.query === trimmedSearchText ? latestAutocompleteRef.current.results : null;
    const resolvedSuggestion = findExactSearchMatch(
      latestAutocompleteResults ?? (await fetchAutocompleteResults(trimmedSearchText, new AbortController(), "submit")),
      trimmedSearchText
    );
    if (resolvedSuggestion) {
      selectSuggestion(resolvedSuggestion);
      return;
    }

    try {
      const resolution = await withPerformanceAuditSource(
        buildTopbarSearchAuditContext(TOPBAR_SEARCH_AUDIT_SOURCES.resolve, pathname),
        () => resolveCompanyIdentifier(trimmedSearchText)
      );
      if (resolution.resolved && resolution.ticker) {
        goToTicker(resolution.ticker);
        return;
      }

      const message = resolution.error === "lookup_failed" ? "SEC lookup unavailable" : "Wrong ticker or company";
      setAutocompleteOpen(false);
      setInvalidMessage(message);
      showAppToast({ message, tone: "danger" });
    } catch {
      const message = "Lookup unavailable, try again.";
      setAutocompleteOpen(false);
      setInvalidMessage(message);
      showAppToast({ message, tone: "danger" });
    }
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
      setHasNavigatedSuggestions(true);
      setActiveSuggestionIndex((current) => (autocompleteOpen ? Math.min(current + 1, autocompleteResults.length - 1) : 0));
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      setAutocompleteOpen(true);
      setHasNavigatedSuggestions(true);
      setActiveSuggestionIndex((current) => (autocompleteOpen ? Math.max(current - 1, 0) : 0));
      return;
    }

    if (event.key === "Enter" && showAutocomplete) {
      event.preventDefault();
      void submitSearch();
    }
  }

  return (
    <div className={`app-shell${isCompanyRoute ? " is-company-route" : ""}${isHomeRoute ? " is-home-route" : ""}`}>
      {toast ? (
        <div className="app-toast-stack" aria-live="assertive" aria-atomic="true">
          <div className={`app-toast is-${toast.tone ?? "info"}`} role="alert">
            {toast.message}
          </div>
        </div>
      ) : null}

      <header ref={topbarRef} className={`app-topbar${isHomeRoute ? " is-home-route" : ""}`}>
        <button onClick={() => router.push("/")} className="app-brand" aria-label="Go to home">
          <span className="app-brand-mark" aria-hidden="true">
            <AppLogo className="app-brand-logo" />
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
          {!isHomeRoute ? (
            <div className="app-workspace-pill" aria-label="Current workspace">
              <span className="app-workspace-pill-label">Workspace</span>
              <span className="app-workspace-pill-value">{workspace.label}</span>
            </div>
          ) : (
            <div className="app-home-intro" aria-label="Home workspace summary">
              <span className="app-home-intro-label">The best free SEC-first research workstation for U.S. public equities</span>
            </div>
          )}

          {!isHomeRoute ? (
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
                  ref={desktopInputRef}
                  value={searchText}
                  onChange={(event) => {
                    setSearchText(event.target.value);
                    setSearchDirty(true);
                    setAutocompleteOpen(true);
                    setHasNavigatedSuggestions(false);
                    setInvalidMessage(null);
                  }}
                  onFocus={() => {
                    if (allowAutocomplete) {
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
                  aria-activedescendant={activeOptionId}
                  aria-invalid={Boolean(invalidMessage)}
                />

                {showAutocomplete ? (
                  <CompanyAutocompleteMenu
                    id="app-topbar-autocomplete"
                    results={autocompleteResults}
                    loading={autocompleteLoading}
                    activeIndex={activeSuggestionIndex}
                    onHover={(index) => {
                      setHasNavigatedSuggestions(true);
                      setActiveSuggestionIndex(index);
                    }}
                    onSelect={selectSuggestion}
                  />
                ) : null}

                {invalidMessage ? <div className="company-search-feedback is-invalid">{invalidMessage}</div> : null}
              </div>
              <button type="submit" className="app-topbar-search-submit">
                Open
              </button>
            </form>
          ) : null}
        </div>

        <div className={`app-topbar-tools${isHomeRoute ? " is-home-route" : ""}`}>
          <button type="button" className={`app-device-shortcut${isScreenerRoute ? " is-active" : ""}`} onClick={() => router.push("/screener")} title="Open the official screener">
            Screener
          </button>

          <button type="button" className="app-device-shortcut" onClick={() => router.push("/watchlist")} title="Open your browser-only saved list">
            Saved
            <span className="app-device-shortcut-count">{savedCompanyCount}</span>
          </button>

          <span className="app-tools-label">Theme</span>

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

      {isCompanyRoute ? (
        <div className="app-mobile-command-shell">
          <div className="app-mobile-command-bar">
            <button type="button" className="app-mobile-command-button" onClick={() => router.push("/")}>
              Home
            </button>
            <div className="app-mobile-command-summary" aria-label="Current workspace">
              <span className="app-mobile-command-kicker">Workspace</span>
              <span className="app-mobile-command-title">
                {workspace.label}
                {workspace.ticker ? ` / ${workspace.ticker}` : ""}
              </span>
            </div>
            <button
              type="button"
              className="app-mobile-command-button"
              onClick={() => {
                setMobileSearchOpen((current) => !current);
                setAutocompleteOpen(allowAutocomplete);
                setInvalidMessage(null);
              }}
              aria-expanded={mobileSearchOpen}
              aria-controls="app-mobile-command-drawer"
            >
              {mobileSearchOpen ? "Close" : "Search"}
            </button>
          </div>

          <div
            ref={mobileSearchRef}
            id="app-mobile-command-drawer"
            className={`app-mobile-command-drawer${mobileSearchOpen ? " is-open" : ""}`}
          >
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void submitSearch();
              }}
              className={`app-topbar-search app-mobile-command-search${invalidMessage ? " is-invalid" : ""}`}
            >
              <div className="app-topbar-search-copy">
                <span className="app-topbar-search-label">Open another company</span>
                <input
                  ref={mobileInputRef}
                  value={searchText}
                  onChange={(event) => {
                    setSearchText(event.target.value);
                    setSearchDirty(true);
                    setAutocompleteOpen(true);
                    setHasNavigatedSuggestions(false);
                    setInvalidMessage(null);
                  }}
                  onFocus={() => {
                    if (allowAutocomplete) {
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
                  aria-controls="app-mobile-autocomplete"
                  aria-activedescendant={activeMobileOptionId}
                  aria-invalid={Boolean(invalidMessage)}
                />

                {showAutocomplete ? (
                  <CompanyAutocompleteMenu
                    id="app-mobile-autocomplete"
                    results={autocompleteResults}
                    loading={autocompleteLoading}
                    activeIndex={activeSuggestionIndex}
                    onHover={(index) => {
                      setHasNavigatedSuggestions(true);
                      setActiveSuggestionIndex(index);
                    }}
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
        </div>
      ) : null}

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

function buildTopbarSearchAuditContext(source: string, pathname: string | null): PerformanceAuditContext {
  return {
    scenario: "topbar_search",
    pageRoute: deriveAuditPageRoute(pathname),
    source,
  };
}

function deriveAuditPageRoute(pathname: string | null): string {
  if (!pathname) {
    return "/unknown";
  }
  if (pathname.startsWith("/company/")) {
    return "/company/[ticker]";
  }
  return pathname;
}

function deriveWorkspace(pathname: string | null): { label: string; ticker: string | null } {
  if (!pathname || pathname === "/") {
    return { label: "Home", ticker: null };
  }

  const parts = pathname.split("/").filter(Boolean);
  if (parts[0] === "screener") {
    return { label: "Official Screener", ticker: null };
  }

  if (parts[0] === "watchlist") {
    return { label: "Watchlist", ticker: null };
  }

  if (parts[0] !== "company" || !parts[1]) {
    return { label: "Workspace", ticker: null };
  }

  const ticker = decodeURIComponent(parts[1]).toUpperCase();
  const section = parts[2] ?? "brief";

  switch (section) {
    case "brief":
    case "overview":
      return { label: "Brief", ticker };
    case "financials":
      return { label: "Financials", ticker };
    case "models":
      return { label: "Models", ticker };
    case "peers":
      return { label: "Peers", ticker };
    case "earnings":
      return { label: "Earnings", ticker };
    case "filings":
      return { label: "Filings", ticker };
    case "events":
      return { label: "Events", ticker };
    case "governance":
      return { label: "Governance", ticker };
    case "ownership":
    case "ownership-changes":
    case "stakes":
      return { label: "Ownership & Stakes", ticker };
    case "insiders":
      return { label: "Insiders", ticker };
    case "capital-markets":
      return { label: "Capital Markets", ticker };
    case "sec-feed":
      return { label: "SEC Feed", ticker };
    default:
      return { label: "Workspace", ticker };
  }
}
