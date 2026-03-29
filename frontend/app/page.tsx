"use client";

import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { EconomicDashboard } from "@/components/home/economic-dashboard";
import { StatusConsole } from "@/components/console/status-console";
import { CompanyAutocompleteMenu } from "@/components/search/company-autocomplete-menu";
import { Panel } from "@/components/ui/panel";
import { StatusPill } from "@/components/ui/status-pill";
import { useJobStream } from "@/hooks/use-job-stream";
import { ACTIVE_JOB_EVENT, clearStoredActiveJob, readStoredActiveJob, type StoredActiveJob } from "@/lib/active-job";
import { getGlobalMarketContext, resolveCompanyIdentifier, searchCompanies } from "@/lib/api";
import { showAppToast } from "@/lib/app-toast";
import { getPreferredSuggestion, normalizeSearchText } from "@/lib/company-search";
import type { CompanyMarketContextResponse, CompanyPayload, CompanySearchResponse, RefreshState } from "@/lib/types";

const MACRO_REFRESH_INTERVAL_MS = 5 * 60 * 1000;

export default function HomePage() {
  const router = useRouter();
  const homeSearchFormRef = useRef<HTMLFormElement>(null);
  const [query, setQuery] = useState("");
  const [data, setData] = useState<CompanySearchResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [invalidMessage, setInvalidMessage] = useState<string | null>(null);
  const [autocompleteOpen, setAutocompleteOpen] = useState(false);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(0);
  const [recentJob, setRecentJob] = useState<StoredActiveJob | null>(null);
  const [macroContext, setMacroContext] = useState<CompanyMarketContextResponse | null>(null);
  const [macroError, setMacroError] = useState<string | null>(null);
  const normalizedSearchText = useMemo(() => normalizeSearchText(query), [query]);
  const trimmedSearchText = normalizedSearchText.trim();
  const normalizedTickerQuery = trimmedSearchText.toUpperCase();
  const autocompleteResults = data?.results ?? [];
  const showAutocomplete = autocompleteOpen && trimmedSearchText.length > 0;
  const activeOptionId = showAutocomplete && autocompleteResults.length ? `home-search-autocomplete-option-${activeSuggestionIndex}` : undefined;
  const { consoleEntries, connectionState } = useJobStream(recentJob?.jobId ?? null);
  const bestMatch = getBestMatch(autocompleteResults, normalizedTickerQuery);
  const refreshLabel = getRefreshLabel(data?.refresh, loading);
  const displayTicker = bestMatch?.ticker ?? (normalizedTickerQuery || "-");

  useEffect(() => {
    setRecentJob(readStoredActiveJob());

    function syncRecentJob() {
      setRecentJob(readStoredActiveJob());
    }

    window.addEventListener(ACTIVE_JOB_EVENT, syncRecentJob as EventListener);
    return () => window.removeEventListener(ACTIVE_JOB_EVENT, syncRecentJob as EventListener);
  }, []);

  useEffect(() => {
    if (!recentJob || connectionState !== "error" || consoleEntries.length) {
      return;
    }

    clearStoredActiveJob(recentJob.jobId);
    setRecentJob(null);
  }, [connectionState, consoleEntries.length, recentJob]);

  useEffect(() => {
    let cancelled = false;

    async function loadMacroContext() {
      try {
        const payload = await getGlobalMarketContext();
        if (cancelled) {
          return;
        }
        setMacroContext(payload);
        setMacroError(null);
      } catch (nextError) {
        if (cancelled) {
          return;
        }
        setMacroError(nextError instanceof Error ? nextError.message : "Unable to load macro snapshot");
      }
    }

    function onVisibilityChange() {
      if (document.visibilityState === "visible") {
        void loadMacroContext();
      }
    }

    function onWindowFocus() {
      void loadMacroContext();
    }

    const intervalId = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void loadMacroContext();
      }
    }, MACRO_REFRESH_INTERVAL_MS);

    window.addEventListener("focus", onWindowFocus);
    document.addEventListener("visibilitychange", onVisibilityChange);

    void loadMacroContext();

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
      window.removeEventListener("focus", onWindowFocus);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, []);

  const goToTicker = useCallback(
    (ticker: string, destination: "company" | "models" = "company") => {
      const normalizedTicker = ticker.trim().toUpperCase();
      if (!normalizedTicker) {
        return;
      }

      setInvalidMessage(null);
      const suffix = destination === "models" ? "/models" : "";
      router.push(`/company/${encodeURIComponent(normalizedTicker)}${suffix}`);
    },
    [router]
  );

  const loadSearch = useCallback(async (searchQuery: string, signal?: AbortSignal) => {
    if (!searchQuery) {
      setData(null);
      setError(null);
      setLoading(false);
      setActiveSuggestionIndex(0);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const response = await searchCompanies(searchQuery, { refresh: false, signal });
      setData(response);
      setActiveSuggestionIndex(0);
    } catch (nextError) {
      if (signal?.aborted) {
        return;
      }
      setError(nextError instanceof Error ? nextError.message : "Search failed");
    } finally {
      if (!signal?.aborted) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void loadSearch(trimmedSearchText, controller.signal);
    }, 250);

    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [loadSearch, trimmedSearchText]);

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
    goToTicker(result.ticker, destination);
  }

  async function openSearch(destination: "company" | "models" = "company") {
    const selectedSuggestion = getPreferredSuggestion(autocompleteResults, trimmedSearchText, activeSuggestionIndex);
    if (selectedSuggestion) {
      selectSuggestion(selectedSuggestion, destination);
      return;
    }

    if (!trimmedSearchText) {
      return;
    }

    try {
      const resolution = await resolveCompanyIdentifier(trimmedSearchText);
      if (resolution.resolved && resolution.ticker) {
        setQuery(resolution.ticker);
        goToTicker(resolution.ticker, destination);
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
      void openSearch();
    }
  }

  return (
    <div className="home-shell home-shell-dashboard">
      <h1 className="sr-only">Fundamental Terminal Home</h1>
      <Panel
        title="Research Launcher"
        className="home-hero"
        variant="hero"
      >
        <div className="home-hero-grid">
          <form
            ref={homeSearchFormRef}
            onSubmit={(event) => {
              event.preventDefault();
              void openSearch();
            }}
            className="home-search-form"
          >
            <div className="home-command-copy">
              <span className="home-command-kicker">Research command</span>
              <div className="home-command-title">Search a company</div>
              <div className="home-command-text">
                Enter a ticker, company name, or CIK to open the workspace or jump into valuation models.
              </div>
            </div>

            <label className="home-search-label">
              <span className="home-search-kicker">Ticker, Company, or CIK</span>
              <div className="home-search-field">
                <input
                  value={query}
                  onChange={(event) => {
                    setQuery(event.target.value);
                    setAutocompleteOpen(true);
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
                    onHover={setActiveSuggestionIndex}
                    onSelect={(result) => selectSuggestion(result)}
                  />
                ) : null}
              </div>
            </label>

            <div className="home-hero-note home-search-note">
              Ticker, company name, or CIK. Resolution validated against SEC before routing.
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
            </div>
          </form>

          <div className="home-hero-side">
            {data ? <StatusPill state={data.refresh} /> : <span className="pill">Ready</span>}

            <div className="home-status-preview">
              <div className="home-status-preview-header">
                <span className="metric-label">Preview</span>
                <span className="home-status-preview-ticker">{displayTicker}</span>
              </div>
              <div className="home-status-preview-name">
                {bestMatch ? bestMatch.name : loading ? "Checking" : "Awaiting match"}
              </div>
              <div className="home-status-preview-meta">{bestMatch?.sector ? bestMatch.sector : ""}</div>
              <div className="pill">{refreshLabel}</div>
            </div>
          </div>
        </div>

      </Panel>

      <div className="home-dashboard-lower">
        <Panel
          title="Market Context"
          subtitle="Macro conditions and economic indicators."
          className="home-macro-panel"
          variant="subtle"
        >
          {macroError ? <div className="text-muted">{macroError}</div> : <EconomicDashboard context={macroContext} />}
        </Panel>

        <Panel
          title="Live Refresh Stream"
          subtitle={recentJob ? `Latest: ${recentJob.ticker}` : "Monitor background SEC fetches and model jobs."}
          className="home-launcher-panel"
          variant="subtle"
        >
          <StatusConsole entries={consoleEntries} connectionState={connectionState} />
        </Panel>
      </div>
    </div>
  );
}

function getBestMatch(results: CompanyPayload[], ticker: string): CompanyPayload | null {
  return results.find((result) => result.ticker.toUpperCase() === ticker) ?? results[0] ?? null;
}

function getRefreshLabel(refresh: RefreshState | null | undefined, loading: boolean): string {
  if (!refresh) {
    return loading ? "Checking ticker..." : "Ready to load data.";
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
