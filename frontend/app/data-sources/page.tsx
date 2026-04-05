"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { Panel } from "@/components/ui/panel";
import { getCacheMetrics, getSourceRegistry } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { CacheMetricsResponse, SourceRegistryResponse, SourceTier } from "@/lib/types";

type SourceTierSection = {
  tier: SourceTier;
  label: string;
  copy: string;
};

const SOURCE_TIER_SECTIONS: SourceTierSection[] = [
  {
    tier: "official_regulator",
    label: "Official Regulators",
    copy: "Primary disclosure and filing systems from market regulators.",
  },
  {
    tier: "official_statistical",
    label: "Official Statistical Agencies",
    copy: "Government statistical releases used for macro and sector context.",
  },
  {
    tier: "official_treasury_or_fed",
    label: "Treasury and Federal Reserve",
    copy: "Rates, liquidity, and macro policy context from Treasury and the Fed.",
  },
  {
    tier: "derived_from_official",
    label: "Derived From Official Inputs",
    copy: "Internal services that transform official or public inputs into reusable cached views.",
  },
  {
    tier: "commercial_fallback",
    label: "Commercial Fallbacks",
    copy: "Explicitly labeled fallbacks limited to non-core market context such as price and profile data.",
  },
  {
    tier: "manual_override",
    label: "Manual Overrides",
    copy: "Exceptional manual or synthetic inputs that require explicit disclosure.",
  },
];

export default function DataSourcesPage() {
  const router = useRouter();
  const [data, setData] = useState<SourceRegistryResponse | null>(null);
  const [cacheMetrics, setCacheMetrics] = useState<CacheMetricsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cacheError, setCacheError] = useState<string | null>(null);

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
  }, []);

  const groupedSources = useMemo(() => {
    const entries = data?.sources ?? [];
    return SOURCE_TIER_SECTIONS.map((section) => ({
      ...section,
      sources: entries.filter((entry) => entry.source_tier === section.tier),
    })).filter((section) => section.sources.length > 0);
  }, [data]);

  return (
    <div className="data-sources-page">
      <section className="data-sources-hero">
        <div className="data-sources-hero-copy">
          <span className="home-section-kicker">Transparency</span>
          <h1 className="data-sources-title">Data Sources</h1>
          <p className="data-sources-text">
            Core company fundamentals stay anchored to official/public sources. Internal derived services are labeled, commercial fallbacks stay narrow and explicit, and strict official mode can suppress fallback-backed inputs when it is enabled.
          </p>
        </div>
        <div className="data-sources-hero-meta">
          <span className="pill">Strict official mode {data?.strict_official_mode ? "on" : "off"}</span>
          <span className="pill">Sources {data?.sources.length ?? 0}</span>
          {data?.generated_at ? <span className="pill">Updated {formatDate(data.generated_at)}</span> : null}
          <button type="button" className="ticker-button" onClick={() => router.push("/")}>Back to Home</button>
        </div>
      </section>

      <Panel
        title="Current Health"
        subtitle="A compact view of cache coverage and recent source issues pulled from the same registry endpoint."
        className="data-sources-health-panel"
        variant="subtle"
      >
        {loading ? <div className="text-muted">Loading source registry...</div> : null}
        {error ? <div className="text-muted">{error}</div> : null}
        {data ? (
          <div className="data-sources-health-grid">
            <div className="data-sources-health-card">
              <div className="data-sources-health-label">Companies cached</div>
              <div className="data-sources-health-value">{new Intl.NumberFormat("en-US").format(data.health.total_companies_cached)}</div>
              <div className="data-sources-health-detail">Cached company financial snapshots available for workspace loading.</div>
            </div>
            <div className="data-sources-health-card">
              <div className="data-sources-health-label">Average data age</div>
              <div className="data-sources-health-value">{formatDurationFromSeconds(data.health.average_data_age_seconds)}</div>
              <div className="data-sources-health-detail">Mean age of cached company financial refresh timestamps.</div>
            </div>
            <div className="data-sources-health-card">
              <div className="data-sources-health-label">Recent source errors</div>
              <div className="data-sources-health-value">{data.health.sources_with_recent_errors.length}</div>
              <div className="data-sources-health-detail">Rolling {data.health.recent_error_window_hours}h source-error window.</div>
            </div>
          </div>
        ) : null}
      </Panel>

      <Panel
        title="Shared Hot Cache"
        subtitle="Redis-backed hot-path cache visibility for the highest-read backend responses."
        className="data-sources-health-panel"
        variant="subtle"
      >
        {loading ? <div className="text-muted">Loading shared cache metrics...</div> : null}
        {cacheError ? <div className="text-muted">{cacheError}</div> : null}
        {cacheMetrics ? (
          <div className="data-sources-health-grid">
            <div className="data-sources-health-card">
              <div className="data-sources-health-label">Backend</div>
              <div className="data-sources-health-value">{cacheMetrics.hot_cache.shared ? "Redis" : "Local"}</div>
              <div className="data-sources-health-detail">Namespace {cacheMetrics.hot_cache.namespace}</div>
            </div>
            <div className="data-sources-health-card">
              <div className="data-sources-health-label">Hit rate</div>
              <div className="data-sources-health-value">{formatPercent(cacheMetrics.hot_cache.overall.hit_rate)}</div>
              <div className="data-sources-health-detail">{new Intl.NumberFormat("en-US").format(cacheMetrics.hot_cache.overall.hits)} hits across {new Intl.NumberFormat("en-US").format(cacheMetrics.hot_cache.overall.requests)} requests.</div>
            </div>
            <div className="data-sources-health-card">
              <div className="data-sources-health-label">Average fill time</div>
              <div className="data-sources-health-value">{formatMilliseconds(cacheMetrics.hot_cache.overall.avg_fill_time_ms)}</div>
              <div className="data-sources-health-detail">Singleflight fill average across {new Intl.NumberFormat("en-US").format(cacheMetrics.hot_cache.overall.fills)} fills.</div>
            </div>
            <div className="data-sources-health-card">
              <div className="data-sources-health-label">Stale served</div>
              <div className="data-sources-health-value">{new Intl.NumberFormat("en-US").format(cacheMetrics.hot_cache.overall.stale_served_count)}</div>
              <div className="data-sources-health-detail">Responses served during stale-while-revalidate windows.</div>
            </div>
            <div className="data-sources-health-card">
              <div className="data-sources-health-label">Invalidations</div>
              <div className="data-sources-health-value">{new Intl.NumberFormat("en-US").format(cacheMetrics.hot_cache.overall.invalidation_count)}</div>
              <div className="data-sources-health-detail">{new Intl.NumberFormat("en-US").format(cacheMetrics.hot_cache.overall.invalidated_keys)} shared keys evicted.</div>
            </div>
          </div>
        ) : null}
      </Panel>

      <div className="data-sources-tier-list">
        {groupedSources.map((section) => (
          <Panel
            key={section.tier}
            title={section.label}
            subtitle={section.copy}
            className="data-sources-tier-panel"
            variant="subtle"
          >
            <div className="data-sources-card-grid">
              {section.sources.map((source) => (
                <article key={source.source_id} className="data-source-card">
                  <div className="data-source-card-head">
                    <div className="data-source-card-copy">
                      <div className="data-source-card-title">{source.display_label}</div>
                      <div className="data-source-card-id">{source.source_id}</div>
                    </div>
                    <div className="data-source-card-pills">
                      <span className="pill">{humanizeFlag(source.source_tier)}</span>
                      <span className="pill">TTL {formatTtl(source.default_freshness_ttl_seconds)}</span>
                      <span className={`pill data-source-strict-pill${source.strict_official_mode_state === "disabled" ? " is-disabled" : ""}`}>
                        Strict mode {source.strict_official_mode_state}
                      </span>
                    </div>
                  </div>
                  <div className="data-source-card-note">{source.disclosure_note}</div>
                  <div className="data-source-card-state">{source.strict_official_mode_note}</div>
                  <a href={source.url} target="_blank" rel="noreferrer" className="ticker-button data-source-card-link">
                    Open source
                  </a>
                </article>
              ))}
            </div>
          </Panel>
        ))}
      </div>
    </div>
  );
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

function formatMilliseconds(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(2)}s`;
  }
  return `${Math.round(value)}ms`;
}