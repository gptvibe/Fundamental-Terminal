"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  EmptyState,
  ErrorState,
  KpiCard,
  KpiStrip,
  LoadingSkeleton,
  PageHeader,
  PageShell,
  PrimaryTableCard,
  SectionAccordion,
  SourceBadge,
} from "@/components/ui/research-primitives";
import { getCacheMetrics, getSourceRegistry } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { CacheMetricsResponse, SourceRegistryEntryPayload, SourceRegistryResponse, SourceTier } from "@/lib/types";

type SummaryTone = "neutral" | "positive" | "warning" | "danger";

type SummaryCard = {
  label: string;
  value: string;
  detail: string;
  tone: SummaryTone;
};

type SourceStatusView = {
  title: string;
  tone: SummaryTone;
  badges: string[];
};

export default function DataSourcesPage() {
  const router = useRouter();
  const [data, setData] = useState<SourceRegistryResponse | null>(null);
  const [cacheMetrics, setCacheMetrics] = useState<CacheMetricsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cacheError, setCacheError] = useState<string | null>(null);
  const [requestVersion, setRequestVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function loadSourceRegistry() {
      try {
        setLoading(true);
        setError(null);
        setCacheError(null);
        const [sourceRegistryResult, cacheMetricsResult] = await Promise.allSettled([getSourceRegistry(), getCacheMetrics()]);
        if (cancelled) {
          return;
        }

        if (sourceRegistryResult.status === "fulfilled") {
          setData(sourceRegistryResult.value);
        } else {
          setData(null);
          setError(sourceRegistryResult.reason instanceof Error ? sourceRegistryResult.reason.message : "Unable to load data sources");
        }

        if (cacheMetricsResult.status === "fulfilled") {
          setCacheMetrics(cacheMetricsResult.value);
        } else {
          setCacheMetrics(null);
          setCacheError(cacheMetricsResult.reason instanceof Error ? cacheMetricsResult.reason.message : "Unable to load shared cache metrics");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadSourceRegistry();
    return () => {
      cancelled = true;
    };
  }, [requestVersion]);

  const sources = useMemo(() => data?.sources ?? [], [data]);
  const summaryCards = useMemo(
    () => buildSummaryCards({ data, cacheMetrics, cacheError, loading }),
    [cacheError, cacheMetrics, data, loading],
  );
  const latestSuccessAt = useMemo(
    () => pickLatestTimestamp(sources.map((source) => source.last_success_at)),
    [sources],
  );

  const retryAction = (
    <button type="button" className="ticker-button" onClick={() => setRequestVersion((current) => current + 1)}>
      Retry
    </button>
  );

  return (
    <PageShell className="data-sources-page">
      <PageHeader
        eyebrow="Transparency"
        title="Data Sources"
        subtitle="See whether filing, macro, and cache inputs look healthy before you rely on a page. Technical notes stay available below without taking over the scan path."
        actions={
          <div className="data-sources-header-actions">
            <span className="pill">Strict official mode {data?.strict_official_mode ? "on" : "off"}</span>
            <span className="pill">Sources {sources.length}</span>
            {data?.generated_at ? <span className="pill">Updated {formatDate(data.generated_at)}</span> : null}
            <button type="button" className="ticker-button" onClick={() => router.push("/")}>Back to Home</button>
          </div>
        }
      />

      <KpiStrip aria-label="Data source summary cards">
        {summaryCards.map((card) => (
          <KpiCard
            key={card.label}
            label={card.label}
            value={card.value}
            detail={card.detail}
            tone={card.tone}
          />
        ))}
      </KpiStrip>

      <PrimaryTableCard
        title="Source health"
        subtitle="One row per source so a normal scan shows what is healthy, stale, or disabled without opening debug views."
      >
        {loading && !data ? <LoadingSkeleton lines={6} label="Loading source health table" /> : null}
        {!loading && error && !data ? <ErrorState title="Source registry unavailable" message={error} retryAction={retryAction} /> : null}
        {!loading && !error && data && sources.length === 0 ? (
          <EmptyState
            title="No sources registered"
            message="The source registry returned no sources, so there is nothing to summarize yet."
            action={retryAction}
          />
        ) : null}
        {!loading && data && sources.length > 0 ? (
          <>
            <div className="compare-table-shell">
              <table className="compare-table data-sources-table" aria-label="Source health table">
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Status</th>
                    <th>Last success</th>
                    <th>Last error</th>
                    <th>Cache TTL</th>
                    <th>Used by</th>
                  </tr>
                </thead>
                <tbody>
                  {sources.map((source) => {
                    const status = getSourceStatus(source);
                    return (
                      <tr key={source.source_id}>
                        <td>
                          <div className="data-sources-source-cell">
                            <div className="data-sources-source-name">{source.display_label}</div>
                            <div className="data-sources-source-meta">
                              <span>{source.source_id}</span>
                              <a href={source.url} target="_blank" rel="noreferrer" className="data-sources-inline-link">
                                Open source
                              </a>
                            </div>
                          </div>
                        </td>
                        <td>
                          <div className="data-sources-status-cell">
                            <div className={`data-sources-status-title is-${status.tone}`}>{status.title}</div>
                            <div className="data-sources-status-badges">
                              {status.badges.map((badge) => (
                                <span className="pill" key={`${source.source_id}:${badge}`}>{badge}</span>
                              ))}
                            </div>
                          </div>
                        </td>
                        <td>{formatSuccessValue(source)}</td>
                        <td>{formatErrorValue(source)}</td>
                        <td>{formatTtl(source.default_freshness_ttl_seconds)}</td>
                        <td>
                          <div className="data-sources-used-by">
                            {buildUsageLabels(source.used_by_paths).map((label) => (
                              <span className="data-sources-chip" key={`${source.source_id}:${label}`}>{label}</span>
                            ))}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {cacheError ? <div className="data-sources-inline-warning">Cache metrics unavailable: {cacheError}</div> : null}
          </>
        ) : null}
      </PrimaryTableCard>

      <SectionAccordion
        title="How to read this page"
        subtitle="Fast interpretation guide for the labels and statuses shown above."
        defaultOpen
      >
        <div className="data-sources-accordion-copy">
          <ul className="data-sources-guidance-list">
            <li><strong>Official</strong> means the source is official, public, or derived directly from official inputs.</li>
            <li><strong>Fallback</strong> means the source is a commercial or manual fallback and should not dominate your trust in core fundamentals.</li>
            <li><strong>Disabled in strict mode</strong> means the source is intentionally suppressed when strict official mode is on.</li>
            <li><strong>Stale</strong> means the tracked freshness deadline has passed and the page may still be usable, but it needs a refresh.</li>
          </ul>
          <div className="text-muted">
            The status column only turns into an active warning when the latest recorded error is newer than the latest success. Older resolved errors stay visible in the history column without dominating the current health signal.
          </div>
        </div>
      </SectionAccordion>

      <SectionAccordion
        title="Methodology and source notes"
        subtitle="Long explanations, strict-mode notes, and route usage details live here instead of in the main scan path."
        aside={sources.length ? `${sources.length} sources` : "No source notes"}
      >
        {sources.length ? (
          <div className="data-sources-note-list">
            {sources.map((source) => (
              <article key={`note:${source.source_id}`} className="data-sources-note-item">
                <div className="data-sources-note-head">
                  <div>
                    <div className="data-sources-note-title">{source.display_label}</div>
                    <div className="data-sources-source-meta">{source.source_id}</div>
                  </div>
                  <SourceBadge source={humanizeFlag(source.source_tier)} kind={toSourceBadgeKind(source.source_tier)} />
                </div>
                <div className="data-sources-note-copy">{source.disclosure_note}</div>
                <div className="data-sources-note-copy">{source.strict_official_mode_note}</div>
                <div className="data-sources-note-copy">
                  Used by: {source.used_by_paths.length ? source.used_by_paths.join(", ") : "Used internally or loaded on demand."}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="data-sources-empty-note">Source notes appear once the registry loads.</div>
        )}
      </SectionAccordion>

      <SectionAccordion
        title="Raw configuration and debug details"
        subtitle="Registry snapshot timing, cache configuration, and recent tracked source errors."
        aside={data?.generated_at ? `Snapshot ${formatDate(data.generated_at)}` : "Pending"}
      >
        <div className="data-sources-debug-grid">
          <div className="data-sources-debug-list">
            <div>Companies cached: {data ? new Intl.NumberFormat("en-US").format(data.health.total_companies_cached) : "—"}</div>
            <div>Average company data age: {data ? formatDurationFromSeconds(data.health.average_data_age_seconds) : "—"}</div>
            <div>Recent error window: {data ? `${data.health.recent_error_window_hours}h` : "—"}</div>
            <div>Latest tracked success: {latestSuccessAt ? formatDate(latestSuccessAt) : "Not tracked"}</div>
          </div>
          <pre className="data-sources-debug-pre">
{JSON.stringify(
  {
    strictOfficialMode: data?.strict_official_mode ?? null,
    generatedAt: data?.generated_at ?? null,
    searchCache: cacheMetrics?.search_cache ?? null,
    hotCache: cacheMetrics
      ? {
          backend: cacheMetrics.hot_cache.backend,
          shared: cacheMetrics.hot_cache.shared,
          namespace: cacheMetrics.hot_cache.namespace,
          config: cacheMetrics.hot_cache.config,
          overall: cacheMetrics.hot_cache.overall,
        }
      : null,
    recentSourceErrors: data?.health.sources_with_recent_errors ?? [],
  },
  null,
  2,
)}</pre>
        </div>
      </SectionAccordion>
    </PageShell>
  );
}

function buildSummaryCards({
  data,
  cacheMetrics,
  cacheError,
  loading,
}: {
  data: SourceRegistryResponse | null;
  cacheMetrics: CacheMetricsResponse | null;
  cacheError: string | null;
  loading: boolean;
}): SummaryCard[] {
  const sources = data?.sources ?? [];
  const secSources = sources.filter((source) => source.source_id.startsWith("sec_"));
  const macroSources = sources.filter(
    (source) => source.source_tier === "official_statistical" || source.source_tier === "official_treasury_or_fed",
  );
  const latestSuccessAt = pickLatestTimestamp(sources.map((source) => source.last_success_at));

  return [
    summarizeSourceGroup("SEC status", secSources, loading, "official filing and correspondence feeds"),
    summarizeSourceGroup("Macro status", macroSources, loading, "macro and rates feeds"),
    summarizeCacheCard(cacheMetrics, cacheError, loading),
    summarizeRefreshCard(data?.generated_at ?? null, latestSuccessAt, loading),
  ];
}

function summarizeSourceGroup(label: string, sources: SourceRegistryEntryPayload[], loading: boolean, noun: string): SummaryCard {
  if (loading && sources.length === 0) {
    return { label, value: "Loading", detail: `Checking ${noun}.`, tone: "neutral" };
  }
  if (sources.length === 0) {
    return { label, value: "Not tracked", detail: `No ${noun} are registered here.`, tone: "neutral" };
  }

  const activeErrorCount = sources.filter(hasActiveError).length;
  const staleCount = sources.filter((source) => source.is_stale).length;
  const latestSuccessAt = pickLatestTimestamp(sources.map((source) => source.last_success_at));

  if (activeErrorCount > 0) {
    return {
      label,
      value: "Degraded",
      detail: `${activeErrorCount} source${activeErrorCount === 1 ? "" : "s"} need attention.`,
      tone: "danger",
    };
  }
  if (staleCount > 0) {
    return {
      label,
      value: "Watching",
      detail: `${staleCount} source${staleCount === 1 ? "" : "s"} marked stale.`,
      tone: "warning",
    };
  }
  if (latestSuccessAt) {
    return {
      label,
      value: "Healthy",
      detail: `Last tracked success ${formatDate(latestSuccessAt)}.`,
      tone: "positive",
    };
  }
  return {
    label,
    value: "Available",
    detail: `${sources.length} source${sources.length === 1 ? "" : "s"} ready for use.`,
    tone: "positive",
  };
}

function summarizeCacheCard(
  cacheMetrics: CacheMetricsResponse | null,
  cacheError: string | null,
  loading: boolean,
): SummaryCard {
  if (loading && !cacheMetrics && !cacheError) {
    return { label: "Cache status", value: "Loading", detail: "Checking shared cache metrics.", tone: "neutral" };
  }
  if (cacheError || !cacheMetrics) {
    return {
      label: "Cache status",
      value: "Unavailable",
      detail: cacheError ?? "Shared cache metrics are not available.",
      tone: "danger",
    };
  }

  if (!cacheMetrics.hot_cache.shared) {
    return {
      label: "Cache status",
      value: "Watching",
      detail: `Running local only. Hit rate ${formatPercent(cacheMetrics.hot_cache.overall.hit_rate)}.`,
      tone: "warning",
    };
  }
  if ((cacheMetrics.hot_cache.overall.hit_rate ?? 0) >= 0.75 && cacheMetrics.hot_cache.overall.stale_served_count === 0) {
    return {
      label: "Cache status",
      value: "Healthy",
      detail: `${formatPercent(cacheMetrics.hot_cache.overall.hit_rate)} hit rate in ${new Intl.NumberFormat("en-US").format(cacheMetrics.hot_cache.overall.requests)} requests.`,
      tone: "positive",
    };
  }
  return {
    label: "Cache status",
    value: "Watching",
    detail: `${formatPercent(cacheMetrics.hot_cache.overall.hit_rate)} hit rate, ${new Intl.NumberFormat("en-US").format(cacheMetrics.hot_cache.overall.stale_served_count)} stale responses served.`,
    tone: "warning",
  };
}

function summarizeRefreshCard(generatedAt: string | null, latestSuccessAt: string | null, loading: boolean): SummaryCard {
  if (loading && !generatedAt && !latestSuccessAt) {
    return { label: "Last refresh", value: "Loading", detail: "Waiting for the latest registry snapshot.", tone: "neutral" };
  }
  if (generatedAt) {
    return {
      label: "Last refresh",
      value: formatDate(generatedAt),
      detail: latestSuccessAt ? `Latest tracked source success ${formatDate(latestSuccessAt)}.` : "Registry snapshot time.",
      tone: "neutral",
    };
  }
  if (latestSuccessAt) {
    return {
      label: "Last refresh",
      value: formatDate(latestSuccessAt),
      detail: "Latest tracked source success.",
      tone: "neutral",
    };
  }
  return {
    label: "Last refresh",
    value: "Pending",
    detail: "No tracked refresh timestamp is available yet.",
    tone: "neutral",
  };
}

function getSourceStatus(source: SourceRegistryEntryPayload): SourceStatusView {
  const badges = [isFallbackSource(source.source_tier) ? "Fallback" : "Official"];
  if (source.strict_official_mode_state === "disabled") {
    badges.push("Disabled in strict mode");
  }
  if (source.is_stale) {
    badges.push("Stale");
  }

  if (source.strict_official_mode_state === "disabled") {
    return { title: "Disabled", tone: "warning", badges };
  }
  if (hasActiveError(source)) {
    return { title: "Needs attention", tone: "danger", badges };
  }
  if (source.is_stale) {
    return { title: "Stale", tone: "warning", badges };
  }
  if (source.last_success_at) {
    return { title: "Healthy", tone: "positive", badges };
  }
  return { title: "Available", tone: "neutral", badges };
}

function hasActiveError(source: SourceRegistryEntryPayload): boolean {
  if (!source.last_error_at) {
    return false;
  }
  if (!source.last_success_at) {
    return true;
  }
  return Date.parse(source.last_error_at) >= Date.parse(source.last_success_at);
}

function formatSuccessValue(source: SourceRegistryEntryPayload): string {
  if (source.last_success_at) {
    return formatDate(source.last_success_at);
  }
  if (source.used_by_paths.length > 0) {
    return "On demand";
  }
  return "—";
}

function formatErrorValue(source: SourceRegistryEntryPayload): string {
  if (!source.last_error || !source.last_error_at) {
    return "No recent error";
  }
  return `${formatDate(source.last_error_at)} · ${source.last_error}`;
}

function buildUsageLabels(paths: string[]): string[] {
  const labels = Array.from(new Set(paths.map(humanizeUsagePath))).filter(Boolean);
  if (labels.length <= 3) {
    return labels.length ? labels : ["On demand"];
  }
  return [...labels.slice(0, 3), `+${labels.length - 3} more`];
}

function humanizeUsagePath(path: string): string {
  if (path === "/api/companies/{ticker}" || path.includes("/research-brief") || path.endsWith("/brief")) {
    return "Research brief";
  }
  if (path.includes("/screener")) {
    return "Screener";
  }
  if (path.includes("/search") || path.includes("/resolve")) {
    return "Search";
  }
  if (path.includes("/financials")) {
    return "Financials";
  }
  if (path.includes("/charts")) {
    return "Charts";
  }
  if (path.includes("/models")) {
    return "Models";
  }
  if (path.includes("/peers")) {
    return "Peers";
  }
  if (path.includes("/earnings")) {
    return "Earnings";
  }
  if (path.includes("/filings")) {
    return "Filings";
  }
  if (path.includes("/capital-markets")) {
    return "Capital markets";
  }
  if (path.includes("/comment-letters")) {
    return "Comment letters";
  }

  const segments = path.split("/").filter(Boolean).filter((segment) => segment !== "api" && segment !== "companies" && !segment.startsWith("{"));
  if (!segments.length) {
    return "Workspace";
  }
  return segments[segments.length - 1]
    .replaceAll("-", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function pickLatestTimestamp(values: Array<string | null | undefined>): string | null {
  let latest: string | null = null;
  let latestTime = Number.NEGATIVE_INFINITY;

  for (const value of values) {
    if (!value) {
      continue;
    }
    const parsed = Date.parse(value);
    if (Number.isNaN(parsed)) {
      continue;
    }
    if (parsed > latestTime) {
      latest = value;
      latestTime = parsed;
    }
  }

  return latest;
}

function formatTtl(ttlSeconds: number): string {
  if (ttlSeconds <= 0) {
    return "manual";
  }
  if (ttlSeconds % 86_400 === 0) {
    return `${ttlSeconds / 86_400}d`;
  }
  if (ttlSeconds % 3_600 === 0) {
    return `${ttlSeconds / 3_600}h`;
  }
  if (ttlSeconds % 60 === 0) {
    return `${ttlSeconds / 60}m`;
  }
  return `${ttlSeconds}s`;
}

function formatDurationFromSeconds(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  const totalMinutes = Math.max(Math.round(value / 60), 0);
  if (totalMinutes < 60) {
    return `${totalMinutes}m`;
  }
  const totalHours = Math.round(totalMinutes / 60);
  if (totalHours < 48) {
    return `${totalHours}h`;
  }
  return `${Math.round(totalHours / 24)}d`;
}

function humanizeFlag(value: string): string {
  return value.replaceAll("_", " ");
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function isFallbackSource(sourceTier: SourceTier): boolean {
  return sourceTier === "commercial_fallback" || sourceTier === "manual_override";
}

function toSourceBadgeKind(sourceTier: SourceTier): "sec" | "market" | "model" | "derived" | "internal" | "external" {
  if (sourceTier === "official_regulator") {
    return "sec";
  }
  if (sourceTier === "official_statistical" || sourceTier === "official_treasury_or_fed") {
    return "market";
  }
  if (sourceTier === "derived_from_official") {
    return "derived";
  }
  if (sourceTier === "manual_override") {
    return "internal";
  }
  return "external";
}