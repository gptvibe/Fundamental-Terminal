"use client";

import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { CompanyAutocompleteMenu } from "@/components/search/company-autocomplete-menu";
import { Panel } from "@/components/ui/panel";
import { StatusPill } from "@/components/ui/status-pill";
import { useJobStream } from "@/hooks/use-job-stream";
import { useLocalUserData } from "@/hooks/use-local-user-data";
import { ACTIVE_JOB_EVENT, clearStoredActiveJob, readStoredActiveJob, type StoredActiveJob } from "@/lib/active-job";
import { getGlobalMarketContext, getWatchlistSummary, resolveCompanyIdentifier, searchCompanies } from "@/lib/api";
import { showAppToast } from "@/lib/app-toast";
import { getPreferredSuggestion, normalizeSearchText } from "@/lib/company-search";
import { formatDate, formatPercent, titleCase } from "@/lib/format";
import {
  readRecentCompanies,
  recordRecentCompany,
  subscribeRecentCompanies,
  type RecentCompany,
  type RecentCompanySnapshot,
} from "@/lib/recent-companies";
import type {
  CompanyMarketContextResponse,
  CompanyPayload,
  CompanySearchResponse,
  ConsoleEntry,
  MarketFredSeriesPayload,
  RefreshState,
  WatchlistSummaryItemPayload,
} from "@/lib/types";

const MACRO_REFRESH_INTERVAL_MS = 5 * 60 * 1000;
const MAX_WATCHLIST_SUMMARY_TICKERS = 8;

type HomeChangeTone = "attention-high" | "attention-medium" | "live" | "success" | "error";

interface HomeChangeItem {
  id: string;
  ticker: string | null;
  name: string | null;
  label: string;
  title: string;
  detail: string;
  date: string | null;
  tone: HomeChangeTone;
}

interface HomeMacroCard {
  label: string;
  value: string;
  detail: string;
}

export default function HomePage() {
  const router = useRouter();
  const homeSearchFormRef = useRef<HTMLFormElement>(null);
  const [query, setQuery] = useState("");
  const [data, setData] = useState<CompanySearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [invalidMessage, setInvalidMessage] = useState<string | null>(null);
  const [autocompleteOpen, setAutocompleteOpen] = useState(false);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(0);
  const [recentJob, setRecentJob] = useState<StoredActiveJob | null>(null);
  const [macroContext, setMacroContext] = useState<CompanyMarketContextResponse | null>(null);
  const [macroError, setMacroError] = useState<string | null>(null);
  const [recentLaunches, setRecentLaunches] = useState<RecentCompany[]>([]);
  const [watchlistSummary, setWatchlistSummary] = useState<WatchlistSummaryItemPayload[]>([]);
  const [watchlistSummaryLoading, setWatchlistSummaryLoading] = useState(false);
  const [watchlistSummaryError, setWatchlistSummaryError] = useState<string | null>(null);
  const normalizedSearchText = useMemo(() => normalizeSearchText(query), [query]);
  const trimmedSearchText = normalizedSearchText.trim();
  const normalizedTickerQuery = trimmedSearchText.toUpperCase();
  const autocompleteResults = data?.results ?? [];
  const showAutocomplete = autocompleteOpen && trimmedSearchText.length > 0;
  const activeOptionId = showAutocomplete && autocompleteResults.length ? `home-search-autocomplete-option-${activeSuggestionIndex}` : undefined;
  const { consoleEntries, connectionState } = useJobStream(recentJob?.jobId ?? null);
  const { savedCompanies, watchlist, watchlistCount, noteCount, savedCompanyCount, syncMetadata } = useLocalUserData();
  const bestMatch = getBestMatch(autocompleteResults, normalizedTickerQuery);
  const refreshLabel = getRefreshLabel(data?.refresh, loading, Boolean(trimmedSearchText));
  const displayTicker = bestMatch?.ticker ?? (normalizedTickerQuery || "Preview");
  const previewName =
    bestMatch?.name ??
    (trimmedSearchText ? (loading ? "Checking company registry" : "Press Enter to resolve directly") : "Ticker, company, or CIK");
  const watchlistTickers = useMemo(
    () => watchlist.map((item) => item.ticker.trim().toUpperCase()).filter(Boolean).slice(0, MAX_WATCHLIST_SUMMARY_TICKERS),
    [watchlist]
  );
  const recentCompanies = useMemo(() => recentLaunches.slice(0, 4), [recentLaunches]);
  const savedFocus = useMemo(() => savedCompanies.slice(0, 4), [savedCompanies]);
  const recentChanges = useMemo(() => buildRecentChangeFeed(watchlistSummary, consoleEntries), [watchlistSummary, consoleEntries]);
  const macroSnapshot = useMemo(() => buildMacroSnapshot(macroContext), [macroContext]);
  const liveFeedLabel = useMemo(() => getLiveFeedLabel(connectionState, recentJob), [connectionState, recentJob]);

  useEffect(() => {
    setRecentJob(readStoredActiveJob());
    setRecentLaunches(readRecentCompanies());

    function syncRecentJob() {
      setRecentJob(readStoredActiveJob());
    }

    const unsubscribeRecentCompanies = subscribeRecentCompanies(() => {
      setRecentLaunches(readRecentCompanies());
    });

    window.addEventListener(ACTIVE_JOB_EVENT, syncRecentJob as EventListener);
    return () => {
      window.removeEventListener(ACTIVE_JOB_EVENT, syncRecentJob as EventListener);
      unsubscribeRecentCompanies();
    };
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

  useEffect(() => {
    let cancelled = false;

    async function loadWatchlistSummary() {
      if (!watchlistTickers.length) {
        setWatchlistSummary([]);
        setWatchlistSummaryError(null);
        setWatchlistSummaryLoading(false);
        return;
      }

      try {
        setWatchlistSummaryLoading(true);
        setWatchlistSummaryError(null);
        const response = await getWatchlistSummary(watchlistTickers);
        if (cancelled) {
          return;
        }
        setWatchlistSummary(response.companies);
      } catch (nextError) {
        if (cancelled) {
          return;
        }
        setWatchlistSummary([]);
        setWatchlistSummaryError(nextError instanceof Error ? nextError.message : "Unable to load watchlist summary");
      } finally {
        if (!cancelled) {
          setWatchlistSummaryLoading(false);
        }
      }
    }

    void loadWatchlistSummary();
    return () => {
      cancelled = true;
    };
  }, [watchlistTickers]);

  const goToTicker = useCallback(
    (ticker: string, destination: "company" | "models" = "company", snapshot?: RecentCompanySnapshot | null) => {
      const normalizedTicker = ticker.trim().toUpperCase();
      if (!normalizedTicker) {
        return;
      }

      const recentSnapshot = {
        ticker: normalizedTicker,
        name: snapshot?.name ?? null,
        sector: snapshot?.sector ?? snapshot?.market_sector ?? null,
      };

      setRecentLaunches(recordRecentCompany(recentSnapshot));
      if (recentSnapshot.name || recentSnapshot.sector) {
        syncMetadata(recentSnapshot);
      }

      setInvalidMessage(null);
      const suffix = destination === "models" ? "/models" : "";
      router.push(`/company/${encodeURIComponent(normalizedTicker)}${suffix}`);
    },
    [router, syncMetadata]
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
    goToTicker(result.ticker, destination, result);
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
    <div className="home-shell home-shell-terminal">
      <h1 className="sr-only">Fundamental Terminal Home</h1>
      <section className="home-launchpad">
        <div className="home-launchpad-grid">
          <div className="home-launchpad-main">
            <div className="home-launchpad-copy">
              <span className="home-launchpad-kicker">Research entry</span>
              <h2 className="home-launchpad-title">Start with a company, then move into evidence.</h2>
              <p className="home-launchpad-text">
                Search leads the page. Saved names, recent launches, and the latest watchlist changes stay nearby without reading like separate dashboards.
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

            <div className="home-macro-compact">
              <div className="home-macro-compact-head">
                <div>
                  <span className="home-section-kicker">Macro backdrop</span>
                  <div className="home-macro-compact-title">{macroSnapshot.title}</div>
                </div>
                <span className="pill">{macroError ? "Issue" : macroContext ? "Live" : "Loading"}</span>
              </div>
              <div className="home-macro-compact-copy">{macroError ?? macroSnapshot.copy}</div>
              <div className="home-macro-compact-grid">
                {macroSnapshot.cards.map((card) => (
                  <div key={card.label} className="home-macro-compact-card">
                    <div className="home-macro-compact-label">{card.label}</div>
                    <div className="home-macro-compact-value">{card.value}</div>
                    <div className="home-macro-compact-detail">{card.detail}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="home-terminal-grid">
        <Panel
          title="Recent Companies"
          subtitle="Names opened most recently across company workspaces."
          className="home-terminal-panel"
          variant="subtle"
        >
          {recentCompanies.length ? (
            <div className="home-utility-list">
              {recentCompanies.map((company) => (
                <div key={company.ticker} className="home-utility-item">
                  <div className="home-company-line">
                    <button
                      type="button"
                      className="home-inline-link home-company-button"
                      onClick={() => goToTicker(company.ticker, "company", company)}
                    >
                      <span className="home-company-ticker">{company.ticker}</span>
                      <span className="home-company-name">{company.name ?? "Open company workspace"}</span>
                    </button>
                    <span className="home-utility-time">{formatRelativeMoment(company.openedAt)}</span>
                  </div>
                  <div className="home-utility-meta">
                    {company.sector ? <span className="pill">{company.sector}</span> : null}
                    <span className="pill">Opened {formatDate(company.openedAt)}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="home-utility-empty">Recent launches will appear here after you open a company workspace.</div>
          )}
        </Panel>

        <Panel
          title="Saved & Watchlist"
          subtitle="Browser-local saved names and thesis notes kept within reach of search."
          className="home-terminal-panel"
          variant="subtle"
          aside={
            <button type="button" className="ticker-button home-toolbar-link" onClick={() => router.push("/watchlist")}>
              Open Watchlist
            </button>
          }
        >
          <div className="home-saved-summary-grid">
            <div className="home-saved-summary-card">
              <span className="home-saved-summary-label">Saved names</span>
              <span className="home-saved-summary-value">{savedCompanyCount}</span>
              <span className="home-saved-summary-detail">Local watchlist entries or notes.</span>
            </div>
            <div className="home-saved-summary-card">
              <span className="home-saved-summary-label">Watchlist</span>
              <span className="home-saved-summary-value">{watchlistCount}</span>
              <span className="home-saved-summary-detail">Tracked names ready for refresh and triage.</span>
            </div>
            <div className="home-saved-summary-card">
              <span className="home-saved-summary-label">Notes</span>
              <span className="home-saved-summary-value">{noteCount}</span>
              <span className="home-saved-summary-detail">Local research notes attached to a ticker.</span>
            </div>
          </div>

          {savedFocus.length ? (
            <div className="home-utility-list">
              {savedFocus.map((company) => (
                <div key={company.ticker} className="home-utility-item">
                  <div className="home-company-line">
                    <button
                      type="button"
                      className="home-inline-link home-company-button"
                      onClick={() =>
                        goToTicker(company.ticker, "company", {
                          ticker: company.ticker,
                          name: company.name,
                          sector: company.sector,
                        })
                      }
                    >
                      <span className="home-company-ticker">{company.ticker}</span>
                      <span className="home-company-name">{company.name ?? "Saved company"}</span>
                    </button>
                    <span className="home-utility-time">{formatRelativeMoment(company.activityAt)}</span>
                  </div>
                  <div className="home-utility-meta">
                    {company.sector ? <span className="pill">{company.sector}</span> : null}
                    {company.isInWatchlist ? <span className="pill">Watchlist</span> : null}
                    {company.hasNote ? <span className="pill">Note</span> : null}
                  </div>
                  <div className="home-utility-note">
                    {company.note ?? "No local note yet. Save a note from the company workspace to keep the thesis visible here."}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="home-utility-empty">Save a company or add a local note from any workspace to keep it pinned here.</div>
          )}
        </Panel>

        <Panel
          title="Recent Changes"
          subtitle={
            watchlistTickers.length
              ? "Latest watchlist alerts, filing activity, and background refresh events in one feed."
              : "Background refreshes stay visible here. Add watchlist names to layer in persisted alerts and activity."
          }
          className="home-terminal-panel home-terminal-panel-wide"
          variant="subtle"
          aside={<span className="pill">{liveFeedLabel}</span>}
        >
          {watchlistSummaryError ? <div className="text-muted">{watchlistSummaryError}</div> : null}
          {watchlistSummaryLoading && watchlistTickers.length ? <div className="text-muted">Loading watchlist changes...</div> : null}
          {recentChanges.length ? (
            <div className="home-change-list">
              {recentChanges.map((change) => (
                <div key={change.id} className="home-change-item">
                  <div className="home-change-copy">
                    <div className="home-change-kicker-row">
                      <span className={`home-change-badge ${getChangeToneClass(change.tone)}`}>{change.label}</span>
                      {change.ticker ? <span className="home-change-company">{change.ticker}{change.name ? ` · ${change.name}` : ""}</span> : null}
                    </div>
                    {change.ticker ? (
                      <button
                        type="button"
                        className="home-inline-link home-change-link"
                        onClick={() =>
                          goToTicker(change.ticker ?? "", "company", {
                            ticker: change.ticker ?? "",
                            name: change.name,
                          })
                        }
                      >
                        {change.title}
                      </button>
                    ) : (
                      <div className="home-change-title">{change.title}</div>
                    )}
                    <div className="home-change-detail">{change.detail}</div>
                  </div>
                  <div className="home-change-time">{formatRelativeMoment(change.date)}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="home-utility-empty">No recent changes yet. Launch a company or run a refresh to start building the feed.</div>
          )}
        </Panel>
      </div>
    </div>
  );
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

function buildRecentChangeFeed(summaryItems: WatchlistSummaryItemPayload[], consoleEntries: ConsoleEntry[]): HomeChangeItem[] {
  const watchlistChanges = summaryItems.flatMap((item) => {
    const changes: HomeChangeItem[] = [];

    if (item.latest_alert) {
      changes.push({
        id: `${item.ticker}-alert-${item.latest_alert.id}`,
        ticker: item.ticker,
        name: item.name,
        label: `${item.latest_alert.level.toUpperCase()} alert`,
        title: item.latest_alert.title,
        detail: [item.latest_alert.source, item.alert_summary.total ? `${item.alert_summary.total} active alerts` : null].filter(Boolean).join(" · "),
        date: item.latest_alert.date ?? item.last_checked,
        tone: item.latest_alert.level === "high" ? "attention-high" : "attention-medium",
      });
    }

    if (item.latest_activity) {
      changes.push({
        id: `${item.ticker}-activity-${item.latest_activity.id}`,
        ticker: item.ticker,
        name: item.name,
        label: item.latest_activity.badge || titleCase(item.latest_activity.type),
        title: item.latest_activity.title,
        detail: [item.sector, titleCase(item.latest_activity.type)].filter(Boolean).join(" · ") || "Watchlist activity",
        date: item.latest_activity.date ?? item.last_checked,
        tone: "live",
      });
    }

    return changes;
  });

  const streamChanges = consoleEntries.map((entry) => ({
    id: `console-${entry.id}`,
    ticker: entry.ticker?.trim().toUpperCase() || null,
    name: null,
    label: entry.level === "error" ? "Pipeline issue" : entry.status === "completed" ? "Refresh complete" : titleCase(entry.stage),
    title: entry.message,
    detail: [entry.ticker?.trim().toUpperCase() || null, entry.kind ? titleCase(entry.kind) : null, entry.trace_id ? `#${entry.trace_id.slice(0, 8)}` : null]
      .filter(Boolean)
      .join(" · ") || "Background refresh",
    date: entry.timestamp,
    tone: toneFromConsoleEntry(entry),
  }));

  return [...watchlistChanges, ...streamChanges]
    .sort((left, right) => toTimestamp(right.date) - toTimestamp(left.date))
    .slice(0, 8);
}

function toneFromConsoleEntry(entry: ConsoleEntry): HomeChangeTone {
  if (entry.level === "error") {
    return "error";
  }
  if (entry.level === "success" || entry.status === "completed") {
    return "success";
  }
  return "live";
}

function getChangeToneClass(tone: HomeChangeTone): string {
  return `is-${tone}`;
}

function buildMacroSnapshot(context: CompanyMarketContextResponse | null): { title: string; copy: string; cards: HomeMacroCard[] } {
  if (!context) {
    return {
      title: "Loading macro backdrop",
      copy: "Treasury, credit, and labor context are loading in the background.",
      cards: [
        { label: "10Y Treasury", value: "—", detail: "Treasury curve" },
        { label: "2s10s", value: "—", detail: "Curve slope" },
        { label: "BAA spread", value: "—", detail: "Credit spread" },
        { label: "Unemployment", value: "—", detail: "Labor" },
      ],
    };
  }

  const tenYearPoint = context.curve_points.find((point) => point.tenor === "10y") ?? null;
  const creditSpread = findFredSeries(context, "BAA10Y");
  const unemployment = findFredSeries(context, "UNRATE");
  const slope2s10s = context.slope_2s10s.value;
  const slope3m10y = context.slope_3m10y.value;
  let title = "Macro backdrop is steady";
  let copy = "Keep rates, labor, and credit in view while the company search stays primary.";

  if ((slope3m10y ?? 0) < 0 || (slope2s10s ?? 0) < 0) {
    title = "Curve still looks restrictive";
    copy = "The front end remains tighter than the long end, so financing sensitivity should stay in frame while you screen companies.";
  } else if ((creditSpread?.value ?? 0) > 0.03) {
    title = "Credit stress is elevated";
    copy = "Wider BAA spreads raise the bar for balance-sheet quality and refinancing resilience.";
  } else if ((unemployment?.value ?? 0) > 0.045) {
    title = "Labor is softening";
    copy = "A softer labor print can matter more than headline index strength when you build a fresh company brief.";
  }

  return {
    title,
    copy,
    cards: [
      {
        label: "10Y Treasury",
        value: formatPercent(tenYearPoint?.rate ?? null),
        detail: tenYearPoint?.observation_date ? formatDate(tenYearPoint.observation_date) : "Treasury curve",
      },
      {
        label: "2s10s",
        value: formatPercent(slope2s10s),
        detail: describeSlope(slope2s10s),
      },
      {
        label: "BAA spread",
        value: formatPercent(creditSpread?.value ?? null),
        detail: creditSpread?.observation_date ? formatDate(creditSpread.observation_date) : "Credit spread",
      },
      {
        label: "Unemployment",
        value: formatPercent(unemployment?.value ?? null),
        detail: unemployment?.observation_date ? formatDate(unemployment.observation_date) : "Labor backdrop",
      },
    ],
  };
}

function findFredSeries(context: CompanyMarketContextResponse, seriesId: string): MarketFredSeriesPayload | null {
  return context.fred_series.find((item) => item.series_id === seriesId) ?? null;
}

function describeSlope(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "Awaiting update";
  }

  if (value < 0) {
    return "Inverted";
  }
  if (value < 0.005) {
    return "Flat";
  }
  return "Positive";
}

function formatRelativeMoment(value: string | null | undefined): string {
  const timestamp = toTimestamp(value);
  if (!timestamp) {
    return "Date unavailable";
  }

  const deltaMs = Date.now() - timestamp;
  const minutes = Math.round(Math.abs(deltaMs) / 60000);

  if (minutes < 1) {
    return deltaMs >= 0 ? "Just now" : "Soon";
  }
  if (minutes < 60) {
    return deltaMs >= 0 ? `${minutes}m ago` : `In ${minutes}m`;
  }

  const hours = Math.round(minutes / 60);
  if (hours < 24) {
    return deltaMs >= 0 ? `${hours}h ago` : `In ${hours}h`;
  }

  const days = Math.round(hours / 24);
  return deltaMs >= 0 ? `${days}d ago` : `In ${days}d`;
}

function toTimestamp(value: string | null | undefined): number {
  if (!value) {
    return 0;
  }

  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function getLiveFeedLabel(connectionState: "idle" | "connecting" | "open" | "closed" | "error", recentJob: StoredActiveJob | null): string {
  if (!recentJob) {
    return "Watching for updates";
  }

  switch (connectionState) {
    case "open":
      return `${recentJob.ticker} live`;
    case "connecting":
      return `${recentJob.ticker} connecting`;
    case "error":
      return `${recentJob.ticker} reconnecting`;
    case "closed":
      return `${recentJob.ticker} paused`;
    default:
      return `${recentJob.ticker} queued`;
  }
}
