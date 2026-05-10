"use client";

import type { ReactNode } from "react";
import { clsx } from "clsx";

export interface StickyCompanyHeaderProps {
  ticker: string;
  companyName?: string;
  lastUpdated?: string;
  dataSource?: "sec" | "cached" | "model";
  cacheState?: string | null;
  refreshState?: "idle" | "loading" | "queued" | "refreshing";
  onRefresh?: () => void;
  children?: ReactNode;
  className?: string;
}

export function StickyCompanyHeader({
  ticker,
  companyName,
  lastUpdated,
  dataSource = "cached",
  cacheState,
  refreshState = "idle",
  onRefresh,
  children,
  className,
}: StickyCompanyHeaderProps) {
  const sourceLabel: Record<string, string> = {
    sec: "SEC Official",
    cached: "Cached",
    model: "Derived",
  };

  const normalizedCacheState = cacheState?.trim().toLowerCase() || null;
  const cacheStateLabel = normalizedCacheState
    ? normalizedCacheState.replaceAll("_", " ")
    : null;

  return (
    <header
      className={clsx(
        "sticky-company-header",
        `data-source-${dataSource}`,
        `refresh-state-${refreshState}`,
        className
      )}
      role="banner"
      aria-label={`Company header for ${ticker}`}
    >
      <div className="sticky-header-content">
        <div className="sticky-header-left">
          <div className="company-identifier">
            <span className="ticker-badge" aria-label={`Ticker: ${ticker}`}>
              {ticker}
            </span>
            {companyName && (
              <span className="company-name" title={companyName}>
                {companyName}
              </span>
            )}
          </div>
        </div>

        <div className="sticky-header-center">
          {children}
        </div>

        <div className="sticky-header-right">
          <div className="freshness-status">
            {lastUpdated && (
              <span className="last-updated" title={`Last updated: ${lastUpdated}`}>
                {lastUpdated}
              </span>
            )}
            <span
              className={clsx("data-source-badge", `source-${dataSource}`)}
              aria-label={`Data source: ${sourceLabel[dataSource]}`}
            >
              <span className="status-glyph" aria-hidden="true">
                {dataSource === "sec" ? "SEC" : "SRC"}
              </span>
              {sourceLabel[dataSource]}
            </span>
            {cacheStateLabel && (
              <span
                className={clsx("cache-state-badge", `cache-state-${normalizedCacheState}`)}
                aria-label={`Cache state: ${cacheStateLabel}`}
              >
                <span className="status-glyph" aria-hidden="true">
                  {normalizedCacheState === "fresh" ? "OK" : normalizedCacheState === "stale" ? "STL" : "MIS"}
                </span>
                {cacheStateLabel}
              </span>
            )}
            {refreshState !== "idle" && (
              <span
                className={clsx("refresh-indicator", `state-${refreshState}`)}
                aria-live="polite"
              >
                {refreshState === "loading" && "⟳ Loading"}
                {refreshState === "queued" && "⏱ Queued"}
                {refreshState === "refreshing" && "↻ Refreshing"}
              </span>
            )}
          </div>

          {onRefresh && (
            <button
              onClick={onRefresh}
              className="refresh-button"
              aria-label="Refresh data"
              disabled={refreshState === "loading" || refreshState === "refreshing"}
              title="Press 'r' to refresh"
            >
              ↻
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
