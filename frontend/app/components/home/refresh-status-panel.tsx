"use client";

import { useMemo } from "react";

import { formatDate } from "@/lib/format";
import type { WatchlistSummaryItemPayload } from "@/lib/types";
import "./refresh-status-panel.css";

interface RefreshStatusPanelProps {
  watchlistTickers: string[];
  summaryItems: WatchlistSummaryItemPayload[];
  summaryLoading: boolean;
  summaryError: string | null;
}

export function RefreshStatusPanel({
  watchlistTickers,
  summaryItems,
  summaryLoading,
  summaryError,
}: RefreshStatusPanelProps) {
  // Track refresh statuses from watchlist items
  const refreshStatus = useMemo(() => {
    const statuses = summaryItems
      .filter((item) => item.refresh?.triggered)
      .map((item) => ({
        ticker: item.ticker,
        reason: item.refresh?.reason || "refreshing",
        triggered: item.refresh?.triggered || false,
      }));

    return statuses;
  }, [summaryItems]);

  return (
    <section className="home-refresh-status-panel">
      <h2 className="home-refresh-status-title">Refresh Status</h2>

      {/* Refresh indicator */}
      <div className="home-refresh-connection-status">
        {refreshStatus.length > 0 ? (
          <>
            <div className="home-refresh-connection-dot home-refresh-connection-open" />
            <span className="home-refresh-connection-text">
              {refreshStatus.length} {refreshStatus.length === 1 ? "company" : "companies"} refreshing
            </span>
          </>
        ) : (
          <>
            <div className="home-refresh-connection-dot home-refresh-connection-idle" />
            <span className="home-refresh-connection-text">All current</span>
          </>
        )}
      </div>

      {/* Refreshing items */}
      {refreshStatus.length > 0 && (
        <div className="home-refresh-watchlist-changes">
          <h3 className="home-refresh-watchlist-changes-title">
            Currently Refreshing
          </h3>

          <div className="home-refresh-watchlist-items">
            {refreshStatus.slice(0, 5).map((item) => (
              <div key={item.ticker} className="home-refresh-watchlist-item">
                <span className="home-refresh-watchlist-ticker">
                  {item.ticker}
                </span>
                <span className="home-refresh-watchlist-status home-refresh-watchlist-status-pending">
                  {item.reason}
                </span>
              </div>
            ))}
          </div>

          {refreshStatus.length > 5 && (
            <p className="home-refresh-watchlist-more">
              +{refreshStatus.length - 5} more
            </p>
          )}
        </div>
      )}

      {/* Loading state */}
      {summaryLoading && (
        <div className="home-refresh-loading">
          <p>Syncing watchlist…</p>
        </div>
      )}

      {/* Error state */}
      {summaryError && (
        <div className="home-refresh-error">
          <p>{summaryError}</p>
        </div>
      )}

      {/* Empty state */}
      {!summaryLoading &&
        !summaryError &&
        summaryItems.length === 0 &&
        watchlistTickers.length === 0 && (
          <div className="home-refresh-empty">
            <p>Add companies to your watchlist to see refresh status.</p>
          </div>
        )}
    </section>
  );
}
