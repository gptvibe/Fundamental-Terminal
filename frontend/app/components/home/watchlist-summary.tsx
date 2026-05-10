"use client";

import { useGoToTicker } from "@/hooks/use-go-to-ticker";
import { formatCompactNumber, formatPercent } from "@/lib/format";
import type { WatchlistSummaryItemPayload } from "@/lib/types";
import "./watchlist-summary.css";

interface WatchlistSummaryProps {
  summaryItems: WatchlistSummaryItemPayload[];
  summaryLoading: boolean;
  summaryError: string | null;
}

export function WatchlistSummary({
  summaryItems,
  summaryLoading,
  summaryError,
}: WatchlistSummaryProps) {
  const goToTicker = useGoToTicker();

  if (summaryError) {
    return (
      <section className="home-watchlist-summary">
        <h2 className="home-watchlist-summary-title">Watchlist</h2>
        <div className="home-watchlist-summary-error">
          <p>{summaryError}</p>
        </div>
      </section>
    );
  }

  if (summaryLoading || !summaryItems.length) {
    return (
      <section className="home-watchlist-summary">
        <h2 className="home-watchlist-summary-title">Watchlist</h2>
        <div className="home-watchlist-summary-empty">
          {summaryLoading ? (
            <p>Loading watchlist…</p>
          ) : (
            <p>Add companies to your watchlist to see them here.</p>
          )}
        </div>
      </section>
    );
  }

  return (
    <section className="home-watchlist-summary">
      <h2 className="home-watchlist-summary-title">Watchlist</h2>
      <div className="home-watchlist-summary-grid">
        {summaryItems.map((item) => (
          <button
            key={item.ticker}
            onClick={() =>
              goToTicker(item.ticker, "company", {
                ticker: item.ticker,
                name: item.name,
                sector: item.sector,
              })
            }
            className="home-watchlist-summary-card"
            type="button"
          >
            <div className="home-watchlist-summary-card-header">
              <span className="home-watchlist-summary-ticker">
                {item.ticker}
              </span>
              {item.name && (
                <span className="home-watchlist-summary-name">
                  {item.name}
                </span>
              )}
            </div>

            {item.sector && (
              <div className="home-watchlist-summary-sector">
                {item.sector}
              </div>
            )}

            <div className="home-watchlist-summary-metrics">
              {item.fair_value_gap !== null &&
                item.fair_value_gap !== undefined && (
                  <div className="home-watchlist-summary-metric">
                    <span className="home-watchlist-summary-metric-label">
                      Fair Value Gap
                    </span>
                    <span className="home-watchlist-summary-metric-value">
                      {formatPercent(item.fair_value_gap)}
                    </span>
                  </div>
                )}

              {item.shareholder_yield !== null &&
                item.shareholder_yield !== undefined && (
                  <div className="home-watchlist-summary-metric">
                    <span className="home-watchlist-summary-metric-label">
                      Shareholder Yield
                    </span>
                    <span className="home-watchlist-summary-metric-value">
                      {formatPercent(item.shareholder_yield)}
                    </span>
                  </div>
                )}

              {item.roic !== null && item.roic !== undefined && (
                <div className="home-watchlist-summary-metric">
                  <span className="home-watchlist-summary-metric-label">
                    ROIC
                  </span>
                  <span className="home-watchlist-summary-metric-value">
                    {formatPercent(item.roic)}
                  </span>
                </div>
              )}
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}
