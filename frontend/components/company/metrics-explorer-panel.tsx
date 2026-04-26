"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { useJobStream } from "@/hooks/use-job-stream";
import { MetricConfidenceBadge, type MetricConfidenceMetadata } from "@/components/ui/metric-confidence-badge";
import { MetricLabel } from "@/components/ui/metric-label";
import { SourceFreshnessSummary } from "@/components/ui/source-freshness-summary";
import { getCompanyDerivedMetricsSummary, invalidateApiReadCacheForTicker } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { CompanyDerivedMetricsSummaryResponse, DerivedMetricValuePayload } from "@/lib/types";
const GENERAL_DISPLAY_KEYS = [
  "revenue_growth",
  "eps_growth",
  "gross_margin",
  "operating_margin",
  "fcf_margin",
  "roic_proxy",
  "roe",
  "roa",
  "current_ratio",
  "cash_ratio",
  "shareholder_yield",
  "cash_conversion_cycle_days",
] as const;

const BANK_DISPLAY_KEYS = [
  "net_interest_margin",
  "provision_burden",
  "asset_quality_ratio",
  "cet1_ratio",
  "tier1_capital_ratio",
  "total_capital_ratio",
  "core_deposit_ratio",
  "uninsured_deposit_ratio",
  "tangible_book_value_per_share",
  "roatce",
] as const;

interface MetricsExplorerPanelProps {
  ticker: string;
  reloadKey?: string;
}

export function MetricsExplorerPanel({ ticker, reloadKey }: MetricsExplorerPanelProps) {
  const [periodType, setPeriodType] = useState<"quarterly" | "annual" | "ttm">("ttm");
  const [payload, setPayload] = useState<CompanyDerivedMetricsSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const { lastEvent } = useJobStream(activeJobId);

  const loadSummary = useCallback(
    async (showLoading: boolean) => {
      try {
        if (showLoading) {
          setLoading(true);
        }
        setError(null);
        const next = await getCompanyDerivedMetricsSummary(ticker, { periodType });
        setPayload(next);
        setActiveJobId(next.refresh.job_id);
      } catch (nextError) {
        setError(nextError instanceof Error ? nextError.message : "Unable to load metrics summary");
      } finally {
        if (showLoading) {
          setLoading(false);
        }
      }
    },
    [periodType, ticker]
  );

  useEffect(() => {
    void loadSummary(true);
  }, [loadSummary, reloadKey]);

  useEffect(() => {
    if (!activeJobId || !lastEvent) {
      return;
    }
    if (lastEvent.status !== "completed" && lastEvent.status !== "failed") {
      return;
    }
    invalidateApiReadCacheForTicker(ticker);
    void loadSummary(false);
  }, [activeJobId, lastEvent, loadSummary, ticker]);

  const metricMap = useMemo(() => {
    const map = new Map<string, DerivedMetricValuePayload>();
    for (const metric of payload?.metrics ?? []) {
      map.set(metric.metric_key, metric);
    }
    return map;
  }, [payload?.metrics]);
  const bankMode = Boolean(
    payload?.company?.regulated_entity && (BANK_DISPLAY_KEYS as readonly string[]).some((key) => metricMap.has(key))
  );
  const displayKeys = bankMode ? BANK_DISPLAY_KEYS : GENERAL_DISPLAY_KEYS;
  const metricsAreStale = Boolean(payload?.staleness_reason);

  if (loading) {
    return <div className="text-muted">Loading derived metrics explorer...</div>;
  }
  if (error) {
    return <div className="text-muted">{error}</div>;
  }
  if (!payload || !payload.metrics.length) {
    return <div className="text-muted">No persisted derived metrics available yet. Queue a refresh to compute SEC-derived metrics.</div>;
  }

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        {(["quarterly", "annual", "ttm"] as const).map((value) => (
          <button
            key={value}
            type="button"
            className={`chart-chip${periodType === value ? " chart-chip-active" : ""}`}
            onClick={() => setPeriodType(value)}
          >
            {value.toUpperCase()}
          </button>
        ))}
        <span className="pill">Latest: {payload.latest_period_end ? formatDate(payload.latest_period_end) : "?"}</span>
        {payload.staleness_reason ? <span className="pill">{payload.staleness_reason}</span> : null}
        {activeJobId ? <span className="pill">refreshing</span> : null}
      </div>

      <SourceFreshnessSummary
        provenance={payload.provenance}
        asOf={payload.as_of}
        lastRefreshedAt={payload.last_refreshed_at}
        sourceMix={payload.source_mix}
        confidenceFlags={payload.confidence_flags}
      />

      <div className="metric-grid">
        {displayKeys.map((key) => {
          const metric = metricMap.get(key);
          return <MetricValueCard key={key} metricKey={key} metric={metric} metricsAreStale={metricsAreStale} />;
        })}
      </div>
    </div>
  );
}

function MetricValueCard({
  metricKey,
  metric,
  metricsAreStale,
}: {
  metricKey: string;
  metric?: DerivedMetricValuePayload;
  metricsAreStale: boolean;
}) {
  const value = metric?.metric_value;
  const provenance = asRecord(metric?.provenance);
  const unit = String(provenance.unit ?? "").toLowerCase();
  const isPercent = unit === "ratio" && metricKey !== "current_ratio" && metricKey !== "cash_ratio";
  const label = metric?.metric_key ? metric.metric_key.replaceAll("_", " ") : metricKey.replaceAll("_", " ");
  const confidence = buildMetricConfidenceMetadata(metric, provenance, metricsAreStale);

  return (
    <div className="metric-card">
      <div className="metric-label">
        <MetricLabel label={label} metricKey={metric?.metric_key ?? metricKey} />
      </div>
      <div className="metric-value">{formatMetricValue(value, isPercent)}</div>
      {confidence ? <MetricConfidenceBadge metadata={confidence} /> : null}
      {metric?.quality_flags?.length ? (
        <div className="text-muted" style={{ fontSize: 11 }}>
          {metric.quality_flags.join(", ")}
        </div>
      ) : null}
    </div>
  );
}

function buildMetricConfidenceMetadata(
  metric: DerivedMetricValuePayload | undefined,
  provenance: Record<string, unknown>,
  metricsAreStale: boolean
): MetricConfidenceMetadata | null {
  if (!metric) {
    return null;
  }

  const source = asString(
    provenance.source_key ?? provenance.statement_source ?? provenance.price_source ?? provenance.source
  );
  const formulaVersion = asString(provenance.formula_version);
  const missingInputs = asStringArray(provenance.missing_inputs);
  const qualityFlags = metric.quality_flags ?? [];
  const fallbackUsed =
    asBoolean(provenance.fallback_used) ??
    qualityFlags.some((flag) => flag.includes("fallback")) ??
    false;

  return {
    freshness: metricsAreStale ? "stale" : "fresh",
    source,
    formulaVersion,
    missingInputsCount: missingInputs.length,
    missingInputs,
    proxyUsed: metric.is_proxy,
    fallbackUsed,
    qualityFlags,
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function asBoolean(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim())
    .filter(Boolean);
}

function formatMetricValue(value: number | null | undefined, isPercent: boolean): string {
  if (value == null) {
    return "?";
  }
  if (isPercent) {
    return `${(value * 100).toFixed(1)}%`;
  }
  if (Math.abs(value) >= 1000) {
    return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
  }
  return value.toFixed(2);
}
