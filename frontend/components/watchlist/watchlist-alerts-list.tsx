import { clsx } from "clsx";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { WatchlistAlertPayload, WatchlistAlertsResponse } from "@/lib/types";
import { getWatchlistAlerts } from "@/lib/api/watchlist";
import { formatDate } from "@/lib/format";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui/research-primitives";

interface WatchlistAlertsListProps {
  tickers: string[];
  onRefresh?: () => void;
  isLoading?: boolean;
  error?: string | null;
}

export type AlertSortBy = "recent" | "oldest" | "type" | "ticker";
export type AlertShowMode = "unread" | "all";

export const ALERT_TYPE_LABELS: Record<string, { label: string; color: string; icon: string; priority: number }> = {
  "late-filing": {
    label: "Late Filing Notice",
    color: "bg-red-100 text-red-900",
    icon: "⏰",
    priority: 5,
  },
  "8-K": {
    label: "Current Report",
    color: "bg-purple-100 text-purple-900",
    icon: "⚡",
    priority: 4,
  },
  amendment: {
    label: "Amended Filing",
    color: "bg-yellow-100 text-yellow-900",
    icon: "✏️",
    priority: 3,
  },
  "form-4": {
    label: "Insider Transaction",
    color: "bg-orange-100 text-orange-900",
    icon: "👤",
    priority: 2,
  },
  "10-K": {
    label: "Annual Report",
    color: "bg-blue-100 text-blue-900",
    icon: "📄",
    priority: 1,
  },
  "10-Q": {
    label: "Quarterly Report",
    color: "bg-blue-100 text-blue-900",
    icon: "📊",
    priority: 1,
  },
  proxy: {
    label: "Proxy Statement",
    color: "bg-green-100 text-green-900",
    icon: "🗳️",
    priority: 1,
  },
  "stale-data": {
    label: "Stale Data",
    color: "bg-gray-100 text-gray-900",
    icon: "⚠️",
    priority: 0,
  },
};

export function WatchlistAlertsList({
  tickers,
  onRefresh,
  isLoading = false,
  error = null,
}: WatchlistAlertsListProps) {
  const [alerts, setAlerts] = useState<WatchlistAlertPayload[]>([]);
  const [selectedTypes, setSelectedTypes] = useState<Set<string>>(new Set());
  const [sortBy, setSortBy] = useState<AlertSortBy>("recent");
  const [showMode, setShowMode] = useState<AlertShowMode>("unread");
  const [loading, setLoading] = useState(isLoading);
  const [loadError, setLoadError] = useState<string | null>(error);

  const filteredAndSortedAlerts = useMemo(() => {
    let result = alerts;

    // Apply type filter
    if (selectedTypes.size > 0) {
      result = result.filter((a) => selectedTypes.has(a.alert_type));
    }

    // Apply show mode filter
    if (showMode === "unread") {
      result = result.filter((a) => a.dismissed_at === null);
    }

    // Apply sorting
    result.sort((a, b) => {
      switch (sortBy) {
        case "recent":
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        case "oldest":
          return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
        case "type": {
          const typeA = ALERT_TYPE_LABELS[a.alert_type]?.priority || 0;
          const typeB = ALERT_TYPE_LABELS[b.alert_type]?.priority || 0;
          if (typeA !== typeB) return typeB - typeA;
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        }
        case "ticker":
          if (a.ticker !== b.ticker) return a.ticker.localeCompare(b.ticker);
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        default:
          return 0;
      }
    });

    return result;
  }, [alerts, selectedTypes, sortBy, showMode]);

  const alertTypesSummary = useMemo(() => {
    const summary: Record<string, number> = {};
    for (const alert of alerts) {
      summary[alert.alert_type] = (summary[alert.alert_type] || 0) + 1;
    }
    return summary;
  }, [alerts]);

  const unreadCount = useMemo(() => {
    return alerts.filter((a) => a.dismissed_at === null).length;
  }, [alerts]);

  const loadAlerts = useCallback(async () => {
    if (tickers.length === 0) {
      setAlerts([]);
      return;
    }

    setLoading(true);
    setLoadError(null);

    try {
      const response = await getWatchlistAlerts(
        tickers,
        selectedTypes.size > 0 ? Array.from(selectedTypes) : undefined
      );
      setAlerts(response.alerts);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load alerts";
      setLoadError(message);
      setAlerts([]);
    } finally {
      setLoading(false);
    }
  }, [tickers, selectedTypes]);

  // Load alerts on mount and when tickers/filters change
  useEffect(() => {
    loadAlerts();
  }, [loadAlerts]);

  const toggleAlertType = useCallback((type: string) => {
    setSelectedTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  }, []);

  if (loading) {
    return (
      <div className="space-y-4">
        <LoadingSkeleton lines={3} />
      </div>
    );
  }

  if (loadError) {
    return <ErrorState title="Unable to load alerts" message={loadError} />;
  }

  if (alerts.length === 0) {
    return (
      <EmptyState
        title="No alerts"
        message="No watchlist alerts for these companies."
      />
    );
  }

  return (
    <div className="space-y-4">
      {/* Controls Section */}
      <div className="space-y-3 pb-3 border-b">
        {/* Show Mode Toggle */}
        <div className="flex gap-2">
          <button
            onClick={() => setShowMode("unread")}
            className={clsx(
              "px-3 py-1 rounded text-sm font-medium transition-colors",
              showMode === "unread"
                ? "bg-blue-600 text-white"
                : "bg-gray-200 text-gray-700 hover:bg-gray-300"
            )}
          >
            Unread ({unreadCount})
          </button>
          <button
            onClick={() => setShowMode("all")}
            className={clsx(
              "px-3 py-1 rounded text-sm font-medium transition-colors",
              showMode === "all"
                ? "bg-blue-600 text-white"
                : "bg-gray-200 text-gray-700 hover:bg-gray-300"
            )}
          >
            All ({alerts.length})
          </button>
        </div>

        {/* Sort Options */}
        <div className="flex gap-2 items-center">
          <label className="text-sm font-medium text-gray-700">Sort:</label>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as AlertSortBy)}
            className="px-2 py-1 text-sm border rounded bg-white"
          >
            <option value="recent">Most Recent</option>
            <option value="oldest">Oldest First</option>
            <option value="type">By Importance</option>
            <option value="ticker">By Ticker</option>
          </select>
        </div>
      </div>

      {/* Alert Type Filter */}
      <div className="flex flex-wrap gap-2">
        {Object.entries(ALERT_TYPE_LABELS)
          .sort((a, b) => b[1].priority - a[1].priority)
          .map(([type, { label, color }]) => {
            const count = alertTypesSummary[type] || 0;
            if (count === 0) return null;

            const isSelected = selectedTypes.has(type);
            return (
              <button
                key={type}
                onClick={() => toggleAlertType(type)}
                className={clsx(
                  "px-3 py-1 rounded-full text-sm font-medium transition-all",
                  isSelected
                    ? `${color} ring-2 ring-offset-1 ring-current`
                    : "bg-gray-200 text-gray-600 opacity-60 hover:opacity-80"
                )}
                title={`Filter by ${label}`}
              >
                {label} ({count})
              </button>
            );
          })}
      </div>

      {/* Alerts List */}
      <div className="space-y-2">
        {filteredAndSortedAlerts.length === 0 ? (
          <EmptyState title="No alerts match your filters" message="Adjust your filter selections to see more alerts." />
        ) : (
          filteredAndSortedAlerts.map((alert) => {
            const typeInfo = ALERT_TYPE_LABELS[alert.alert_type] || ALERT_TYPE_LABELS["stale-data"];
            const isDismissed = alert.dismissed_at !== null;

            return (
              <div
                key={alert.id}
                className={clsx(
                  "flex items-start gap-3 p-3 rounded-lg border transition-opacity",
                  isDismissed
                    ? "opacity-50 bg-gray-50 border-gray-200"
                    : `${typeInfo.color} border-current`
                )}
              >
                <span className="text-xl flex-shrink-0">{typeInfo.icon}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <h4 className="font-semibold text-sm">{alert.title}</h4>
                      <p className="text-xs text-gray-600">{alert.ticker}</p>
                    </div>
                    <span className="text-xs text-gray-500 flex-shrink-0">
                      {formatDate(alert.created_at)}
                    </span>
                  </div>
                  <p className="text-sm text-gray-700 mt-1">{alert.detail}</p>
                  {alert.source_filing_accession && (
                    <p className="text-xs text-gray-600 mt-1">
                      Accession: {alert.source_filing_accession}
                    </p>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Summary Footer */}
      <div className="text-xs text-gray-600 pt-2 border-t">
        Showing {filteredAndSortedAlerts.length} of {alerts.length} alerts
        {selectedTypes.size > 0 && (
          <button
            onClick={() => setSelectedTypes(new Set())}
            className="ml-2 text-blue-600 hover:underline"
          >
            Clear filters
          </button>
        )}
      </div>
    </div>
  );
}

export function WatchlistAlertsBadge({
  count,
  className,
}: {
  count: number;
  className?: string;
}) {
  if (count === 0) return null;

  return (
    <span
      className={clsx(
        "inline-flex items-center justify-center w-5 h-5 rounded-full bg-red-500 text-white text-xs font-bold",
        className
      )}
    >
      {count > 9 ? "9+" : count}
    </span>
  );
}
