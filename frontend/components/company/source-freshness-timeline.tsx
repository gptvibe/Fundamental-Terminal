"use client";

import { useEffect, useMemo, useState } from "react";
import { clsx } from "clsx";

import { formatDate } from "@/lib/format";
import { isPerformanceAuditEnabled, type PerformanceAuditRequestRecord } from "@/lib/performance-audit";
import type {
  CompanyChartsDashboardResponse,
  CompanyFinancialsResponse,
  CompanyPayload,
  CompanyWorkspaceBootstrapResponse,
  FilingTimelineItemPayload,
  ProvenanceEntryPayload,
  RefreshState,
  SourceMixPayload,
} from "@/lib/types";

type SourceFreshnessTimelineProps = {
  ticker: string;
  company?: CompanyPayload | null;
  refreshState?: RefreshState | null;
  activeJobId?: string | null;
  financialsResponse?: CompanyFinancialsResponse | null;
  chartsResponse?: CompanyChartsDashboardResponse | null;
  workspaceBootstrap?: CompanyWorkspaceBootstrapResponse | null;
  filingTimeline?: FilingTimelineItemPayload[] | null;
  provenance?: ProvenanceEntryPayload[] | null;
  sourceMix?: SourceMixPayload | null;
  asOf?: string | null;
  lastRefreshedAt?: string | null;
  className?: string;
};

type TimelineStep = {
  key: string;
  label: string;
  status: "good" | "warn" | "neutral";
  title: string;
  detail: string;
  badges?: string[];
};

type EndpointCacheStatus = {
  endpoint: string;
  source: string;
  disposition: string;
  at: string;
};

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);

export function SourceFreshnessTimeline({
  ticker,
  company,
  refreshState,
  activeJobId,
  financialsResponse,
  chartsResponse,
  workspaceBootstrap,
  filingTimeline,
  provenance,
  sourceMix,
  asOf,
  lastRefreshedAt,
  className,
}: SourceFreshnessTimelineProps) {
  const timelineFacts = useMemo(() => {
    const mergedFinancials = [
      ...(financialsResponse?.financials ?? []),
      ...(workspaceBootstrap?.financials?.financials ?? []),
    ];

    const latestFiling = pickLatestDate([
      ...mergedFinancials.map((item) => item.period_end),
      ...(filingTimeline ?? []).map((item) => item.date),
    ]);
    const latestAnnualFiling = pickLatestDate([
      ...mergedFinancials.filter((item) => ANNUAL_FORMS.has(item.filing_type)).map((item) => item.period_end),
      ...(filingTimeline ?? []).filter((item) => ANNUAL_FORMS.has(item.form)).map((item) => item.date),
    ]);

    const resolvedRefreshState = refreshState
      ?? financialsResponse?.refresh
      ?? chartsResponse?.refresh
      ?? workspaceBootstrap?.financials?.refresh
      ?? null;

    const resolvedAsOf = asOf
      ?? financialsResponse?.as_of
      ?? chartsResponse?.as_of
      ?? workspaceBootstrap?.financials?.as_of
      ?? null;

    const resolvedLastRefreshedAt = lastRefreshedAt
      ?? financialsResponse?.last_refreshed_at
      ?? chartsResponse?.last_refreshed_at
      ?? workspaceBootstrap?.financials?.last_refreshed_at
      ?? null;

    const resolvedProvenance =
      provenance
      ?? financialsResponse?.provenance
      ?? chartsResponse?.provenance
      ?? workspaceBootstrap?.financials?.provenance
      ?? [];

    const resolvedSourceMix =
      sourceMix
      ?? financialsResponse?.source_mix
      ?? chartsResponse?.source_mix
      ?? workspaceBootstrap?.financials?.source_mix
      ?? null;

    return {
      latestFiling,
      latestAnnualFiling,
      refreshState: resolvedRefreshState,
      asOf: resolvedAsOf,
      lastRefreshedAt: resolvedLastRefreshedAt,
      provenance: resolvedProvenance,
      sourceMix: resolvedSourceMix,
    };
  }, [asOf, chartsResponse, filingTimeline, financialsResponse, lastRefreshedAt, provenance, refreshState, sourceMix, workspaceBootstrap]);

  const endpointStatuses = useEndpointCacheStatuses(ticker);
  const sourceBadges = useMemo(() => buildSourceBadges(timelineFacts.sourceMix, timelineFacts.provenance), [timelineFacts.provenance, timelineFacts.sourceMix]);

  const steps = useMemo<TimelineStep[]>(() => {
    const refresh = timelineFacts.refreshState;
    const jobActive = Boolean(activeJobId || refresh?.job_id);
    const refreshQueued = Boolean(refresh?.job_id);

    return [
      {
        key: "sec-filing",
        label: "SEC filing",
        status: timelineFacts.latestFiling ? "good" : "warn",
        title: timelineFacts.latestFiling ? `Latest filing ${formatDate(timelineFacts.latestFiling)}` : "No filing date yet",
        detail: timelineFacts.latestAnnualFiling
          ? `Latest annual filing ${formatDate(timelineFacts.latestAnnualFiling)}`
          : "Annual filing date not available",
      },
      {
        key: "backend-refresh",
        label: "Backend refresh",
        status: jobActive || refreshQueued ? "warn" : "good",
        title: formatRefreshTitle(refresh, activeJobId),
        detail: timelineFacts.lastRefreshedAt
          ? `Last backend refresh ${formatDate(timelineFacts.lastRefreshedAt)}`
          : timelineFacts.asOf
            ? `As of ${formatDate(timelineFacts.asOf)}`
            : "Backend freshness metadata pending",
      },
      {
        key: "browser-cache",
        label: "Browser cache",
        status: endpointStatuses.length ? "good" : "neutral",
        title: endpointStatuses.length
          ? `${endpointStatuses[0].endpoint}: ${endpointStatuses[0].source}`
          : "No endpoint cache event yet",
        detail: endpointStatuses.length
          ? `${endpointStatuses[0].disposition} at ${endpointStatuses[0].at}`
          : "Performance audit endpoint cache metadata unavailable",
      },
      {
        key: "current-view",
        label: "Current view",
        status: company?.cache_state === "stale" || company?.cache_state === "missing" ? "warn" : "good",
        title: company?.cache_state ? `Cache ${company.cache_state}` : "Cache state unavailable",
        detail: company?.last_checked ? `Company last checked ${formatDate(company.last_checked)}` : "Company check timestamp pending",
        badges: sourceBadges,
      },
    ];
  }, [activeJobId, company?.cache_state, company?.last_checked, endpointStatuses, sourceBadges, timelineFacts.asOf, timelineFacts.lastRefreshedAt, timelineFacts.latestAnnualFiling, timelineFacts.latestFiling, timelineFacts.refreshState]);

  return (
    <section className={clsx("source-freshness-timeline", className)} aria-label="Source freshness timeline">
      <div className="source-freshness-timeline-header">
        <h2 className="source-freshness-timeline-title">Source freshness timeline</h2>
        <p className="source-freshness-timeline-subtitle">{`${ticker} · SEC filing -> backend refresh -> browser cache -> current view`}</p>
      </div>

      <ol className="source-freshness-timeline-track">
        {steps.map((step) => (
          <li key={step.key} className={clsx("source-freshness-timeline-step", `tone-${step.status}`)}>
            <span className="source-freshness-timeline-step-label">{step.label}</span>
            <span className="source-freshness-timeline-step-title">{step.title}</span>
            <span className="source-freshness-timeline-step-detail">{step.detail}</span>
            {step.badges?.length ? (
              <span className="source-freshness-timeline-badges">
                {step.badges.map((badge) => (
                  <span key={badge} className="source-freshness-timeline-badge">{badge}</span>
                ))}
              </span>
            ) : null}
          </li>
        ))}
      </ol>

      {endpointStatuses.length ? (
        <div className="source-freshness-timeline-endpoints" aria-label="Endpoint cache status">
          <span className="source-freshness-timeline-endpoints-label">Endpoint cache status</span>
          <div className="source-freshness-timeline-endpoint-list">
            {endpointStatuses.map((status) => (
              <span key={`${status.endpoint}:${status.at}`} className="source-freshness-timeline-endpoint-chip" title={`${status.disposition} via ${status.source}`}>
                {status.endpoint}: {status.source}
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function useEndpointCacheStatuses(ticker: string): EndpointCacheStatus[] {
  const enabled = isPerformanceAuditEnabled();
  const [statuses, setStatuses] = useState<EndpointCacheStatus[]>([]);

  useEffect(() => {
    if (!enabled || typeof window === "undefined") {
      setStatuses([]);
      return;
    }

    const tickerPath = `/companies/${encodeURIComponent(ticker.trim().toUpperCase())}/`;

    const readStatuses = () => {
      const snapshot = window.__FT_PERFORMANCE_AUDIT__?.snapshot();
      if (!snapshot) {
        setStatuses([]);
        return;
      }

      const latestByEndpoint = new Map<string, PerformanceAuditRequestRecord>();
      for (const record of snapshot.requests) {
        if (!matchesTickerPath(record, tickerPath)) {
          continue;
        }

        const endpoint = extractEndpointLabel(record.path, tickerPath);
        if (!endpoint) {
          continue;
        }

        const previous = latestByEndpoint.get(endpoint);
        if (!previous || compareRecords(record, previous) > 0) {
          latestByEndpoint.set(endpoint, record);
        }
      }

      const next = [...latestByEndpoint.entries()]
        .map(([endpoint, record]) => ({
          endpoint,
          source: record.responseSource ?? (record.networkRequest ? "network" : "unknown"),
          disposition: record.cacheDisposition,
          at: formatAuditTime(record.startedAt),
          sortAt: Date.parse(record.startedAt),
        }))
        .sort((a, b) => (Number.isFinite(b.sortAt) ? b.sortAt : 0) - (Number.isFinite(a.sortAt) ? a.sortAt : 0))
        .slice(0, 6)
        .map(({ sortAt: _sortAt, ...rest }) => rest);

      setStatuses(next);
    };

    readStatuses();
    const intervalId = window.setInterval(readStatuses, 1500);
    window.addEventListener("storage", readStatuses);
    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener("storage", readStatuses);
    };
  }, [enabled, ticker]);

  return statuses;
}

function matchesTickerPath(record: PerformanceAuditRequestRecord, tickerPath: string): boolean {
  if (record.path.startsWith(tickerPath)) {
    return true;
  }

  if (record.cacheKey && record.cacheKey.startsWith(tickerPath)) {
    return true;
  }

  return false;
}

function extractEndpointLabel(path: string, tickerPath: string): string | null {
  if (!path.startsWith(tickerPath)) {
    return null;
  }

  const noQuery = path.split("?")[0];
  const suffix = noQuery.slice(tickerPath.length);
  if (!suffix) {
    return null;
  }

  const head = suffix.split("/")[0] || suffix;
  switch (head) {
    case "workspace-bootstrap":
      return "Workspace";
    case "financials":
      return "Financials";
    case "overview":
      return "Overview";
    case "charts":
      return "Charts";
    case "brief":
      return "Brief";
    default:
      return head.replaceAll("-", " ");
  }
}

function compareRecords(a: PerformanceAuditRequestRecord, b: PerformanceAuditRequestRecord): number {
  const aTime = Date.parse(a.startedAt);
  const bTime = Date.parse(b.startedAt);
  if (Number.isFinite(aTime) && Number.isFinite(bTime) && aTime !== bTime) {
    return aTime - bTime;
  }
  return a.id.localeCompare(b.id);
}

function formatAuditTime(value: string): string {
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) {
    return value;
  }
  return new Date(parsed).toLocaleTimeString();
}

function pickLatestDate(values: Array<string | null | undefined>): string | null {
  let best: string | null = null;
  let bestTs = Number.NEGATIVE_INFINITY;
  for (const value of values) {
    if (!value) {
      continue;
    }
    const ts = Date.parse(value);
    if (!Number.isFinite(ts)) {
      continue;
    }
    if (ts > bestTs) {
      bestTs = ts;
      best = value;
    }
  }
  return best;
}

function formatRefreshTitle(refreshState: RefreshState | null, activeJobId: string | null | undefined): string {
  if (activeJobId) {
    return `Active refresh job ${activeJobId.slice(0, 8)}`;
  }
  if (refreshState?.job_id) {
    return `Refresh queued (${refreshState.job_id.slice(0, 8)})`;
  }
  if (refreshState?.reason) {
    return `Refresh reason ${refreshState.reason}`;
  }
  return "Refresh state unavailable";
}

function buildSourceBadges(sourceMix: SourceMixPayload | null, provenance: ProvenanceEntryPayload[]): string[] {
  const badges: string[] = [];

  if (sourceMix?.official_only) {
    badges.push("Official only");
  } else if ((sourceMix?.fallback_source_ids.length ?? 0) > 0) {
    badges.push("Includes fallback sources");
  }

  for (const entry of provenance.slice(0, 3)) {
    badges.push(entry.display_label);
  }

  return badges;
}
