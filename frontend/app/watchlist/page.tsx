"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { Panel } from "@/components/ui/panel";
import { useLocalUserData } from "@/hooks/use-local-user-data";
import { getWatchlistSummary, refreshCompany } from "@/lib/api";
import { showAppToast } from "@/lib/app-toast";
import { formatDate, formatPercent } from "@/lib/format";
import type { WatchlistSummaryItemPayload } from "@/lib/types";

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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
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
        setError(null);
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        setError(null);
        const response = await getWatchlistSummary(watchlistTickers);
        if (cancelled) {
          return;
        }

        setRows(toWatchlistRows(response.companies, notesByTicker));
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError instanceof Error ? nextError.message : "Unable to load watchlist summary");
          setRows([]);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
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
        const response = await getWatchlistSummary(watchlistTickers);
        if (cancelled) {
          return;
        }
        setRows(toWatchlistRows(response.companies, notesByTicker));
        setError(null);
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError instanceof Error ? nextError.message : "Unable to auto-refresh watchlist summary");
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

  async function handleRefresh(ticker: string) {
    try {
      setRefreshingTicker(ticker);
      await refreshCompany(ticker);
      showAppToast({ message: `${ticker} refresh queued.`, tone: "info" });
      const response = await getWatchlistSummary(watchlistTickers);
      setRows(toWatchlistRows(response.companies, notesByTicker));
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
        subtitle="Browser-local saved companies with alert triage, latest activity, note previews, and quick actions."
      >
        <div className="watchlist-toolbar">
          <div className="saved-companies-summary">
            <span className="pill">{watchlistTickers.length} tracked</span>
            <span className="pill">{rows.filter((item) => item.alert_summary.high > 0 || item.alert_summary.medium > 0).length} need attention</span>
            <span className="pill">{rows.filter((item) => item.isStale).length} stale</span>
            <span className="pill">{rows.filter((item) => (item.fair_value_gap ?? -1) > 0).length} undervalued</span>
          </div>
          <div className="watchlist-filter-row">
            <select value={sortBy} onChange={(event) => setSortBy(event.target.value as WatchlistSort)} aria-label="Sort watchlist">
              <option value="attention">Sort: Attention</option>
              <option value="undervaluation">Sort: Undervaluation</option>
              <option value="quality">Sort: Quality</option>
              <option value="capital-return">Sort: Capital return</option>
              <option value="balance-risk">Sort: Balance-sheet risk</option>
            </select>
          </div>
          <div className="watchlist-filter-row" role="tablist" aria-label="Watchlist filters">
            {FILTERS.map((item) => (
              <button
                key={item.key}
                type="button"
                className={`ticker-button${filter === item.key ? " is-active" : ""}`}
                onClick={() => setFilter(item.key)}
                aria-pressed={filter === item.key}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        {error ? <div className="text-muted">{error}</div> : null}

        {!watchlistTickers.length ? (
          <div className="grid-empty-state watchlist-empty-state">
            <div className="grid-empty-kicker">Watchlist</div>
            <div className="grid-empty-title">No companies saved yet</div>
            <div className="grid-empty-copy">Open any company page and use Save to My Watchlist to start your browser-local multi-company workspace.</div>
          </div>
        ) : loading ? (
          <div className="text-muted">Loading watchlist summary...</div>
        ) : filteredRows.length ? (
          <div className="watchlist-card-grid">
            {filteredRows.map((item) => (
              <article key={item.ticker} className="saved-company-card watchlist-company-card">
                <div className="saved-company-card-header">
                  <div className="saved-company-card-headline">
                    <div className="saved-company-card-ticker">{item.ticker}</div>
                    <div className="saved-company-card-name">{item.name ?? "Unknown company"}</div>
                  </div>
                  <div className="saved-company-card-pills">
                    {item.sector ? <span className="pill">{item.sector}</span> : null}
                    <span className="pill">{item.isStale ? "Stale" : "Fresh"}</span>
                    <span className="pill">CIK {item.cik ?? "Unknown"}</span>
                  </div>
                </div>

                <div className={`saved-company-card-note${item.hasNote ? " has-note" : ""}`}>
                  {item.notePreview ?? "No local note. Add a note from the company workspace to keep your thesis visible here."}
                </div>

                <div className="saved-company-card-meta">
                  <span>Last checked {item.last_checked ? formatDate(item.last_checked) : "Pending"}</span>
                  <span>{getRefreshCopy(item.isStale, item.refresh.reason)}</span>
                </div>

                <div className="watchlist-alert-row" aria-label={`Alert summary for ${item.ticker}`}>
                  <span className="pill">High {item.alert_summary.high}</span>
                  <span className="pill">Medium {item.alert_summary.medium}</span>
                  <span className="pill">Low {item.alert_summary.low}</span>
                  <span className="pill">Total {item.alert_summary.total}</span>
                </div>

                <div className="watchlist-latest-stack">
                  <div className="watchlist-latest-item">
                    <strong>Latest alert:</strong> {item.latest_alert?.title ?? "No current alert"}
                  </div>
                  <div className="watchlist-latest-item">
                    <strong>Latest activity:</strong>{" "}
                    {item.latest_activity
                      ? `${item.latest_activity.title}${item.latest_activity.date ? ` (${formatDate(item.latest_activity.date)})` : ""}`
                      : "No recent activity"}
                  </div>
                  <div className="watchlist-latest-item">
                    <strong>Coverage:</strong> {item.coverage.financial_periods.toLocaleString()} financial periods · {item.coverage.price_points.toLocaleString()} price points
                  </div>
                  <div className="watchlist-latest-item">
                    <strong>Valuation gap:</strong> {formatValuationMetric(item.fair_value_gap, item.fair_value_gap_status)} · <strong>ROIC:</strong> {formatPercent(item.roic)}
                  </div>
                  <div className="watchlist-latest-item">
                    <strong>Shareholder yield:</strong> {formatPercent(item.shareholder_yield)} · <strong>Implied growth:</strong> {formatValuationMetric(item.implied_growth, item.implied_growth_status)}
                  </div>
                  <div className="watchlist-latest-item">
                    <strong>Balance-sheet risk:</strong> {formatSigned(item.balance_sheet_risk)} net debt / FCF
                  </div>
                  <div className="watchlist-latest-item">
                    <strong>Market context:</strong> {formatMarketContextStatus(item.market_context_status)}
                  </div>
                </div>

                <div className="saved-company-card-actions watchlist-action-row">
                  <button type="button" className="ticker-button" onClick={() => router.push(`/company/${encodeURIComponent(item.ticker)}`)}>
                    Open Workspace
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
              </article>
            ))}
          </div>
        ) : (
          <div className="grid-empty-state watchlist-empty-state">
            <div className="grid-empty-kicker">Filtered view</div>
            <div className="grid-empty-title">No companies in this filter</div>
            <div className="grid-empty-copy">Try another filter to view additional watchlist companies.</div>
          </div>
        )}
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
