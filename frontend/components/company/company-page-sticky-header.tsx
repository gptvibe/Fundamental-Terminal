"use client";

import { type ReactNode } from "react";
import { clsx } from "clsx";
import { DataFreshnessBadge, SourceBadge } from "@/components/ui/research-primitives";
import type { CacheState, SourceMixPayload } from "@/lib/types";

export interface StickyHeaderProps {
  ticker: string;
  companyName?: string | null;
  sector?: string | null;
  cacheState?: CacheState | null;
  sourceMix?: SourceMixPayload | null;
  isLoading?: boolean;
  hasError?: boolean;
  asOf?: string | null;
  className?: string;
}

export function CompanyPageStickyHeader({
  ticker,
  companyName,
  sector,
  cacheState,
  sourceMix,
  isLoading,
  hasError,
  asOf,
  className,
}: StickyHeaderProps) {
  return (
    <div
      className={clsx("research-brief-sticky-header", className)}
      role="banner"
      aria-label={`Company page header for ${ticker}`}
    >
      <div className="research-brief-sticky-header-content">
        <div className="research-brief-sticky-info">
          <div className="research-brief-sticky-ticker">
            {companyName || ticker}
            <span className="research-brief-sticky-ticker-code">{companyName && ` (${ticker})`}</span>
          </div>
          {sector && <span className="research-brief-sticky-sector">{sector}</span>}
        </div>

        <div className="research-brief-sticky-status">
          <DataFreshnessBadge
            freshness={
              cacheState === "stale" || hasError
                ? "stale"
                : cacheState === "missing"
                ? "unknown"
                : isLoading
                ? "unknown"
                : "fresh"
            }
            asOf={asOf ?? undefined}
          />
          {(sourceMix?.primary_source_ids ?? []).slice(0, 1).map((src) => (
            <SourceBadge key={src} source={src} kind="sec" />
          ))}
          {(sourceMix?.fallback_source_ids ?? []).slice(0, 1).map((src) => (
            <SourceBadge key={src} source={src} kind="external" />
          ))}
        </div>
      </div>
    </div>
  );
}
