import type { CSSProperties, ReactNode } from "react";
import { clsx } from "clsx";

import { MetricLabel } from "@/components/ui/metric-label";
import { formatDate } from "@/lib/format";
import type { CacheState, RefreshState } from "@/lib/types";

type AccentTone = "green" | "cyan" | "gold" | "red";

export interface CompanyFactItem {
  label: string;
  value: string | null;
}

export interface CompanySummaryItem {
  label: string;
  value: string;
  accent?: AccentTone;
}

export interface CompanyHeaderFreshness {
  cacheState?: CacheState | null;
  refreshState?: RefreshState | null;
  loading?: boolean;
  hasData?: boolean;
  lastChecked?: string | null;
  errors?: Array<string | null | undefined>;
  detailLines?: Array<string | null | undefined>;
}

export interface CompanyRibbonItem {
  label: string;
  value: string;
  tone?: AccentTone;
}

interface CompanyResearchHeaderProps {
  ticker: string;
  title: string;
  companyName?: string | null;
  sector?: string | null;
  cacheState?: string | null;
  description?: string;
  aside?: ReactNode;
  facts?: CompanyFactItem[];
  ribbonItems?: CompanyRibbonItem[];
  summaries?: CompanySummaryItem[];
  factsLoading?: boolean;
  summariesLoading?: boolean;
  freshness?: CompanyHeaderFreshness;
  freshnessPlacement?: "title" | "subtitle";
  className?: string;
  children?: ReactNode;
}

const METRIC_SKELETON_WIDTHS = ["72%", "58%", "66%", "80%"];
const SUMMARY_SKELETON_WIDTHS = ["64%", "78%", "56%", "70%"];

type FreshnessTone = "fresh" | "stale" | "error";

export function CompanyResearchHeader({
  ticker,
  title,
  companyName,
  sector,
  cacheState,
  description,
  aside,
  facts = [],
  ribbonItems = [],
  summaries = [],
  factsLoading = false,
  summariesLoading = false,
  freshness,
  freshnessPlacement = "subtitle",
  className,
  children,
}: CompanyResearchHeaderProps) {
  const freshnessIndicator = freshness ? buildFreshnessIndicator(freshness) : null;

  return (
    <section className={clsx("company-research-header", className)}>
      <div className="company-research-header-top">
        <div className="company-research-header-copy">
          {sector || cacheState ? (
            <div className="company-research-header-kicker-row">
              {sector ? <span className="company-research-header-tag">{sector}</span> : null}
              {cacheState ? (
                <span className={clsx("company-research-header-tag", `tone-${cacheState}`)}>
                  {cacheState}
                </span>
              ) : null}
            </div>
          ) : null}
          <div className="company-research-header-title-row">
            <div className="company-research-header-heading-stack">
              <div className="company-research-header-heading-line">
                <h1 className="company-research-header-title">{title}</h1>
                {freshnessPlacement === "title" && freshnessIndicator ? (
                  <HeaderFreshnessIndicator {...freshnessIndicator} />
                ) : null}
              </div>
              <div className="company-research-header-subtitle-row">
                <p className="company-research-header-subtitle">{companyName ?? ticker}</p>
                {freshnessPlacement === "subtitle" && freshnessIndicator ? (
                  <HeaderFreshnessIndicator {...freshnessIndicator} />
                ) : null}
              </div>
            </div>
            {aside ? <div className="company-research-header-aside">{aside}</div> : null}
          </div>
          {description ? <p className="company-research-header-description">{description}</p> : null}
        </div>
      </div>

      {ribbonItems.length ? (
        <div className="company-source-ribbon" aria-label="Data sources and freshness">
          {ribbonItems.map((item) => (
            <div key={`${item.label}:${item.value}`} className={clsx("company-source-chip", item.tone && `tone-${item.tone}`)}>
              <span className="company-source-chip-label">{item.label}</span>
              <span className="company-source-chip-value">{item.value}</span>
            </div>
          ))}
        </div>
      ) : null}

      {facts.length ? <CompanyMetricGrid items={facts} loading={factsLoading} /> : null}
      {summaries.length ? <CompanySummaryStrip items={summaries} loading={summariesLoading} /> : null}
      {children ? <div className="company-research-header-extra">{children}</div> : null}
    </section>
  );
}

export function CompanyMetricGrid({ items, loading = false }: { items: CompanyFactItem[]; loading?: boolean }) {
  return (
    <div className="metric-grid" aria-busy={loading ? "true" : undefined}>
      {items.map((item, index) => (
        <div key={item.label} className={clsx("metric-card", loading && "metric-card-loading")}>
          <div className="metric-label">
            <MetricLabel label={item.label} />
          </div>
          <div className="metric-value">
            {loading ? (
              <span
                aria-hidden="true"
                className="workspace-skeleton metric-value-skeleton"
                style={buildSkeletonWidth(METRIC_SKELETON_WIDTHS[index % METRIC_SKELETON_WIDTHS.length])}
              />
            ) : (
              item.value ?? "\u2014"
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export function CompanySummaryStrip({ items, className, loading = false }: { items: CompanySummaryItem[]; className?: string; loading?: boolean }) {
  return (
    <div className={clsx("company-summary-strip", className)}>
      {items.map((item, index) => (
        <div key={item.label} className={clsx("summary-card", `accent-${item.accent ?? "cyan"}`, loading && "summary-card-loading")}>
          <div className="summary-card-label">
            <MetricLabel label={item.label} />
          </div>
          <div className="summary-card-value">
            {loading ? (
              <span
                aria-hidden="true"
                className="workspace-skeleton summary-card-value-skeleton"
                style={buildSkeletonWidth(SUMMARY_SKELETON_WIDTHS[index % SUMMARY_SKELETON_WIDTHS.length])}
              />
            ) : (
              item.value || "\u2014"
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function HeaderFreshnessIndicator({
  tone,
  label,
  detailLines,
}: {
  tone: FreshnessTone;
  label: string;
  detailLines: string[];
}) {
  const title = [label, ...detailLines].join("\n");

  return (
    <span
      className={clsx("company-freshness-indicator", `tone-${tone}`)}
      tabIndex={0}
      role="img"
      aria-label={label}
      title={title}
    >
      <span className="company-freshness-dot" aria-hidden="true" />
      <span className="company-freshness-tooltip" role="tooltip">
        <span className="company-freshness-tooltip-title">{label}</span>
        {detailLines.map((line) => (
          <span key={line} className="company-freshness-tooltip-line">
            {line}
          </span>
        ))}
      </span>
    </span>
  );
}

function buildFreshnessIndicator(freshness: CompanyHeaderFreshness): {
  tone: FreshnessTone;
  label: string;
  detailLines: string[];
} {
  const errors = (freshness.errors ?? []).filter((item): item is string => Boolean(item));
  const hasData = Boolean(freshness.hasData);
  const cacheState = freshness.cacheState ?? null;
  const refreshState = freshness.refreshState ?? null;
  const refreshQueued = Boolean(refreshState?.job_id);

  let tone: FreshnessTone = "stale";
  let label = "Cached data is warming";

  if (errors.length) {
    tone = "error";
    label = hasData ? "Some data failed to load" : "Company data failed to load";
  } else if (freshness.loading && !hasData) {
    label = "Fetching first company snapshot";
  } else if (cacheState === "fresh" || (refreshState?.reason === "fresh" && hasData)) {
    tone = "fresh";
    label = refreshQueued ? "Fresh snapshot, refresh queued" : "Fresh snapshot";
  } else if (refreshQueued) {
    label = "Refresh queued in background";
  } else if (cacheState === "stale" || refreshState?.reason === "stale") {
    label = "Cached data is stale";
  } else if (cacheState === "missing" || refreshState?.reason === "missing") {
    label = hasData ? "Snapshot is incomplete" : "No cached snapshot yet";
  } else if (refreshState?.reason === "manual") {
    label = "Manual refresh requested";
  } else if (hasData) {
    label = "Cached data available";
  }

  const detailLines = [
    cacheState ? `Cache: ${formatCacheState(cacheState)}` : null,
    refreshState ? `Refresh: ${formatRefreshState(refreshState)}` : null,
    freshness.lastChecked ? `Last checked: ${formatDate(freshness.lastChecked)}` : null,
    ...(freshness.detailLines ?? []),
    ...errors.map((message) => `Error: ${message}`),
  ].filter((line): line is string => Boolean(line));
  const uniqueDetailLines = Array.from(new Set(detailLines));

  return {
    tone,
    label,
    detailLines: uniqueDetailLines,
  };
}

function formatCacheState(cacheState: CacheState): string {
  switch (cacheState) {
    case "fresh":
      return "fresh";
    case "stale":
      return "stale";
    case "missing":
      return "pending first snapshot";
    default:
      return cacheState;
  }
}

function formatRefreshState(refreshState: RefreshState): string {
  if (refreshState.job_id) {
    return "refresh queued in background";
  }

  switch (refreshState.reason) {
    case "fresh":
      return refreshState.triggered ? "fresh data with refresh requested" : "up to date";
    case "stale":
      return "stale cache waiting for refresh";
    case "missing":
      return "first snapshot pending";
    case "manual":
      return "manual refresh requested";
    case "none":
      return "background-first";
    default:
      return refreshState.reason;
  }
}

function buildSkeletonWidth(width: string): CSSProperties {
  return { width };
}
