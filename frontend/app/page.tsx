"use client";

import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { StatusConsole } from "@/components/console/status-console";
import { HomeSavedCompaniesPanel } from "@/components/personal/home-saved-companies-panel";
import { CompanyAutocompleteMenu } from "@/components/search/company-autocomplete-menu";
import { Panel } from "@/components/ui/panel";
import { StatusPill } from "@/components/ui/status-pill";
import { useJobStream } from "@/hooks/use-job-stream";
import { ACTIVE_JOB_EVENT, clearStoredActiveJob, readStoredActiveJob, type StoredActiveJob } from "@/lib/active-job";
import { resolveCompanyIdentifier, searchCompanies } from "@/lib/api";
import { showAppToast } from "@/lib/app-toast";
import { getPreferredSuggestion, normalizeSearchText } from "@/lib/company-search";
import { MODEL_GUIDE, TRENDING_TICKERS } from "@/lib/constants";
import type { CompanyPayload, CompanySearchResponse, RefreshState } from "@/lib/types";

const HOW_IT_WORKS_STEPS = [
  {
    title: "Enter a ticker",
    copy: "Type a stock ticker and open the company workspace or the valuation models page."
  },
  {
    title: "We fetch the source data",
    copy: "The app checks company filings and other saved market data, then refreshes anything missing or out of date."
  },
  {
    title: "The calculations run automatically",
    copy: "Financial data is processed in the background and the available models are calculated for that ticker."
  },
  {
    title: "Charts and tables fill in",
    copy: "Once the refresh finishes, the financial views and model visuals update on their own."
  }
];

const WHERE_TO_LOOK = [
  {
    title: "Company Workspace",
    accentClass: "neon-green",
    copy: "Use this page for statements, historical financial data, and company-level views."
  },
  {
    title: "Valuation Models",
    accentClass: "neon-gold",
    copy: "Use this page for DCF, DuPont, Piotroski, Altman Z, ratios, and the model charts."
  },
  {
    title: "Live Updates",
    accentClass: "neon-cyan",
    copy: "Use this panel whenever a new ticker needs time to fetch data and finish the calculations."
  }
];

export default function HomePage() {
  const router = useRouter();
  const homeSearchFormRef = useRef<HTMLFormElement>(null);
  const [query, setQuery] = useState("AAPL");
  const [data, setData] = useState<CompanySearchResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [invalidMessage, setInvalidMessage] = useState<string | null>(null);
  const [autocompleteOpen, setAutocompleteOpen] = useState(false);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(0);
  const [recentJob, setRecentJob] = useState<StoredActiveJob | null>(null);
  const normalizedSearchText = useMemo(() => normalizeSearchText(query), [query]);
  const trimmedSearchText = normalizedSearchText.trim();
  const normalizedTickerQuery = trimmedSearchText.toUpperCase();
  const autocompleteResults = data?.results ?? [];
  const showAutocomplete = autocompleteOpen && trimmedSearchText.length > 0;
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

  const loadSearch = useCallback(async (searchQuery: string) => {
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
      const response = await searchCompanies(searchQuery, { refresh: false });
      setData(response);
      setActiveSuggestionIndex(0);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadSearch(trimmedSearchText);
    }, 250);

    return () => window.clearTimeout(timer);
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

    const resolution = await resolveCompanyIdentifier(trimmedSearchText);
    if (resolution.resolved && resolution.ticker) {
      setQuery(resolution.ticker);
      goToTicker(resolution.ticker, destination);
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
      void openSearch();
    }
  }

  return (
    <div className="home-shell">
      <Panel
        title="Start Here"
        subtitle="Type a ticker. We pull SEC filings and saved market data, refresh anything stale, then fill in the charts and model pages. This can take a little while."
        className="home-hero"
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
            <label className="home-search-label">
              <span className="home-search-kicker">Ticker or Company</span>
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
                  placeholder="AAPL or Apple"
                  className={`home-search-input${invalidMessage ? " is-invalid" : ""}`}
                  aria-label="Search company or ticker"
                  role="combobox"
                  aria-autocomplete="list"
                  aria-haspopup="listbox"
                  aria-expanded={showAutocomplete}
                  aria-controls="home-search-autocomplete"
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

            <div className="home-hero-note">
              Type a ticker like `AAPL` or a company name like `Apple`. If the SEC cannot resolve it, the search box turns red.
            </div>

            {invalidMessage ? <div className="company-search-feedback is-invalid">{invalidMessage}</div> : null}

            {error ? (
              <div className="pill" style={{ borderColor: "rgba(255, 77, 109, 0.35)", color: "var(--danger)" }}>
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
            {data ? <StatusPill state={data.refresh} /> : <span className="pill">Ready for a ticker</span>}

            <div className="metric-grid">
              <div className="metric-card">
                <div className="metric-label">Ticker</div>
                <div className="metric-value neon-cyan">{displayTicker}</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Match</div>
                <div className="metric-value neon-green">{bestMatch?.ticker ?? (loading ? "Checking" : "Pending")}</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Models</div>
                <div className="metric-value neon-gold">{MODEL_GUIDE.length}</div>
              </div>
            </div>

            <div className="home-hero-note">
              {bestMatch
                ? `${bestMatch.name}${bestMatch.sector ? ` - ${bestMatch.sector}` : ""}`
                : loading
                  ? "Checking local matches and SEC availability."
                  : "Use the dropdown suggestions or press Open to validate the ticker against the SEC."}
            </div>

            <div className="pill">{refreshLabel}</div>
          </div>
        </div>
      </Panel>

      <div className="home-main-column">
        <Panel title="What Happens Next" subtitle="The app handles the data fetch and model runs in the background">
          <div className="workflow-grid">
            {HOW_IT_WORKS_STEPS.map((step, index) => (
              <div key={step.title} className="workflow-card">
                <div className="grid-empty-kicker">Step {index + 1}</div>
                <div className="grid-empty-title">{step.title}</div>
                <div className="grid-empty-copy">{step.copy}</div>
              </div>
            ))}
          </div>

          <div className="sparkline-note">
            New tickers and stale data can take a little longer because SEC data, saved market data, and model calculations run before the charts update.
          </div>
        </Panel>

        <Panel title="Available Models" subtitle="Open Valuation Models to see these sections. You do not need to know the formulas.">
          <div className="model-guide-grid">
            {MODEL_GUIDE.map((model) => (
              <div key={model.key} className="model-guide-card">
                <div className="grid-empty-kicker">{model.label}</div>
                <div className="grid-empty-copy">Open Valuation Models and check {model.locationSummary}.</div>
              </div>
            ))}
          </div>

          <div className="sparkline-note">Every model section fills in automatically after the ticker finishes refreshing.</div>
        </Panel>
      </div>

      <div className="home-rail">
        <div id="saved-companies">
          <Panel title="Your Saved Companies" subtitle="Watchlist entries and private notes stay only on this browser on this device.">
            <HomeSavedCompaniesPanel />
          </Panel>
        </div>

        <Panel
          title="Live Updates"
          subtitle={recentJob ? `Latest background refresh for ${recentJob.ticker}` : "Watch SEC fetches and background calculations when a ticker needs fresh data"}
        >
          <StatusConsole entries={consoleEntries} connectionState={connectionState} />
        </Panel>

        <Panel title="Trending" subtitle="Popular starting points">
          <div className="home-trending-list">
            {TRENDING_TICKERS.map((item, index) => (
              <button
                key={item.ticker}
                className="ticker-button home-trending-item"
                onClick={() => goToTicker(item.ticker)}
                style={{ borderColor: index % 3 === 0 ? "rgba(0,255,65,0.22)" : index % 3 === 1 ? "rgba(255,215,0,0.22)" : "rgba(0,229,255,0.22)" }}
              >
                <div className="home-trending-copy">
                  <div className="home-trending-symbol">{item.ticker}</div>
                  <div className="text-muted home-trending-name">{item.name}</div>
                </div>
                <div className="home-trending-open">Open</div>
              </button>
            ))}
          </div>
        </Panel>

        <Panel title="Where To Look" subtitle="Use these pages once the ticker is loaded">
          <div className="home-notes-stack">
            {WHERE_TO_LOOK.map((note) => (
              <div key={note.title} className="pill">
                <span className={note.accentClass}>{note.title}</span> {note.copy}
              </div>
            ))}
            <div className="sparkline-note">If a page is still filling in, keep this dashboard open and watch Live Updates until the refresh finishes.</div>
          </div>
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
