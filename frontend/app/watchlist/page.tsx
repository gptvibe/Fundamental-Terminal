"use client";

import { clsx } from "clsx";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Panel } from "@/components/ui/panel";
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
  WATCHLIST_DESK_PRESETS,
  WATCHLIST_MONITORING_PROFILES,
  WATCHLIST_TRIAGE_STATES,
  type LocalWatchlistMonitoringEntry,
  type WatchlistPrimaryFilter,
  type WatchlistSort,
  type WatchlistTriageState,
} from "@/lib/watchlist-monitoring";
import type { WatchlistCalendarEventPayload, WatchlistSummaryItemPayload } from "@/lib/types";

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
    savedWatchlistViews,
    saveMonitoringEntry,
    saveWatchlistView,
    deleteWatchlistView,
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
  const [saveViewName, setSaveViewName] = useState("");
  const [activeDeskPresetKey, setActiveDeskPresetKey] = useState<string | null>(null);
  const [activeSavedViewId, setActiveSavedViewId] = useState<string | null>(null);
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
  const noteCoverageCount = useMemo(() => rows.filter((item) => item.hasNote).length, [rows]);
  const rationaleCoverageCount = useMemo(() => rows.filter((item) => item.hasRationale).length, [rows]);
  const dueCount = useMemo(() => rows.filter((item) => item.reviewState.kind === "due").length, [rows]);
  const parkedCount = useMemo(() => rows.filter((item) => item.reviewState.kind === "snoozed" || item.reviewState.kind === "hold").length, [rows]);
  const materialChangeCount = useMemo(() => rows.filter((item) => hasMaterialChange(item)).length, [rows]);

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
    setActiveDeskPresetKey(null);
    setActiveSavedViewId(null);
  }, []);

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

  function applyDeskPreset(presetKey: string) {
    const preset = WATCHLIST_DESK_PRESETS.find((item) => item.key === presetKey);
    if (!preset) {
      return;
    }

    setViewCriteria({ ...DEFAULT_WATCHLIST_VIEW_CRITERIA, ...preset.criteria });
    setActiveDeskPresetKey(preset.key);
    setActiveSavedViewId(null);
  }

  function applySavedView(viewId: string) {
    const savedView = savedWatchlistViews.find((item) => item.id === viewId);
    if (!savedView) {
      return;
    }

    setViewCriteria(savedView.criteria);
    setActiveSavedViewId(savedView.id);
    setActiveDeskPresetKey(null);
  }

  function handleSaveCurrentView() {
    const trimmedName = saveViewName.trim();
    if (!trimmedName) {
      return;
    }

    saveWatchlistView({
      name: trimmedName,
      criteria: viewCriteria,
    });
    setSaveViewName("");
    showAppToast({ message: `Saved watchlist view: ${trimmedName}`, tone: "info" });
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
      <Panel
        title="Watchlist Monitoring Workspace"
        subtitle="Recurring investor workflow for triage, rationale capture, review dates, and Research Brief change monitoring."
        variant="subtle"
      >
        <div className="watchlist-intro">
          <div className="watchlist-intro-copy">
            <div className="watchlist-intro-kicker">Recurring workflow</div>
            <div className="watchlist-intro-title">Run the list like a monitor surface, not a parking lot.</div>
            <div className="watchlist-intro-text">
              Capture why each name is here, move it through triage, set the next review date, park it with snooze or hold, and sweep fresh Research Brief filing deltas without leaving the page.
            </div>
            <div className="watchlist-intro-actions">
              <button type="button" className="ticker-button" onClick={() => router.push("/")}>
                Open Launcher
              </button>
              <button
                type="button"
                className="ticker-button"
                onClick={() => {
                  setViewCriteria(DEFAULT_WATCHLIST_VIEW_CRITERIA);
                  setActiveDeskPresetKey(null);
                  setActiveSavedViewId(null);
                }}
              >
                Reset View
              </button>
            </div>
          </div>

          <div className="watchlist-summary-strip">
            <div className="watchlist-summary-metric">
              <span className="watchlist-summary-label">Tracked</span>
              <span className="watchlist-summary-value">{summaryCounts.tracked}</span>
              <span className="watchlist-summary-detail">{noteCoverageCount} names still carry a local note from the company workspace.</span>
            </div>
            <div className="watchlist-summary-metric">
              <span className="watchlist-summary-label">Review due</span>
              <span className="watchlist-summary-value">{summaryCounts.due}</span>
              <span className="watchlist-summary-detail">Names whose next review date is due now and not parked.</span>
            </div>
            <div className="watchlist-summary-metric">
              <span className="watchlist-summary-label">Material change</span>
              <span className="watchlist-summary-value">{summaryCounts.materialChange}</span>
              <span className="watchlist-summary-detail">Rows with a fresh filing-delta signal from the Research Brief model.</span>
            </div>
            <div className="watchlist-summary-metric">
              <span className="watchlist-summary-label">Parked</span>
              <span className="watchlist-summary-value">{summaryCounts.parked}</span>
              <span className="watchlist-summary-detail">Snoozed or on hold until a date-driven re-open.</span>
            </div>
            <div className="watchlist-summary-metric">
              <span className="watchlist-summary-label">Why coverage</span>
              <span className="watchlist-summary-value">{summaryCounts.rationaleCoverage}</span>
              <span className="watchlist-summary-detail">Names with an explicit “why this is here” monitor note.</span>
            </div>
          </div>
        </div>

        <div className="watchlist-toolbar">
          <div className="watchlist-toolbar-section">
            <div className="watchlist-toolbar-label">Desk presets</div>
            <div className="watchlist-preset-row" role="group" aria-label="Watchlist desk presets">
              {WATCHLIST_DESK_PRESETS.map((preset) => (
                <button
                  key={preset.key}
                  type="button"
                  className={clsx("watchlist-preset-card", activeDeskPresetKey === preset.key && "is-active")}
                  onClick={() => applyDeskPreset(preset.key)}
                >
                  <span className="watchlist-preset-name">{preset.label}</span>
                  <span className="watchlist-preset-detail">{preset.description}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="watchlist-controls-grid">
            <label className="watchlist-field">
              <span className="watchlist-toolbar-label">Search</span>
              <input
                type="search"
                className="watchlist-field-input"
                value={viewCriteria.searchText}
                onChange={(event) => updateCriteria((current) => ({ ...current, searchText: event.target.value }))}
                placeholder="Ticker, company, rationale, note, or material-change text"
                aria-label="Search watchlist workspace"
              />
            </label>
            <label className="watchlist-field">
              <span className="watchlist-toolbar-label">Sort focus</span>
              <select
                className="watchlist-sort-select"
                value={viewCriteria.sortBy}
                onChange={(event) => updateCriteria((current) => ({ ...current, sortBy: event.target.value as WatchlistSort }))}
                aria-label="Sort watchlist workspace"
              >
                <option value="review">Sort: Review queue</option>
                <option value="attention">Sort: Attention</option>
                <option value="undervaluation">Sort: Undervaluation</option>
                <option value="quality">Sort: Quality</option>
                <option value="capital-return">Sort: Capital return</option>
                <option value="balance-risk">Sort: Balance-sheet risk</option>
              </select>
            </label>
            <label className="watchlist-field">
              <span className="watchlist-toolbar-label">Profile filter</span>
              <select
                className="watchlist-sort-select"
                value={viewCriteria.profileKey ?? "all"}
                onChange={(event) =>
                  updateCriteria((current) => ({
                    ...current,
                    profileKey: event.target.value === "all" ? null : event.target.value as LocalWatchlistMonitoringEntry["profileKey"],
                  }))
                }
                aria-label="Filter by monitoring profile"
              >
                <option value="all">All profiles</option>
                {WATCHLIST_MONITORING_PROFILES.map((profile) => (
                  <option key={profile.key} value={profile.key}>{profile.label}</option>
                ))}
              </select>
            </label>
          </div>

          <div className="watchlist-filter-row" role="group" aria-label="Primary watchlist filters">
            {PRIMARY_FILTERS.map((item) => (
              <button
                key={item.key}
                type="button"
                className={clsx("ticker-button", viewCriteria.primaryFilter === item.key && "is-active")}
                onClick={() => updateCriteria((current) => ({ ...current, primaryFilter: item.key }))}
              >
                {item.label}
              </button>
            ))}
          </div>

          <div className="watchlist-filter-row" role="group" aria-label="Triage state filters">
            {WATCHLIST_TRIAGE_STATES.map((state) => {
              const isActive = viewCriteria.triageStates.includes(state);
              return (
                <button
                  key={state}
                  type="button"
                  className={clsx("ticker-button", isActive && "is-active")}
                  onClick={() =>
                    updateCriteria((current) => ({
                      ...current,
                      triageStates: isActive
                        ? current.triageStates.filter((item) => item !== state)
                        : [...current.triageStates, state],
                    }))
                  }
                >
                  {formatTriageState(state)}
                </button>
              );
            })}
          </div>

          <div className="watchlist-saved-view-shell">
            <div className="watchlist-saved-view-header">
              <div>
                <div className="watchlist-toolbar-label">Saved views</div>
                <div className="watchlist-toolbar-copy">Persist the current monitor setup for repeated sweeps.</div>
              </div>
              <div className="watchlist-saved-view-form">
                <input
                  type="text"
                  className="watchlist-field-input watchlist-saved-view-input"
                  value={saveViewName}
                  onChange={(event) => setSaveViewName(event.target.value)}
                  placeholder="Save current view as..."
                  aria-label="Saved watchlist view name"
                />
                <button type="button" className="ticker-button" onClick={handleSaveCurrentView} disabled={!saveViewName.trim()}>
                  Save View
                </button>
              </div>
            </div>

            {savedWatchlistViews.length ? (
              <div className="watchlist-saved-view-list">
                {savedWatchlistViews.map((view) => (
                  <div key={view.id} className={clsx("watchlist-saved-view-card", activeSavedViewId === view.id && "is-active")}>
                    <button type="button" className="watchlist-saved-view-apply" onClick={() => applySavedView(view.id)}>
                      <span className="watchlist-saved-view-name">{view.name}</span>
                      <span className="watchlist-saved-view-detail">{PRIMARY_FILTERS.find((item) => item.key === view.criteria.primaryFilter)?.label ?? "All"}</span>
                    </button>
                    <button
                      type="button"
                      className="watchlist-saved-view-delete"
                      onClick={() => deleteWatchlistView(view.id)}
                      aria-label={`Delete saved view ${view.name}`}
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="watchlist-toolbar-copy">No saved views yet.</div>
            )}
          </div>

          <div className="watchlist-toolbar-meta">
            <span className="watchlist-toolbar-chip">In view {filteredRows.length}</span>
            <span className="watchlist-toolbar-chip">Notes {noteCoverageCount}/{summaryCounts.tracked || 0}</span>
            <span className="watchlist-toolbar-chip">Why notes {rationaleCoverageCount}/{summaryCounts.tracked || 0}</span>
            <span className="watchlist-toolbar-chip">Filter {PRIMARY_FILTERS.find((item) => item.key === viewCriteria.primaryFilter)?.label ?? "All"}</span>
            {hasPendingRefresh ? <span className="watchlist-toolbar-chip is-live">Background refresh running</span> : null}
          </div>
        </div>

        {error ? <div className="text-muted">{error}</div> : null}

        {!watchlistTickers.length ? (
          <div className="grid-empty-state watchlist-empty-state">
            <div className="grid-empty-kicker">Watchlist</div>
            <div className="grid-empty-title">No companies saved yet</div>
            <div className="grid-empty-copy">Open any company page and use Save to My Watchlist to start your browser-local monitoring workspace.</div>
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
                  <th scope="col">Workflow</th>
                  <th scope="col">Signals</th>
                  <th scope="col">Material change</th>
                  <th scope="col">Valuation &amp; quality</th>
                  <th scope="col">Review</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((item) => {
                  const profile = getWatchlistMonitoringProfile(item.monitoring.profileKey);

                  return (
                    <tr
                      key={item.ticker}
                      className={clsx(item.isStale && "is-stale", item.reviewState.kind === "due" && "is-review-due")}
                    >
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
                        <div className={clsx("watchlist-table-note", item.hasNote && "has-note")}>
                          {item.notePreview ?? "No local note yet. Keep the deeper thesis on the company workspace if you need more than the monitor note."}
                        </div>
                      </td>
                      <td data-label="Workflow">
                        <div className="watchlist-cell-stack">
                          <div className="watchlist-workflow-grid">
                            <label className="watchlist-field">
                              <span className="watchlist-field-label">Triage</span>
                              <select
                                className="watchlist-inline-select"
                                value={item.monitoring.triageState}
                                onChange={(event) => persistMonitoring(item, { triageState: event.target.value as WatchlistTriageState })}
                                aria-label={`Triage state for ${item.ticker}`}
                              >
                                {WATCHLIST_TRIAGE_STATES.map((state) => (
                                  <option key={state} value={state}>{formatTriageState(state)}</option>
                                ))}
                              </select>
                            </label>
                            <label className="watchlist-field">
                              <span className="watchlist-field-label">Profile</span>
                              <select
                                className="watchlist-inline-select"
                                value={item.monitoring.profileKey ?? "none"}
                                onChange={(event) => {
                                  const profileKey = event.target.value === "none" ? null : event.target.value as LocalWatchlistMonitoringEntry["profileKey"];
                                  const nextProfile = getWatchlistMonitoringProfile(profileKey);
                                  persistMonitoring(item, {
                                    profileKey,
                                    triageState: nextProfile?.triageState ?? item.monitoring.triageState,
                                    nextReviewAt: nextProfile ? addDaysDateKey(nextProfile.cadenceDays) : item.monitoring.nextReviewAt,
                                  });
                                }}
                                aria-label={`Monitoring profile for ${item.ticker}`}
                              >
                                <option value="none">No profile</option>
                                {WATCHLIST_MONITORING_PROFILES.map((definition) => (
                                  <option key={definition.key} value={definition.key}>{definition.label}</option>
                                ))}
                              </select>
                            </label>
                          </div>
                          <div className="watchlist-field">
                            <span className="watchlist-field-label">Why this name is here</span>
                            <input
                              type="text"
                              className="watchlist-inline-input"
                              defaultValue={item.monitoring.rationale}
                              onBlur={(event) => {
                                if (event.target.value.trim() !== item.monitoring.rationale.trim()) {
                                  persistMonitoring(item, { rationale: event.target.value });
                                }
                              }}
                              placeholder="Catalyst, valuation gap, quality thesis, or risk to monitor"
                              aria-label={`Why ${item.ticker} is on the monitor`}
                            />
                          </div>
                          <div className="watchlist-cell-detail">
                            {profile ? profile.description : "Pick a profile if you want a default review cadence and workflow posture."}
                          </div>
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
                      <td data-label="Material change">
                        <div className="watchlist-cell-stack">
                          <div className={clsx("watchlist-material-card", item.material_change?.status === "warming" && "is-warming")}>
                            <div className="watchlist-material-headline">{item.material_change?.headline ?? "Research Brief change digest warming."}</div>
                            <div className="watchlist-cell-detail">{item.material_change?.detail ?? "Material filing deltas will appear after the brief cache is ready."}</div>
                            <div className="watchlist-alert-row">
                              <span className="pill">Signal {item.material_change?.high_signal_change_count ?? 0}</span>
                              <span className="pill">Risk {item.material_change?.new_risk_indicator_count ?? 0}</span>
                              <span className="pill">Share {item.material_change?.share_count_change_count ?? 0}</span>
                              <span className="pill">Capital {item.material_change?.capital_structure_change_count ?? 0}</span>
                            </div>
                          </div>
                          {item.material_change?.highlights?.length ? (
                            <div className="watchlist-highlight-list">
                              {item.material_change.highlights.map((highlight) => (
                                <div key={`${item.ticker}:${highlight.title}`} className="watchlist-highlight-item">
                                  <div className="watchlist-highlight-title">{highlight.title}</div>
                                  <div className="watchlist-cell-detail">{highlight.why_it_matters ?? highlight.summary}</div>
                                </div>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      </td>
                      <td data-label="Valuation & quality" className="watchlist-number-cell">
                        <div className="watchlist-cell-stack">
                          <div className="watchlist-metric-line">
                            <span>Gap</span>
                            <strong>{formatValuationMetric(item.fair_value_gap, item.fair_value_gap_status)}</strong>
                          </div>
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
                          <div className="watchlist-cell-detail">
                            Coverage {item.coverage.financial_periods.toLocaleString()} periods · {item.coverage.price_points.toLocaleString()} price points
                          </div>
                        </div>
                      </td>
                      <td data-label="Review">
                        <div className="watchlist-cell-stack">
                          <div className="watchlist-review-banner">
                            <span className={clsx("pill", `tone-${item.reviewState.kind}`)}>{item.reviewState.label}</span>
                            <span className="watchlist-cell-detail">{item.reviewState.detail}</span>
                          </div>
                          <div className="watchlist-cell-note">Last reviewed {item.monitoring.lastReviewedAt ? formatDate(item.monitoring.lastReviewedAt) : "Never"}</div>
                          <div className="watchlist-cell-detail">Last checked {item.last_checked ? formatDate(item.last_checked) : "Pending"}</div>
                          <div className="watchlist-cell-detail">{getRefreshCopy(item.isStale, item.refresh.reason)}</div>
                          <div className="watchlist-cell-detail">{formatMarketContextStatus(item.market_context_status)}</div>
                          <label className="watchlist-field">
                            <span className="watchlist-field-label">Next review</span>
                            <input
                              type="date"
                              className="watchlist-inline-input"
                              value={normalizeDateInputValue(item.monitoring.nextReviewAt)}
                              onChange={(event) => persistMonitoring(item, { nextReviewAt: event.target.value || null })}
                              aria-label={`Next review for ${item.ticker}`}
                            />
                          </label>
                          <div className="watchlist-review-actions">
                            <button type="button" className="ticker-button" onClick={() => applyReviewNow(item)} aria-label={`Review ${item.ticker} now`}>
                              Review now
                            </button>
                            <button type="button" className="ticker-button" onClick={() => applySnooze(item, 7)} aria-label={`Snooze ${item.ticker} for 7 days`}>
                              Snooze 7d
                            </button>
                            <button type="button" className="ticker-button" onClick={() => applyHold(item, 30)} aria-label={`Put ${item.ticker} on hold for 30 days`}>
                              Hold 30d
                            </button>
                            {(item.reviewState.kind === "snoozed" || item.reviewState.kind === "hold") ? (
                              <button type="button" className="ticker-button" onClick={() => clearPause(item)} aria-label={`Clear pause for ${item.ticker}`}>
                                Clear pause
                              </button>
                            ) : null}
                          </div>
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
                  );
                })}
              </tbody>
            </table>
          </div>
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
                  setActiveDeskPresetKey(null);
                  setActiveSavedViewId(null);
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
      </Panel>
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