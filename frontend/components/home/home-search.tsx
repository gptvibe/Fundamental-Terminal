"use client";

import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { CompanyAutocompleteMenu } from "@/components/search/company-autocomplete-menu";
import { StatusPill } from "@/components/ui/status-pill";
import { useGoToTicker } from "@/hooks/use-go-to-ticker";
import { useLocalUserData } from "@/hooks/use-local-user-data";
import { searchCompanies } from "@/lib/api";
import { showAppToast } from "@/lib/app-toast";
import { findExactSearchMatch, normalizeSearchText } from "@/lib/company-search";
import { resolveCompanyIdentifier } from "@/lib/api";
import type { PerformanceAuditContext } from "@/lib/performance-audit";
import { withPerformanceAuditSource } from "@/lib/performance-audit";
import type { CompanyPayload, CompanySearchResponse, RefreshState } from "@/lib/types";

const HOME_SEARCH_DEBOUNCE_MS = 275;
const HOME_SEARCH_MIN_LENGTH = 2;
const SEARCH_CACHE_MAX_SIZE = 50;
const HOME_SEARCH_AUDIT_SOURCES = {
  autocomplete: "home:autocomplete-search",
  submit: "home:submit-search",
  resolve: "home:resolve-company",
} as const;

// Module-level cache: keyed by normalized query string, survives re-renders
const searchQueryCache = new Map<string, CompanySearchResponse>();

function cacheSet(key: string, value: CompanySearchResponse) {
  if (searchQueryCache.size >= SEARCH_CACHE_MAX_SIZE) {
    const firstKey = searchQueryCache.keys().next().value;
    if (firstKey !== undefined) {
      searchQueryCache.delete(firstKey);
    }
  }
  searchQueryCache.set(key, value);
}

function buildHomeSearchAuditContext(source: string): PerformanceAuditContext {
  return { scenario: "homepage_search", pageRoute: "/", source };
}

function getBestMatch(results: CompanyPayload[], ticker: string): CompanyPayload | null {
  return results.find((result) => result.ticker.toUpperCase() === ticker) ?? results[0] ?? null;
}

function getRefreshLabel(refresh: RefreshState | null | undefined, loading: boolean, hasQuery: boolean): string {
  if (!refresh) {
    if (!hasQuery) {
      return "Type a ticker, company, or CIK to preview routing before you launch.";
    }
    return loading ? "Checking ticker..." : "Ready to resolve and route.";
  }

  switch (refresh.reason) {
    case "missing":
      return "Saved data is missing and will load when you open the workspace.";
    case "stale":
      return "Saved data is older and will refresh when you open the workspace.";
    case "manual":
      return "A background refresh is already running.";
    case "fresh":
      return "Saved data is ready to use.";
    default:
      return refresh.triggered ? "Background refresh in progress." : "Open a page to start exploring.";
  }
}

interface HomeSearchProps {
  /** Additional content rendered inside the rail column (below the preview card). */
  railContent?: ReactNode;
}

export function HomeSearch({ railContent }: HomeSearchProps) {
  const router = useRouter();
  const homeSearchFormRef = useRef<HTMLFormElement>(null);
  const goToTicker = useGoToTicker();
  const { savedCompanyCount, watchlistCount, noteCount } = useLocalUserData();

  const [query, setQuery] = useState("");
  const [data, setData] = useState<CompanySearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [invalidMessage, setInvalidMessage] = useState<string | null>(null);
  const [autocompleteOpen, setAutocompleteOpen] = useState(false);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(0);
  const [hasNavigatedSuggestions, setHasNavigatedSuggestions] = useState(false);

  const normalizedSearchText = useMemo(() => normalizeSearchText(query), [query]);
  const trimmedSearchText = normalizedSearchText.trim();
  const normalizedTickerQuery = trimmedSearchText.toUpperCase();
  const autocompleteResults = data?.results ?? [];
  const showAutocomplete = autocompleteOpen && trimmedSearchText.length > 0;
  const activeOptionId =
    showAutocomplete && autocompleteResults.length ? `home-search-autocomplete-option-${activeSuggestionIndex}` : undefined;
  const bestMatch = getBestMatch(autocompleteResults, normalizedTickerQuery);
  const refreshLabel = getRefreshLabel(data?.refresh, loading, Boolean(trimmedSearchText));
  const displayTicker = bestMatch?.ticker ?? (normalizedTickerQuery || "Preview");
  const previewName =
    bestMatch?.name ??
    (trimmedSearchText ? (loading ? "Checking company registry" : "Press Enter to resolve directly") : "Ticker, company, or CIK");

  const loadSearch = useCallback(
    async (searchQuery: string, signal?: AbortSignal, source: keyof typeof HOME_SEARCH_AUDIT_SOURCES = "autocomplete") => {
      if (!searchQuery || searchQuery.length < HOME_SEARCH_MIN_LENGTH) {
        setData(null);
        setError(null);
        setLoading(false);
        setActiveSuggestionIndex(0);
        setHasNavigatedSuggestions(false);
        return null;
      }

      // Return cached result immediately for repeated queries
      const cached = searchQueryCache.get(searchQuery);
      if (cached && source === "autocomplete") {
        setData(cached);
        setActiveSuggestionIndex(0);
        setHasNavigatedSuggestions(false);
        setLoading(false);
        return cached;
      }

      try {
        setLoading(true);
        setError(null);
        const response = await withPerformanceAuditSource(
          buildHomeSearchAuditContext(HOME_SEARCH_AUDIT_SOURCES[source]),
          () => searchCompanies(searchQuery, { refresh: false, signal })
        );
        if (signal?.aborted) {
          return null;
        }
        cacheSet(searchQuery, response);
        setData(response);
        setActiveSuggestionIndex(0);
        setHasNavigatedSuggestions(false);
        return response;
      } catch (nextError) {
        if (signal?.aborted) {
          return null;
        }
        setError(nextError instanceof Error ? nextError.message : "Search failed");
        return null;
      } finally {
        if (!signal?.aborted) {
          setLoading(false);
        }
      }
    },
    []
  );

  // Debounced autocomplete with min-length guard
  useEffect(() => {
    if (trimmedSearchText.length < HOME_SEARCH_MIN_LENGTH) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void loadSearch(trimmedSearchText, controller.signal, "autocomplete");
    }, HOME_SEARCH_DEBOUNCE_MS);

    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [loadSearch, trimmedSearchText]);

  // Close autocomplete on outside click
  useEffect(() => {
    function onPointerDown(event: MouseEvent) {
      if (!homeSearchFormRef.current?.contains(event.target as Node)) {
        setAutocompleteOpen(false);
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, []);

  function selectSuggestion(result: CompanyPayload, destination: "company" | "models" = "company") {
    setQuery(result.ticker);
    setAutocompleteOpen(false);
    setHasNavigatedSuggestions(false);
    setInvalidMessage(null);
    goToTicker(result.ticker, destination, result);
  }

  async function openSearch(destination: "company" | "models" = "company") {
    const selectedSuggestion = hasNavigatedSuggestions
      ? (autocompleteResults[activeSuggestionIndex] ?? null)
      : findExactSearchMatch(autocompleteResults, trimmedSearchText);
    if (selectedSuggestion) {
      selectSuggestion(selectedSuggestion, destination);
      return;
    }

    if (!trimmedSearchText) {
      return;
    }

    const latestSearchResponse = data?.query === trimmedSearchText ? data : await loadSearch(trimmedSearchText, undefined, "submit");
    const resolvedSuggestion = findExactSearchMatch(latestSearchResponse?.results ?? [], trimmedSearchText);
    if (resolvedSuggestion) {
      selectSuggestion(resolvedSuggestion, destination);
      return;
    }

    try {
      const resolution = await withPerformanceAuditSource(
        buildHomeSearchAuditContext(HOME_SEARCH_AUDIT_SOURCES.resolve),
        () => resolveCompanyIdentifier(trimmedSearchText)
      );
      if (resolution.resolved && resolution.ticker) {
        setQuery(resolution.ticker);
        setInvalidMessage(null);
        goToTicker(resolution.ticker, destination, {
          ticker: resolution.ticker,
          name: resolution.name ?? bestMatch?.name ?? null,
          sector: bestMatch?.sector ?? bestMatch?.market_sector ?? null,
        });
        return;
      }

      const message = resolution.error === "lookup_failed" ? "SEC lookup unavailable" : "Wrong ticker, company, or CIK";
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
      void openSearch();
    }
  }

  return (
    <div className="home-launchpad-grid">
      <div className="home-launchpad-main">
        <div className="home-launchpad-copy">
          <span className="home-launchpad-kicker">Research entry</span>
          <h2 className="home-launchpad-title">Start with a company, then move into evidence.</h2>
          <p className="home-launchpad-text">
            Search leads the page. Saved names, recent launches, and the latest watchlist changes stay nearby without reading like separate
            dashboards.
          </p>
        </div>

        <form
          ref={homeSearchFormRef}
          onSubmit={(event) => {
            event.preventDefault();
            void openSearch();
          }}
          className="home-search-form home-launchpad-form"
        >
          <label className="home-search-label">
            <span className="home-search-kicker">Ticker, Company, or CIK</span>
            <div className="home-search-field">
              <input
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setAutocompleteOpen(true);
                  setHasNavigatedSuggestions(false);
                  setInvalidMessage(null);
                }}
                onFocus={() => {
                  if (trimmedSearchText) {
                    setAutocompleteOpen(true);
                  }
                }}
                onKeyDown={handleSearchKeyDown}
                placeholder="AAPL, Apple, or CIK: 0000320193"
                className={`home-search-input${invalidMessage ? " is-invalid" : ""}`}
                aria-label="Search by ticker, company, or CIK"
                role="combobox"
                aria-autocomplete="list"
                aria-haspopup="listbox"
                aria-expanded={showAutocomplete}
                aria-controls="home-search-autocomplete"
                aria-activedescendant={activeOptionId}
                aria-invalid={Boolean(invalidMessage)}
              />

              {showAutocomplete ? (
                <CompanyAutocompleteMenu
                  id="home-search-autocomplete"
                  results={autocompleteResults}
                  loading={loading}
                  activeIndex={activeSuggestionIndex}
                  onHover={(index) => {
                    setHasNavigatedSuggestions(true);
                    setActiveSuggestionIndex(index);
                  }}
                  onSelect={(result) => selectSuggestion(result)}
                />
              ) : null}
            </div>
          </label>

          <div className="home-hero-note home-search-note">
            SEC-validated routing for tickers, company names, and CIKs. Open the company workspace directly or jump into models.
          </div>

          {invalidMessage ? <div className="company-search-feedback is-invalid">{invalidMessage}</div> : null}

          {error ? (
            <div className="pill" style={{ borderColor: "color-mix(in srgb, var(--danger) 35%, transparent)", color: "var(--danger)" }}>
              {error}
            </div>
          ) : null}

          <div className="home-search-actions">
            <button type="submit" className="ticker-button home-action-primary">
              Open Company Workspace
            </button>
            <button type="button" className="ticker-button home-action-secondary" onClick={() => void openSearch("models")}>
              Open Valuation Models
            </button>
            <button type="button" className="ticker-button home-action-secondary" onClick={() => router.push("/screener")}>
              Open Official Screener
            </button>
          </div>
        </form>

        <div className="home-launchpad-stats">
          <div className="home-launchpad-stat">
            <span className="home-launchpad-stat-label">Saved</span>
            <span className="home-launchpad-stat-value">{savedCompanyCount}</span>
            <span className="home-launchpad-stat-detail">Companies with a local watchlist flag or note.</span>
          </div>
          <div className="home-launchpad-stat">
            <span className="home-launchpad-stat-label">Watchlist</span>
            <span className="home-launchpad-stat-value">{watchlistCount}</span>
            <span className="home-launchpad-stat-detail">Tracked names ready for cross-company triage.</span>
          </div>
          <div className="home-launchpad-stat">
            <span className="home-launchpad-stat-label">Notes</span>
            <span className="home-launchpad-stat-value">{noteCount}</span>
            <span className="home-launchpad-stat-detail">Local thesis notes preserved beside the launcher.</span>
          </div>
        </div>
      </div>

      <div className="home-launchpad-rail">
        <div className="home-launchpad-preview">
          <div className="home-launchpad-preview-head">
            <span className="home-section-kicker">Preview</span>
            {data ? <StatusPill state={data.refresh} /> : <span className="pill">Ready</span>}
          </div>
          <div className="home-launchpad-preview-ticker">{displayTicker}</div>
          <div className="home-launchpad-preview-name">{previewName}</div>
          <div className="home-launchpad-preview-copy">{refreshLabel}</div>
          <div className="home-launchpad-preview-meta">{bestMatch?.sector ? bestMatch.sector : "Awaiting company context"}</div>
        </div>

        {railContent}
      </div>
    </div>
  );
}
