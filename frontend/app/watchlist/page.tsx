"use client";

import { clsx } from "clsx";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { EmptyState, ErrorState, LoadingSkeleton, Toolbar } from "@/components/ui/research-primitives";
import { useJobStreams } from "@/hooks/use-job-stream";
import { useLocalUserData } from "@/hooks/use-local-user-data";
import { getWatchlistCalendar, getWatchlistSummary, invalidateApiReadCache, refreshCompany } from "@/lib/api";
import { showAppToast } from "@/lib/app-toast";
import { formatDate, formatPercent } from "@/lib/format";
import { withPerformanceAuditSource } from "@/lib/performance-audit";
import {
  buildDefaultMonitoringEntry,
  DEFAULT_WATCHLIST_VIEW_CRITERIA,
  getWatchlistMonitoringProfile,
  WATCHLIST_MONITOR_TRIGGER_DEFINITIONS,
  WATCHLIST_DESK_PRESETS,
  WATCHLIST_MONITORING_PROFILES,
  WATCHLIST_TRIAGE_STATES,
  type LocalWatchlistMonitoringEntry,
  type WatchlistPrimaryFilter,
  type WatchlistSort,
  type WatchlistTriageState,
} from "@/lib/watchlist-monitoring";
import type { WatchlistCalendarEventPayload, WatchlistSummaryItemPayload } from "@/lib/types";

const WATCHLIST_PAGE_SIZE = 25;

interface WatchlistReviewState {
  kind: "due" | "scheduled" | "snoozed" | "hold" | "unplanned";
  label: string;
  detail: string;
  sortScore: number;
}

interface WatchlistRow extends WatchlistSummaryItemPayload {
  notePreview: string | null;
  hasNote: boolean;
  hasRationale: boolean;
  isStale: boolean;
  monitoring: LocalWatchlistMonitoringEntry;
  reviewState: WatchlistReviewState;
}

interface WatchlistDashboardGroups {
  needsReview: number;
  noNewSignal: number;
  missingData: number;
}

const PRIMARY_FILTERS: Array<{ key: WatchlistPrimaryFilter; label: string }> = [
  { key: "all", label: "All" },
  { key: "review-due", label: "Review due" },
  { key: "material-change", label: "Material change" },
  { key: "attention", label: "Needs attention" },
  { key: "stale", label: "Stale" },
  { key: "no-rationale", label: "No why" },
  { key: "no-note", label: "No note" },
  { key: "undervalued", label: "Undervalued" },
  { key: "quality", label: "Quality" },
  { key: "capital-return", label: "Capital return" },
  { key: "balance-risk", label: "Balance risk" },
  { key: "snoozed", label: "Snoozed" },
  { key: "hold", label: "On hold" },
];

export default function WatchlistPage() {
  const router = useRouter();
  const {
    watchlist,
    notesByTicker,
    monitoringByTicker,
    isSaved,
    toggleWatchlist,
    saveMonitoringEntry,
  } = useLocalUserData();
  const [summaryCompanies, setSummaryCompanies] = useState<WatchlistSummaryItemPayload[]>([]);
  const [calendarEvents, setCalendarEvents] = useState<WatchlistCalendarEventPayload[]>([]);
  const [loading, setLoading] = useState(true);
  const [calendarLoading, setCalendarLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [calendarError, setCalendarError] = useState<string | null>(null);
  const [refreshingTicker, setRefreshingTicker] = useState<string | null>(null);
  const [queuedJobIdsByTicker, setQueuedJobIdsByTicker] = useState<Record<string, string>>({});
  const [settledJobIds, setSettledJobIds] = useState<string[]>([]);
  const [addTickerInput, setAddTickerInput] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [viewCriteria, setViewCriteria] = useState(DEFAULT_WATCHLIST_VIEW_CRITERIA);
  const reloadAfterRefreshStateRef = useRef({ inFlight: false, queued: false });

  const watchlistTickers = useMemo(
    () => watchlist.map((item) => item.ticker.trim().toUpperCase()).filter(Boolean),
    [watchlist]
  );
  const rows = useMemo(
    () => toWatchlistRows(summaryCompanies, notesByTicker, monitoringByTicker),
    [monitoringByTicker, notesByTicker, summaryCompanies]
  );
  const pendingJobIds = useMemo(
    () =>
      [...new Set([
        ...rows
          .map((item) => item.refresh.triggered ? item.refresh.job_id : null)
          .filter((jobId): jobId is string => Boolean(jobId))
          .filter((jobId) => !settledJobIds.includes(jobId)),
        ...Object.values(queuedJobIdsByTicker).filter((jobId) => !settledJobIds.includes(jobId)),
      ])],
    [queuedJobIdsByTicker, rows, settledJobIds]
  );
  const hasPendingRefresh = pendingJobIds.length > 0;
  const { lastTerminalEvent } = useJobStreams(pendingJobIds);

  const loadWatchlistData = useCallback(
    async (source: string, showLoading: boolean) => {
      if (!watchlistTickers.length) {
        setSummaryCompanies([]);
        setCalendarEvents([]);
        setError(null);
        setCalendarError(null);
        setLoading(false);
        setCalendarLoading(false);
        setQueuedJobIdsByTicker({});
        setSettledJobIds([]);
        return;
      }

      try {
        if (showLoading) {
          setLoading(true);
          setCalendarLoading(true);
        }
        setError(null);
        setCalendarError(null);

        const [summaryResult, calendarResult] = await withPerformanceAuditSource(
          {
            pageRoute: "/watchlist",
            scenario: "watchlist_page",
            source,
          },
          () => Promise.allSettled([getWatchlistSummary(watchlistTickers), getWatchlistCalendar(watchlistTickers)])
        );

        if (summaryResult.status === "fulfilled") {
          setSummaryCompanies(summaryResult.value.companies);
          setError(null);
          setQueuedJobIdsByTicker((current) => {
            const next = { ...current };
            const liveJobIds = new Set(
              summaryResult.value.companies
                .map((item) => item.refresh.triggered ? item.refresh.job_id : null)
                .filter((jobId): jobId is string => Boolean(jobId))
            );

            for (const [ticker, jobId] of Object.entries(next)) {
              if (!liveJobIds.has(jobId)) {
                delete next[ticker];
              }
            }

            return next;
          });
        } else {
          setError(summaryResult.reason instanceof Error ? summaryResult.reason.message : "Unable to load watchlist summary");
          setSummaryCompanies([]);
        }

        if (calendarResult.status === "fulfilled") {
          setCalendarEvents(sortCalendarEvents(calendarResult.value.events));
          setCalendarError(null);
        } else {
          setCalendarError(calendarResult.reason instanceof Error ? calendarResult.reason.message : "Unable to load events calendar");
          setCalendarEvents([]);
        }
      } finally {
        if (showLoading) {
          setLoading(false);
          setCalendarLoading(false);
        }
      }
    },
    [watchlistTickers]
  );

  const reloadWatchlistAfterRefresh = useCallback(async () => {
    const reloadState = reloadAfterRefreshStateRef.current;
    if (reloadState.inFlight) {
      reloadState.queued = true;
      return;
    }

    reloadState.inFlight = true;
    try {
      do {
        reloadState.queued = false;
        invalidateApiReadCache("/watchlist/calendar");
        await loadWatchlistData("watchlist:reload-after-refresh", false);
      } while (reloadState.queued);
    } finally {
      reloadState.inFlight = false;
    }
  }, [loadWatchlistData]);

  useEffect(() => {
    let cancelled = false;

    async function loadSummary() {
      if (cancelled) {
        return;
      }

      await loadWatchlistData("watchlist:initial-load", true);
    }

    void loadSummary();
    return () => {
      cancelled = true;
    };
  }, [loadWatchlistData]);

  useEffect(() => {
    if (!lastTerminalEvent || settledJobIds.includes(lastTerminalEvent.job_id)) {
      return;
    }

    setSettledJobIds((current) => (current.includes(lastTerminalEvent.job_id) ? current : [...current, lastTerminalEvent.job_id]));
    setQueuedJobIdsByTicker((current) => {
      const next = { ...current };
      for (const [ticker, jobId] of Object.entries(next)) {
        if (jobId === lastTerminalEvent.job_id) {
          delete next[ticker];
        }
      }
      return next;
    });

    void reloadWatchlistAfterRefresh();
  }, [lastTerminalEvent, reloadWatchlistAfterRefresh, settledJobIds]);

  const filteredRows = useMemo(
    () => sortRows(rows.filter((item) => matchesViewCriteria(item, viewCriteria)), viewCriteria.sortBy),
    [rows, viewCriteria]
  );
  const totalPages = Math.max(1, Math.ceil(filteredRows.length / WATCHLIST_PAGE_SIZE));
  const pagedRows = useMemo(() => {
    const startIndex = (currentPage - 1) * WATCHLIST_PAGE_SIZE;
    return filteredRows.slice(startIndex, startIndex + WATCHLIST_PAGE_SIZE);
  }, [currentPage, filteredRows]);
  const noteCoverageCount = useMemo(() => rows.filter((item) => item.hasNote).length, [rows]);
  const rationaleCoverageCount = useMemo(() => rows.filter((item) => item.hasRationale).length, [rows]);
  const dueCount = useMemo(() => rows.filter((item) => item.reviewState.kind === "due").length, [rows]);
  const parkedCount = useMemo(() => rows.filter((item) => item.reviewState.kind === "snoozed" || item.reviewState.kind === "hold").length, [rows]);
  const materialChangeCount = useMemo(() => rows.filter((item) => hasMaterialChange(item)).length, [rows]);
  const dashboardGroups = useMemo<WatchlistDashboardGroups>(() => {
    return rows.reduce<WatchlistDashboardGroups>((result, item) => {
      const group = classifyWatchlistDashboardGroup(item);
      if (group === "missing-data") {
        result.missingData += 1;
      } else if (group === "needs-review") {
        result.needsReview += 1;
      } else {
        result.noNewSignal += 1;
      }
      return result;
    }, {
      needsReview: 0,
      noNewSignal: 0,
      missingData: 0,
    });
  }, [rows]);

  const summaryCounts = useMemo(
    () => ({
      tracked: watchlistTickers.length,
      due: dueCount,
      materialChange: materialChangeCount,
      parked: parkedCount,
      rationaleCoverage: rationaleCoverageCount,
    }),
    [dueCount, materialChangeCount, parkedCount, rationaleCoverageCount, watchlistTickers.length]
  );

  const updateCriteria = useCallback((updater: (current: typeof viewCriteria) => typeof viewCriteria) => {
    setViewCriteria((current) => updater(current));
  }, []);

  useEffect(() => {
    setCurrentPage(1);
  }, [viewCriteria]);

  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages);
    }
  }, [currentPage, totalPages]);

  function persistMonitoring(item: WatchlistRow, patch: Partial<LocalWatchlistMonitoringEntry>) {
    saveMonitoringEntry({
      ...item.monitoring,
      ...patch,
      ticker: item.ticker,
      updatedAt: new Date().toISOString(),
    });
  }

  function applyReviewNow(item: WatchlistRow) {
    const cadenceDays = getWatchlistMonitoringProfile(item.monitoring.profileKey)?.cadenceDays ?? 21;
    persistMonitoring(item, {
      lastReviewedAt: new Date().toISOString(),
      nextReviewAt: addDaysDateKey(cadenceDays),
      snoozedUntil: null,
      holdUntil: null,
    });
  }

  function applySnooze(item: WatchlistRow, days: number) {
    const nextDate = addDaysDateKey(days);
    persistMonitoring(item, {
      snoozedUntil: nextDate,
      holdUntil: null,
      nextReviewAt: nextDate,
    });
  }

  function applyHold(item: WatchlistRow, days: number) {
    const nextDate = addDaysDateKey(days);
    persistMonitoring(item, {
      holdUntil: nextDate,
      snoozedUntil: null,
      nextReviewAt: nextDate,
    });
  }

  function clearPause(item: WatchlistRow) {
    persistMonitoring(item, {
      snoozedUntil: null,
      holdUntil: null,
    });
  }

  function handleAddTicker() {
    const normalized = addTickerInput.trim().toUpperCase();
    if (!normalized) {
      return;
    }
    if (!/^[A-Z.\-]{1,10}$/.test(normalized)) {
      showAppToast({ message: "Enter a valid ticker symbol.", tone: "danger" });
      return;
    }
    if (isSaved(normalized)) {
      showAppToast({ message: `${normalized} is already on your watchlist.`, tone: "info" });
      return;
    }
    toggleWatchlist({ ticker: normalized, name: null, sector: null });
    setAddTickerInput("");
    showAppToast({ message: `${normalized} added to watchlist.`, tone: "info" });
  }

  async function handleRefresh(ticker: string) {
    try {
      setRefreshingTicker(ticker);
      const response = await withPerformanceAuditSource(
        {
          pageRoute: "/watchlist",
          scenario: "watchlist_page",
          source: "watchlist:queue-refresh",
        },
        () => refreshCompany(ticker)
      );
      if (response.refresh.job_id) {
        setQueuedJobIdsByTicker((current) => ({
          ...current,
          [ticker]: response.refresh.job_id as string,
        }));
      }
      showAppToast({ message: `${ticker} refresh queued.`, tone: "info" });
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
      <Toolbar className="watchlist-toolbar watchlist-toolbar-top" label="Watchlist toolbar">
        <label className="watchlist-field watchlist-search-field">
          <span className="watchlist-toolbar-label">Search</span>
          <input
            type="search"
            className="watchlist-field-input"
            value={viewCriteria.searchText}
            onChange={(event) => updateCriteria((current) => ({ ...current, searchText: event.target.value }))}
            placeholder="Search ticker, company, note, rationale, or filing change"
            aria-label="Search watchlist"
          />
        </label>
        <label className="watchlist-field">
          <span className="watchlist-toolbar-label">Filter</span>
          <select
            className="watchlist-sort-select"
            value={viewCriteria.primaryFilter}
            onChange={(event) => updateCriteria((current) => ({ ...current, primaryFilter: event.target.value as WatchlistPrimaryFilter }))}
            aria-label="Filter watchlist"
          >
            {PRIMARY_FILTERS.map((item) => (
              <option key={item.key} value={item.key}>{item.label}</option>
            ))}
          </select>
        </label>
        <label className="watchlist-field">
          <span className="watchlist-toolbar-label">Sort</span>
          <select
            className="watchlist-sort-select"
            value={viewCriteria.sortBy}
            onChange={(event) => updateCriteria((current) => ({ ...current, sortBy: event.target.value as WatchlistSort }))}
            aria-label="Sort watchlist"
          >
            <option value="review">Review queue</option>
            <option value="attention">Attention</option>
            <option value="undervaluation">Undervaluation</option>
            <option value="quality">Quality</option>
            <option value="capital-return">Capital return</option>
            <option value="balance-risk">Balance-sheet risk</option>
          </select>
        </label>
        <div className="watchlist-add-ticker-row">
          <label className="watchlist-field watchlist-add-ticker-field">
            <span className="watchlist-toolbar-label">Add ticker</span>
            <input
              type="text"
              className="watchlist-field-input"
              value={addTickerInput}
              onChange={(event) => setAddTickerInput(event.target.value.toUpperCase())}
              placeholder="AAPL"
              aria-label="Add ticker"
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  handleAddTicker();
                }
              }}
            />
          </label>
          <button type="button" className="ticker-button" onClick={handleAddTicker}>
            Add
          </button>
        </div>
        <div className="watchlist-toolbar-meta">
          <span className="watchlist-toolbar-chip">Tracked {summaryCounts.tracked}</span>
          <span className="watchlist-toolbar-chip">In view {filteredRows.length}</span>
          <span className="watchlist-toolbar-chip">Alerts {materialChangeCount}</span>
          <span className="watchlist-toolbar-chip">Notes {noteCoverageCount}</span>
          {hasPendingRefresh ? <span className="watchlist-toolbar-chip is-live">Background refresh running</span> : null}
        </div>
      </Toolbar>

      {watchlistTickers.length ? (
        <section className="watchlist-monitor-groups" aria-label="Watchlist monitor groups">
          <article className="watchlist-monitor-group-card">
            <div className="watchlist-monitor-group-title">Needs review</div>
            <div className="watchlist-monitor-group-value">{dashboardGroups.needsReview}</div>
            <div className="watchlist-monitor-group-detail">Due names or fresh filing, alert, and trigger signals.</div>
          </article>
          <article className="watchlist-monitor-group-card">
            <div className="watchlist-monitor-group-title">No new signal</div>
            <div className="watchlist-monitor-group-value">{dashboardGroups.noNewSignal}</div>
            <div className="watchlist-monitor-group-detail">Monitored names with no new high-signal change yet.</div>
          </article>
          <article className="watchlist-monitor-group-card">
            <div className="watchlist-monitor-group-title">Missing data</div>
            <div className="watchlist-monitor-group-value">{dashboardGroups.missingData}</div>
            <div className="watchlist-monitor-group-detail">Refresh needed before monitor conclusions are reliable.</div>
          </article>
        </section>
      ) : null}

      {error ? <ErrorState title="Watchlist summary unavailable" message={error} /> : null}

      {!watchlistTickers.length ? (
        <EmptyState
          className="watchlist-empty-state"
          title="Watchlist is empty"
          message="Add your first company to start tracking fundamentals."
          action={(
            <button type="button" className="ticker-button" onClick={() => router.push("/")}>
              Open Research Launcher
            </button>
          )}
        />
      ) : loading ? (
        <LoadingSkeleton lines={8} label="Loading watchlist" />
      ) : filteredRows.length ? (
        <>
          <div className="watchlist-table-shell">
            <table className="watchlist-table watchlist-investor-table">
              <thead>
                <tr>
                  <th scope="col">Ticker</th>
                  <th scope="col">Company</th>
                  <th scope="col">Price</th>
                  <th scope="col">Revenue growth</th>
                  <th scope="col">Margin</th>
                  <th scope="col">FCF</th>
                  <th scope="col">Leverage/debt signal</th>
                  <th scope="col">Last filing</th>
                  <th scope="col">Alert count</th>
                  <th scope="col">Monitor checklist</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {pagedRows.map((item) => {
                  const lastFiling = item.material_change?.current_period_end ? `${item.material_change.current_filing_type ?? "Filing"} ${formatDate(item.material_change.current_period_end)}` : "Unavailable";
                  return (
                    <tr
                      key={item.ticker}
                      className={clsx(item.isStale && "is-stale", item.reviewState.kind === "due" && "is-review-due")}
                    >
                      <td data-label="Ticker">
                        <button type="button" className="watchlist-company-link" onClick={() => router.push(`/company/${encodeURIComponent(item.ticker)}`)}>
                          <span className="watchlist-table-ticker">{item.ticker}</span>
                        </button>
                      </td>
                      <td data-label="Company">
                        <button type="button" className="watchlist-company-link" onClick={() => router.push(`/company/${encodeURIComponent(item.ticker)}`)}>
                          <span className="watchlist-table-name">{item.name ?? "Unknown company"}</span>
                        </button>
                        <div className="watchlist-table-meta">
                          {item.sector ? <span className="pill">{item.sector}</span> : null}
                          <span className="pill">{item.isStale ? "Stale" : "Fresh"}</span>
                        </div>
                      </td>
                      <td data-label="Price" className="watchlist-number-cell">Unavailable</td>
                      <td data-label="Revenue growth" className="watchlist-number-cell">{formatPercent(item.implied_growth)}</td>
                      <td data-label="Margin" className="watchlist-number-cell">{formatPercent(item.roic)}</td>
                      <td data-label="FCF" className="watchlist-number-cell">{formatPercent(item.shareholder_yield)}</td>
                      <td data-label="Leverage/debt signal" className="watchlist-number-cell">{formatSigned(item.balance_sheet_risk)}</td>
                      <td data-label="Last filing">{lastFiling}</td>
                      <td data-label="Alert count" className="watchlist-number-cell">{item.alert_summary.total}</td>
                      <td data-label="Monitor checklist">
                        <div className="watchlist-monitor-checklist">
                          <div className="watchlist-monitor-trigger-grid">
                            {WATCHLIST_MONITOR_TRIGGER_DEFINITIONS.map((trigger) => {
                              const checked = item.monitoring.triggers[trigger.key];
                              return (
                                <label key={`${item.ticker}:${trigger.key}`} className="watchlist-monitor-trigger-toggle">
                                  <input
                                    type="checkbox"
                                    checked={checked}
                                    onChange={(event) => {
                                      persistMonitoring(item, {
                                        triggers: {
                                          ...item.monitoring.triggers,
                                          [trigger.key]: event.target.checked,
                                        },
                                      });
                                    }}
                                  />
                                  <span>{trigger.label}</span>
                                </label>
                              );
                            })}
                          </div>
                          <label className="watchlist-monitor-note-field">
                            <span className="watchlist-monitor-note-label">Custom note</span>
                            <input
                              type="text"
                              className="watchlist-inline-input"
                              value={item.monitoring.triggers.customNote}
                              onChange={(event) => {
                                persistMonitoring(item, {
                                  triggers: {
                                    ...item.monitoring.triggers,
                                    customNote: event.target.value,
                                  },
                                });
                              }}
                              placeholder="What should you revisit next?"
                              aria-label={`Custom monitor note for ${item.ticker}`}
                            />
                          </label>
                          <div className="watchlist-monitor-trigger-summary">
                            {getTriggerSummary(item.monitoring)}
                          </div>
                        </div>
                      </td>
                      <td data-label="Actions">
                        <div className="watchlist-table-actions">
                          <button type="button" className="ticker-button" onClick={() => router.push(`/company/${encodeURIComponent(item.ticker)}`)}>
                            Workspace
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
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="watchlist-pagination" role="navigation" aria-label="Watchlist pages">
            <button type="button" className="ticker-button" onClick={() => setCurrentPage((current) => Math.max(1, current - 1))} disabled={currentPage <= 1}>
              Previous
            </button>
            <span className="watchlist-toolbar-chip">Page {currentPage} of {totalPages}</span>
            <button type="button" className="ticker-button" onClick={() => setCurrentPage((current) => Math.min(totalPages, current + 1))} disabled={currentPage >= totalPages}>
              Next
            </button>
          </div>

          <div className="watchlist-lower-grid">
            <section className="watchlist-lower-section" aria-labelledby="watchlist-recent-changes-title">
              <h2 id="watchlist-recent-changes-title" className="watchlist-lower-title">Recent changes</h2>
              <div className="watchlist-lower-list">
                {rows.filter((item) => item.material_change?.headline).slice(0, 8).map((item) => (
                  <article key={`${item.ticker}:change`} className="watchlist-lower-item">
                    <button type="button" className="watchlist-calendar-ticker" onClick={() => router.push(`/company/${encodeURIComponent(item.ticker)}`)}>{item.ticker}</button>
                    <div className="watchlist-cell-detail">{item.material_change?.headline}</div>
                  </article>
                ))}
                {!rows.some((item) => item.material_change?.headline) ? <div className="watchlist-cell-detail">No recent filing deltas yet.</div> : null}
              </div>
            </section>

            <section className="watchlist-lower-section" aria-labelledby="watchlist-alerts-title">
              <h2 id="watchlist-alerts-title" className="watchlist-lower-title">Alerts</h2>
              <div className="watchlist-lower-list">
                {rows.filter((item) => item.alert_summary.total > 0).slice(0, 8).map((item) => (
                  <article key={`${item.ticker}:alert`} className="watchlist-lower-item">
                    <button type="button" className="watchlist-calendar-ticker" onClick={() => router.push(`/company/${encodeURIComponent(item.ticker)}`)}>{item.ticker}</button>
                    <div className="watchlist-cell-detail">{item.latest_alert?.title ?? "Alert queued"}</div>
                    <div className="watchlist-alert-row">
                      <span className="pill">H {item.alert_summary.high}</span>
                      <span className="pill">M {item.alert_summary.medium}</span>
                      <span className="pill">L {item.alert_summary.low}</span>
                    </div>
                  </article>
                ))}
                {!rows.some((item) => item.alert_summary.total > 0) ? <div className="watchlist-cell-detail">No active alerts.</div> : null}
              </div>
            </section>

            <section className="watchlist-lower-section" aria-labelledby="watchlist-notes-title">
              <h2 id="watchlist-notes-title" className="watchlist-lower-title">Notes</h2>
              <div className="watchlist-lower-list">
                {rows.filter((item) => item.notePreview || item.monitoring.rationale.trim()).slice(0, 8).map((item) => (
                  <article key={`${item.ticker}:note`} className="watchlist-lower-item">
                    <button type="button" className="watchlist-calendar-ticker" onClick={() => router.push(`/company/${encodeURIComponent(item.ticker)}`)}>{item.ticker}</button>
                    <div className="watchlist-cell-detail">{item.monitoring.rationale || item.notePreview || "No note yet."}</div>
                  </article>
                ))}
                {!rows.some((item) => item.notePreview || item.monitoring.rationale.trim()) ? <div className="watchlist-cell-detail">No notes yet.</div> : null}
              </div>
            </section>
          </div>
        </>
      ) : (
          <div className="grid-empty-state watchlist-empty-state">
            <div className="grid-empty-kicker">Filtered view</div>
            <div className="grid-empty-title">No companies in this view</div>
            <div className="grid-empty-copy">Try another preset, filter, or saved view to surface additional names.</div>
            <div className="watchlist-empty-actions">
              <button
                type="button"
                className="ticker-button"
                onClick={() => {
                  setViewCriteria(DEFAULT_WATCHLIST_VIEW_CRITERIA);
                }}
              >
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
    </div>
  );
}

function toWatchlistRows(
  companies: WatchlistSummaryItemPayload[],
  notesByTicker: Record<string, { note?: string } | undefined>,
  monitoringByTicker: Record<string, LocalWatchlistMonitoringEntry | undefined>
): WatchlistRow[] {
  return companies.map((item) => {
    const note = notesByTicker[item.ticker]?.note ?? "";
    const hasNote = Boolean(note.trim());
    const stale = item.refresh.reason === "stale" || item.refresh.reason === "missing";
    const monitoring = monitoringByTicker[item.ticker] ?? buildDefaultMonitoringEntry(item.ticker);
    return {
      ...item,
      notePreview: hasNote ? truncateNote(note) : null,
      hasNote,
      hasRationale: Boolean(monitoring.rationale.trim()),
      isStale: stale,
      monitoring,
      reviewState: buildReviewState(monitoring),
    } satisfies WatchlistRow;
  });
}

function matchesViewCriteria(item: WatchlistRow, criteria: typeof DEFAULT_WATCHLIST_VIEW_CRITERIA): boolean {
  if (criteria.triageStates.length && !criteria.triageStates.includes(item.monitoring.triageState)) {
    return false;
  }
  if (criteria.profileKey && item.monitoring.profileKey !== criteria.profileKey) {
    return false;
  }
  if (criteria.searchText.trim()) {
    const needle = criteria.searchText.trim().toLowerCase();
    const haystack = [
      item.ticker,
      item.name,
      item.sector,
      item.monitoring.rationale,
      item.notePreview,
      item.latest_alert?.title,
      item.latest_activity?.title,
      item.material_change?.headline,
      item.material_change?.detail,
      ...(item.material_change?.highlights.map((highlight) => `${highlight.title} ${highlight.summary} ${highlight.why_it_matters ?? ""}`) ?? []),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();

    if (!haystack.includes(needle)) {
      return false;
    }
  }

  if (criteria.primaryFilter === "all") {
    return true;
  }
  if (criteria.primaryFilter === "review-due") {
    return item.reviewState.kind === "due";
  }
  if (criteria.primaryFilter === "attention") {
    return item.alert_summary.high > 0 || item.alert_summary.medium > 0;
  }
  if (criteria.primaryFilter === "stale") {
    return item.isStale;
  }
  if (criteria.primaryFilter === "material-change") {
    return hasMaterialChange(item);
  }
  if (criteria.primaryFilter === "no-note") {
    return !item.hasNote;
  }
  if (criteria.primaryFilter === "no-rationale") {
    return !item.hasRationale;
  }
  if (criteria.primaryFilter === "undervalued") {
    return (item.fair_value_gap ?? -1) > 0;
  }
  if (criteria.primaryFilter === "quality") {
    return (item.roic ?? -1) > 0.12;
  }
  if (criteria.primaryFilter === "capital-return") {
    return (item.shareholder_yield ?? -1) > 0.01;
  }
  if (criteria.primaryFilter === "balance-risk") {
    return (item.balance_sheet_risk ?? 0) > 3;
  }
  if (criteria.primaryFilter === "snoozed") {
    return item.reviewState.kind === "snoozed";
  }
  return item.reviewState.kind === "hold";
}

function hasMaterialChange(item: WatchlistRow): boolean {
  if (!item.material_change || item.material_change.status !== "ready") {
    return false;
  }
  return [
    item.material_change.high_signal_change_count,
    item.material_change.new_risk_indicator_count,
    item.material_change.share_count_change_count,
    item.material_change.capital_structure_change_count,
    item.material_change.comment_letter_count,
  ].some((count) => count > 0);
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
  if (sortBy === "review") {
    return copy.sort((left, right) => {
      if (left.reviewState.sortScore !== right.reviewState.sortScore) {
        return left.reviewState.sortScore - right.reviewState.sortScore;
      }
      const leftDate = reviewDateSortValue(left.monitoring);
      const rightDate = reviewDateSortValue(right.monitoring);
      if (leftDate !== rightDate) {
        return leftDate - rightDate;
      }
      return compareRows(left, right);
    });
  }
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

function buildReviewState(monitoring: LocalWatchlistMonitoringEntry): WatchlistReviewState {
  const today = startOfToday();
  const holdUntil = parseDateOnly(monitoring.holdUntil);
  if (holdUntil && holdUntil >= today) {
    return {
      kind: "hold",
      label: `On hold until ${formatDate(holdUntil.toISOString())}`,
      detail: "The name is intentionally parked until the hold date expires.",
      sortScore: 4,
    };
  }

  const snoozedUntil = parseDateOnly(monitoring.snoozedUntil);
  if (snoozedUntil && snoozedUntil >= today) {
    return {
      kind: "snoozed",
      label: `Snoozed until ${formatDate(snoozedUntil.toISOString())}`,
      detail: "The row is temporarily muted until the snooze date.",
      sortScore: 3,
    };
  }

  const nextReview = parseDateOnly(monitoring.nextReviewAt);
  if (nextReview) {
    if (nextReview <= today) {
      return {
        kind: "due",
        label: `Due ${formatDate(nextReview.toISOString())}`,
        detail: "Move the thesis forward, park it, or set a fresh cadence.",
        sortScore: 0,
      };
    }
    return {
      kind: "scheduled",
      label: `Next review ${formatDate(nextReview.toISOString())}`,
      detail: "Scheduled and active.",
      sortScore: 1,
    };
  }

  if (monitoring.lastReviewedAt) {
    return {
      kind: "unplanned",
      label: "Reviewed, no next date",
      detail: "Set the next review date so the queue stays explicit.",
      sortScore: 2,
    };
  }

  return {
    kind: "unplanned",
    label: "Needs first review",
    detail: "Capture why the name is here and set the next checkpoint.",
    sortScore: 2,
  };
}

function reviewDateSortValue(monitoring: LocalWatchlistMonitoringEntry): number {
  return parseDateOnly(monitoring.nextReviewAt)?.getTime() ?? Number.MAX_SAFE_INTEGER;
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

function formatTriageState(value: WatchlistTriageState): string {
  if (value === "inbox") {
    return "Inbox";
  }
  if (value === "reviewing") {
    return "Reviewing";
  }
  if (value === "monitoring") {
    return "Monitoring";
  }
  return "Ready";
}

function normalizeDateInputValue(value: string | null): string {
  if (!value) {
    return "";
  }
  const parsed = parseDateOnly(value);
  return parsed ? toDateKey(parsed) : "";
}

function addDaysDateKey(days: number): string {
  const next = startOfToday();
  next.setDate(next.getDate() + days);
  return toDateKey(next);
}

function parseDateOnly(value: string | null): Date | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
}

function startOfToday(): Date {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

function toDateKey(value: Date): string {
  const year = value.getFullYear();
  const month = `${value.getMonth() + 1}`.padStart(2, "0");
  const day = `${value.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function classifyWatchlistDashboardGroup(item: WatchlistRow): "needs-review" | "no-new-signal" | "missing-data" {
  if (isMissingSignalData(item)) {
    return "missing-data";
  }

  if (item.reviewState.kind === "due" || hasNewSignal(item)) {
    return "needs-review";
  }

  return "no-new-signal";
}

function isMissingSignalData(item: WatchlistRow): boolean {
  return item.refresh.reason === "missing" || !item.material_change || item.material_change.status !== "ready";
}

function hasNewSignal(item: WatchlistRow): boolean {
  if (item.alert_summary.total > 0) {
    return true;
  }
  if (hasMaterialChange(item)) {
    return true;
  }
  return countEnabledTriggers(item.monitoring) > 0;
}

function countEnabledTriggers(monitoring: LocalWatchlistMonitoringEntry): number {
  return WATCHLIST_MONITOR_TRIGGER_DEFINITIONS.reduce((count, trigger) => (
    monitoring.triggers[trigger.key] ? count + 1 : count
  ), 0);
}

function getTriggerSummary(monitoring: LocalWatchlistMonitoringEntry): string {
  const enabledCount = countEnabledTriggers(monitoring);
  if (enabledCount === 0 && !monitoring.triggers.customNote.trim()) {
    return "No monitor triggers selected.";
  }

  const noteSuffix = monitoring.triggers.customNote.trim() ? " Custom note saved." : "";
  return `${enabledCount} trigger${enabledCount === 1 ? "" : "s"} selected.${noteSuffix}`;
}