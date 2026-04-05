"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { Panel } from "@/components/ui/panel";
import { useLocalUserData } from "@/hooks/use-local-user-data";
import { getWatchlistCalendar, getWatchlistSummary, refreshCompany } from "@/lib/api";
import { showAppToast } from "@/lib/app-toast";
import { formatDate, formatPercent } from "@/lib/format";
import { withPerformanceAuditSource } from "@/lib/performance-audit";
import type { WatchlistCalendarEventPayload, WatchlistSummaryItemPayload } from "@/lib/types";

type WatchlistFilter = "all" | "attention" | "stale" | "no-note" | "undervalued" | "quality" | "capital-return" | "balance-risk";
type WatchlistSort = "attention" | "undervaluation" | "quality" | "capital-return" | "balance-risk";

interface WatchlistRow extends WatchlistSummaryItemPayload {
  notePreview: string | null;
  hasNote: boolean;
  isStale: boolean;
}

const REFRESH_POLL_INTERVAL_MS = 3000;

const FILTERS: Array<{ key: WatchlistFilter; label: string }> = [
  { key: "all", label: "All" },
  { key: "attention", label: "Needs attention" },
  { key: "stale", label: "Stale" },
  { key: "no-note", label: "No note" },
  { key: "undervalued", label: "Undervalued" },
  { key: "quality", label: "Quality" },
  { key: "capital-return", label: "Capital return" },
  { key: "balance-risk", label: "Balance risk" },
];

export default function WatchlistPage() {
  const router = useRouter();
  const { watchlist, notesByTicker } = useLocalUserData();
  const [rows, setRows] = useState<WatchlistRow[]>([]);
  const [calendarEvents, setCalendarEvents] = useState<WatchlistCalendarEventPayload[]>([]);
  const [loading, setLoading] = useState(true);
  const [calendarLoading, setCalendarLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [calendarError, setCalendarError] = useState<string | null>(null);
  const [filter, setFilter] = useState<WatchlistFilter>("all");
  const [refreshingTicker, setRefreshingTicker] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<WatchlistSort>("attention");

  const watchlistTickers = useMemo(
    () => watchlist.map((item) => item.ticker.trim().toUpperCase()).filter(Boolean),
    [watchlist]
  );
  const hasPendingRefresh = useMemo(
    () => rows.some((item) => Boolean(item.refresh.triggered && item.refresh.job_id)),
    [rows]
  );

  useEffect(() => {
    let cancelled = false;

    async function loadSummary() {
      if (!watchlistTickers.length) {
        setRows([]);
        setCalendarEvents([]);
        setError(null);
        setCalendarError(null);
        setLoading(false);
        setCalendarLoading(false);
        return;
      }

      try {
        setLoading(true);
        setCalendarLoading(true);
        setError(null);
        setCalendarError(null);
        const [summaryResult, calendarResult] = await withPerformanceAuditSource(
          {
            pageRoute: "/watchlist",
            scenario: "watchlist_page",
            source: "watchlist:initial-load",
          },
          () =>
            Promise.allSettled([
              getWatchlistSummary(watchlistTickers),
              getWatchlistCalendar(watchlistTickers),
            ])
        );
        if (cancelled) {
          return;
        }

        if (summaryResult.status === "fulfilled") {
          setRows(toWatchlistRows(summaryResult.value.companies, notesByTicker));
        } else {
          setError(summaryResult.reason instanceof Error ? summaryResult.reason.message : "Unable to load watchlist summary");
          setRows([]);
        }

        if (calendarResult.status === "fulfilled") {
          setCalendarEvents(sortCalendarEvents(calendarResult.value.events));
        } else {
          setCalendarError(calendarResult.reason instanceof Error ? calendarResult.reason.message : "Unable to load events calendar");
          setCalendarEvents([]);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
          setCalendarLoading(false);
        }
      }
    }

    void loadSummary();
    return () => {
      cancelled = true;
    };
  }, [notesByTicker, watchlistTickers]);

  useEffect(() => {
    if (!watchlistTickers.length || !hasPendingRefresh) {
      return;
    }

    let cancelled = false;
    let pending = false;

    const poll = async () => {
      if (pending) {
        return;
      }

      pending = true;
      try {
        const [summaryResult, calendarResult] = await withPerformanceAuditSource(
          {
            pageRoute: "/watchlist",
            scenario: "watchlist_page",
            source: "watchlist:poll-refresh",
          },
          () =>
            Promise.allSettled([
              getWatchlistSummary(watchlistTickers),
              getWatchlistCalendar(watchlistTickers),
            ])
        );
        if (cancelled) {
          return;
        }

        if (summaryResult.status === "fulfilled") {
          setRows(toWatchlistRows(summaryResult.value.companies, notesByTicker));
          setError(null);
        } else {
          setError(summaryResult.reason instanceof Error ? summaryResult.reason.message : "Unable to auto-refresh watchlist summary");
        }

        if (calendarResult.status === "fulfilled") {
          setCalendarEvents(sortCalendarEvents(calendarResult.value.events));
          setCalendarError(null);
        } else {
          setCalendarError(calendarResult.reason instanceof Error ? calendarResult.reason.message : "Unable to auto-refresh events calendar");
        }
      } finally {
        pending = false;
      }
    };

    const intervalId = window.setInterval(() => {
      void poll();
    }, REFRESH_POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [hasPendingRefresh, notesByTicker, watchlistTickers]);

  const filteredRows = useMemo(() => {
    if (filter === "all") {
      return sortRows(rows, sortBy);
    }
    if (filter === "attention") {
      return sortRows(rows.filter((item) => item.alert_summary.high > 0 || item.alert_summary.medium > 0), sortBy);
    }
    if (filter === "stale") {
      return sortRows(rows.filter((item) => item.isStale), sortBy);
    }
    if (filter === "undervalued") {
      return sortRows(rows.filter((item) => (item.fair_value_gap ?? -1) > 0), sortBy);
    }
    if (filter === "quality") {
      return sortRows(rows.filter((item) => (item.roic ?? -1) > 0.12), sortBy);
    }
    if (filter === "capital-return") {
      return sortRows(rows.filter((item) => (item.shareholder_yield ?? -1) > 0.01), sortBy);
    }
    if (filter === "balance-risk") {
      return sortRows(rows.filter((item) => (item.balance_sheet_risk ?? 0) > 3), sortBy);
    }
    return sortRows(rows.filter((item) => !item.hasNote), sortBy);
  }, [filter, rows, sortBy]);
  const summaryCounts = useMemo(
    () => ({
      tracked: watchlistTickers.length,
      attention: rows.filter((item) => item.alert_summary.high > 0 || item.alert_summary.medium > 0).length,
      stale: rows.filter((item) => item.isStale).length,
      undervalued: rows.filter((item) => (item.fair_value_gap ?? -1) > 0).length
    }),
    [rows, watchlistTickers.length]
  );
  const noteCoverageCount = useMemo(() => rows.filter((item) => item.hasNote).length, [rows]);
  const highPriorityCount = useMemo(() => rows.filter((item) => item.alert_summary.high > 0).length, [rows]);

  async function handleRefresh(ticker: string) {
    try {
      setRefreshingTicker(ticker);
      await withPerformanceAuditSource(
        {
          pageRoute: "/watchlist",
          scenario: "watchlist_page",
          source: "watchlist:queue-refresh",
        },
        () => refreshCompany(ticker)
      );
      showAppToast({ message: `${ticker} refresh queued.`, tone: "info" });
      const [summaryResult, calendarResult] = await withPerformanceAuditSource(
        {
          pageRoute: "/watchlist",
          scenario: "watchlist_page",
          source: "watchlist:post-refresh-reload",
        },
        () =>
          Promise.allSettled([
            getWatchlistSummary(watchlistTickers),
            getWatchlistCalendar(watchlistTickers),
          ])
      );
      if (summaryResult.status === "fulfilled") {
        setRows(toWatchlistRows(summaryResult.value.companies, notesByTicker));
        setError(null);
      }
      if (calendarResult.status === "fulfilled") {
        setCalendarEvents(sortCalendarEvents(calendarResult.value.events));
        setCalendarError(null);
      }
    } catch (nextError) {
      showAppToast({
        message: nextError instanceof Error ? nextError.message : `Unable to refresh ${ticker}`,
        tone: "danger",
      });
    } finally {
      setRefreshingTicker(null);
    }
  }

  return (
    <div className="watchlist-page-grid">
      <Panel
        title="Watchlist Workspace"
        subtitle="Dense browser-local triage surface for saved companies, current alerts, valuation gaps, and direct next actions."
        variant="subtle"
      >
        <div className="watchlist-intro">
          <div className="watchlist-intro-copy">
            <div className="watchlist-intro-kicker">Cross-company triage</div>
            <div className="watchlist-intro-title">Review saved names in one pass.</div>
            <div className="watchlist-intro-text">
              Prioritize freshness, active alerts, valuation gaps, quality signals, and note coverage without leaving the page.
            </div>
            <div className="watchlist-intro-actions">
              <button type="button" className="ticker-button" onClick={() => router.push("/")}>
                Open Launcher
              </button>
              {filter !== "all" ? (
                <button type="button" className="ticker-button" onClick={() => setFilter("all")}>
                  Reset Filter
                </button>
              ) : null}
            </div>
          </div>

          <div className="watchlist-summary-strip">
            <div className="watchlist-summary-metric">
              <span className="watchlist-summary-label">Tracked</span>
              <span className="watchlist-summary-value">{summaryCounts.tracked}</span>
              <span className="watchlist-summary-detail">{noteCoverageCount} names carry an active local note.</span>
            </div>
            <div className="watchlist-summary-metric">
              <span className="watchlist-summary-label">Attention</span>
              <span className="watchlist-summary-value">{summaryCounts.attention}</span>
              <span className="watchlist-summary-detail">{highPriorityCount} have at least one high-severity alert.</span>
            </div>
            <div className="watchlist-summary-metric">
              <span className="watchlist-summary-label">Stale</span>
              <span className="watchlist-summary-value">{summaryCounts.stale}</span>
              <span className="watchlist-summary-detail">Refresh candidates based on cache age or missing data.</span>
            </div>
            <div className="watchlist-summary-metric">
              <span className="watchlist-summary-label">Undervalued</span>
              <span className="watchlist-summary-value">{summaryCounts.undervalued}</span>
              <span className="watchlist-summary-detail">Positive fair-value gap from cached model outputs.</span>
            </div>
          </div>
        </div>

        <div className="watchlist-toolbar">
          <div className="watchlist-controls-row">
            <div className="watchlist-sort-shell">
              <div className="watchlist-toolbar-label">Sort focus</div>
              <select className="watchlist-sort-select" value={sortBy} onChange={(event) => setSortBy(event.target.value as WatchlistSort)} aria-label="Sort watchlist">
                <option value="attention">Sort: Attention</option>
                <option value="undervaluation">Sort: Undervaluation</option>
                <option value="quality">Sort: Quality</option>
                <option value="capital-return">Sort: Capital return</option>
                <option value="balance-risk">Sort: Balance-sheet risk</option>
              </select>
            </div>
            <div className="watchlist-filter-row" role="group" aria-label="Watchlist filters">
              {FILTERS.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={`ticker-button${filter === item.key ? " is-active" : ""}`}
                  onClick={() => setFilter(item.key)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
          <div className="watchlist-toolbar-meta">
            <span className="watchlist-toolbar-chip">In view {filteredRows.length}</span>
            <span className="watchlist-toolbar-chip">Notes {noteCoverageCount}/{summaryCounts.tracked || 0}</span>
            <span className="watchlist-toolbar-chip">Filter {FILTERS.find((item) => item.key === filter)?.label ?? "All"}</span>
            {hasPendingRefresh ? <span className="watchlist-toolbar-chip is-live">Background refresh running</span> : null}
          </div>
        </div>

        {error ? <div className="text-muted">{error}</div> : null}

        {!watchlistTickers.length ? (
          <div className="grid-empty-state watchlist-empty-state">
            <div className="grid-empty-kicker">Watchlist</div>
            <div className="grid-empty-title">No companies saved yet</div>
            <div className="grid-empty-copy">Open any company page and use Save to My Watchlist to start your browser-local multi-company workspace.</div>
            <div className="watchlist-empty-actions">
              <button type="button" className="ticker-button" onClick={() => router.push("/")}>
                Open Research Launcher
              </button>
            </div>
          </div>
        ) : loading ? (
          <div className="text-muted">Loading watchlist summary...</div>
        ) : filteredRows.length ? (
          <div className="watchlist-table-shell">
            <table className="watchlist-table">
              <thead>
                <tr>
                  <th scope="col">Company</th>
                  <th scope="col">Signals</th>
                  <th scope="col">Valuation</th>
                  <th scope="col">Quality</th>
                  <th scope="col">Status</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((item) => (
                  <tr key={item.ticker} className={item.isStale ? "is-stale" : undefined}>
                    <td data-label="Company">
                      <button type="button" className="watchlist-company-link" onClick={() => router.push(`/company/${encodeURIComponent(item.ticker)}`)}>
                        <span className="watchlist-table-ticker">{item.ticker}</span>
                        <span className="watchlist-table-name">{item.name ?? "Unknown company"}</span>
                      </button>
                      <div className="watchlist-table-meta">
                        {item.sector ? <span className="pill">{item.sector}</span> : null}
                        <span className="pill">{item.isStale ? "Stale" : "Fresh"}</span>
                        <span className="pill">CIK {item.cik ?? "Unknown"}</span>
                      </div>
                      <div className={`watchlist-table-note${item.hasNote ? " has-note" : ""}`}>
                        {item.notePreview ?? "No local note yet. Add one from the company workspace to keep the thesis visible here."}
                      </div>
                    </td>
                    <td data-label="Signals">
                      <div className="watchlist-cell-stack">
                        <div className="watchlist-alert-row" aria-label={`Alert summary for ${item.ticker}`}>
                          <span className="pill">H {item.alert_summary.high}</span>
                          <span className="pill">M {item.alert_summary.medium}</span>
                          <span className="pill">L {item.alert_summary.low}</span>
                          <span className="pill">T {item.alert_summary.total}</span>
                        </div>
                        <div className="watchlist-cell-note">{item.latest_alert?.title ?? "No current alert"}</div>
                        <div className="watchlist-cell-detail">
                          {item.latest_activity
                            ? `${item.latest_activity.title}${item.latest_activity.date ? ` · ${formatDate(item.latest_activity.date)}` : ""}`
                            : "No recent activity"}
                        </div>
                      </div>
                    </td>
                    <td data-label="Valuation" className="watchlist-number-cell">
                      <div className="watchlist-cell-stack">
                        <div className="watchlist-metric-line">
                          <span>Gap</span>
                          <strong>{formatValuationMetric(item.fair_value_gap, item.fair_value_gap_status)}</strong>
                        </div>
                        <div className="watchlist-metric-line">
                          <span>Implied growth</span>
                          <strong>{formatValuationMetric(item.implied_growth, item.implied_growth_status)}</strong>
                        </div>
                        <div className="watchlist-cell-detail">
                          Coverage {item.coverage.financial_periods.toLocaleString()} periods · {item.coverage.price_points.toLocaleString()} price points
                        </div>
                      </div>
                    </td>
                    <td data-label="Quality" className="watchlist-number-cell">
                      <div className="watchlist-cell-stack">
                        <div className="watchlist-metric-line">
                          <span>ROIC</span>
                          <strong>{formatPercent(item.roic)}</strong>
                        </div>
                        <div className="watchlist-metric-line">
                          <span>Shareholder yield</span>
                          <strong>{formatPercent(item.shareholder_yield)}</strong>
                        </div>
                        <div className="watchlist-metric-line">
                          <span>Balance risk</span>
                          <strong>{formatSigned(item.balance_sheet_risk)}</strong>
                        </div>
                      </div>
                    </td>
                    <td data-label="Status">
                      <div className="watchlist-cell-stack">
                        <div className="watchlist-cell-note">Last checked {item.last_checked ? formatDate(item.last_checked) : "Pending"}</div>
                        <div className="watchlist-cell-detail">{getRefreshCopy(item.isStale, item.refresh.reason)}</div>
                        <div className="watchlist-cell-detail">{formatMarketContextStatus(item.market_context_status)}</div>
                      </div>
                    </td>
                    <td data-label="Actions">
                      <div className="watchlist-table-actions">
                        <button type="button" className="ticker-button" onClick={() => router.push(`/company/${encodeURIComponent(item.ticker)}`)}>
                          Workspace
                        </button>
                        <button type="button" className="ticker-button" onClick={() => router.push(`/company/${encodeURIComponent(item.ticker)}/models`)}>
                          Models
                        </button>
                        <button
                          type="button"
                          className="ticker-button"
                          onClick={() => void handleRefresh(item.ticker)}
                          disabled={refreshingTicker === item.ticker}
                        >
                          {refreshingTicker === item.ticker ? "Refreshing..." : "Refresh"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="grid-empty-state watchlist-empty-state">
            <div className="grid-empty-kicker">Filtered view</div>
            <div className="grid-empty-title">No companies in this filter</div>
            <div className="grid-empty-copy">Try another filter to view additional watchlist companies.</div>
            <div className="watchlist-empty-actions">
              <button type="button" className="ticker-button" onClick={() => setFilter("all")}>
                Show All Companies
              </button>
            </div>
          </div>
        )}

        {watchlistTickers.length ? (
          <section className="watchlist-calendar-section" aria-labelledby="watchlist-calendar-title">
            <div className="watchlist-calendar-header">
              <div className="watchlist-calendar-copy">
                <div className="watchlist-intro-kicker">Next 90 days</div>
                <div className="watchlist-calendar-title" id="watchlist-calendar-title">Events Calendar</div>
                <div className="watchlist-calendar-text">
                  Projected 10-Q or 10-K filings, known SEC 8-K events, and the next 13F reporting deadline in one date-sorted queue.
                </div>
              </div>
              <div className="watchlist-toolbar-meta">
                <span className="watchlist-toolbar-chip">Events {calendarEvents.length}</span>
              </div>
            </div>

            {calendarError ? <div className="text-muted">{calendarError}</div> : null}

            {calendarLoading ? (
              <div className="text-muted">Loading events calendar...</div>
            ) : calendarEvents.length ? (
              <div className="watchlist-calendar-list">
                {calendarEvents.map((event) => (
                  <article key={event.id} className="watchlist-calendar-item">
                    <div className="watchlist-calendar-date">{formatDate(event.date)}</div>
                    <div className="watchlist-calendar-body">
                      <div className="watchlist-calendar-pill-row">
                        <span className="pill">{formatCalendarEventType(event.event_type)}</span>
                        {event.form ? <span className="pill">{event.form}</span> : null}
                        {event.ticker ? (
                          <button
                            type="button"
                            className="watchlist-calendar-ticker"
                            onClick={() => router.push(`/company/${encodeURIComponent(event.ticker!)}`)}
                          >
                            {event.ticker}
                          </button>
                        ) : (
                          <span className="pill">Market-wide</span>
                        )}
                      </div>
                      <div className="watchlist-calendar-item-title">{event.title}</div>
                      <div className="watchlist-calendar-item-detail">
                        {event.company_name ? `${event.company_name} · ` : ""}
                        {event.detail ?? "No additional detail"}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className="grid-empty-state watchlist-empty-state watchlist-calendar-empty-state">
                <div className="grid-empty-kicker">Events calendar</div>
                <div className="grid-empty-title">No events in the next 90 days</div>
                <div className="grid-empty-copy">Projected filings or future-dated SEC events will appear here as cached company data updates.</div>
              </div>
            )}
          </section>
        ) : null}
      </Panel>
    </div>
  );
}

function toWatchlistRows(
  companies: WatchlistSummaryItemPayload[],
  notesByTicker: Record<string, { note?: string } | undefined>
): WatchlistRow[] {
  return companies.map((item) => {
    const note = notesByTicker[item.ticker]?.note ?? "";
    const hasNote = Boolean(note.trim());
    const stale = item.refresh.reason === "stale" || item.refresh.reason === "missing";
    return {
      ...item,
      notePreview: hasNote ? truncateNote(note) : null,
      hasNote,
      isStale: stale,
    } satisfies WatchlistRow;
  });
}

function truncateNote(note: string): string {
  const compact = note.trim().replace(/\s+/g, " ");
  if (compact.length <= 160) {
    return compact;
  }
  return `${compact.slice(0, 157)}...`;
}

function compareRows(left: WatchlistRow, right: WatchlistRow): number {
  if (right.alert_summary.high !== left.alert_summary.high) {
    return right.alert_summary.high - left.alert_summary.high;
  }
  if (right.alert_summary.medium !== left.alert_summary.medium) {
    return right.alert_summary.medium - left.alert_summary.medium;
  }
  if (left.isStale !== right.isStale) {
    return left.isStale ? -1 : 1;
  }
  return left.ticker.localeCompare(right.ticker);
}

function sortRows(rows: WatchlistRow[], sortBy: WatchlistSort): WatchlistRow[] {
  const copy = [...rows];
  if (sortBy === "attention") {
    return copy.sort(compareRows);
  }
  if (sortBy === "undervaluation") {
    return copy.sort((left, right) => (right.fair_value_gap ?? -999) - (left.fair_value_gap ?? -999));
  }
  if (sortBy === "quality") {
    return copy.sort((left, right) => (right.roic ?? -999) - (left.roic ?? -999));
  }
  if (sortBy === "capital-return") {
    return copy.sort((left, right) => (right.shareholder_yield ?? -999) - (left.shareholder_yield ?? -999));
  }
  return copy.sort((left, right) => (left.balance_sheet_risk ?? 999) - (right.balance_sheet_risk ?? 999));
}

function formatSigned(value: number | null): string {
  if (value === null) {
    return "—";
  }
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 2,
    signDisplay: "exceptZero",
  }).format(value);
}

function getRefreshCopy(isStale: boolean, reason: string): string {
  if (isStale) {
    return "Data should be refreshed";
  }
  if (reason === "manual") {
    return "Background refresh running";
  }
  if (reason === "fresh") {
    return "Data is fresh";
  }
  return "Ready";
}

function formatValuationMetric(value: number | null, status: string | null | undefined): string {
  if (status === "unsupported") {
    return "Unsupported";
  }
  return formatPercent(value);
}

function formatMarketContextStatus(status: WatchlistSummaryItemPayload["market_context_status"]): string {
  if (!status) {
    return "Unavailable";
  }
  const observed = status.observation_date ? ` (${formatDate(status.observation_date)})` : "";
  return `${status.label}${observed}`;
}

function sortCalendarEvents(events: WatchlistCalendarEventPayload[]): WatchlistCalendarEventPayload[] {
  return [...events].sort((left, right) => {
    if (left.date !== right.date) {
      return left.date.localeCompare(right.date);
    }
    if ((left.ticker ?? "") !== (right.ticker ?? "")) {
      return (left.ticker ?? "").localeCompare(right.ticker ?? "");
    }
    return left.title.localeCompare(right.title);
  });
}

function formatCalendarEventType(value: WatchlistCalendarEventPayload["event_type"]): string {
  if (value === "expected_filing") {
    return "Projected filing";
  }
  if (value === "sec_event") {
    return "SEC event";
  }
  return "13F deadline";
}
