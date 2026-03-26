"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { useJobStream } from "@/hooks/use-job-stream";
import { getCompanyDerivedMetricsSummary, invalidateApiReadCacheForTicker } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { CompanyDerivedMetricsSummaryResponse, DerivedMetricValuePayload } from "@/lib/types";

const REFRESH_POLL_INTERVAL_MS = 3000;
const DISPLAY_KEYS = [
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
];

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

  useEffect(() => {
    if (!activeJobId) {
      return;
    }
    if (lastEvent?.status === "completed" || lastEvent?.status === "failed") {
      return;
    }
    const timerId = window.setInterval(() => {
      void loadSummary(false);
    }, REFRESH_POLL_INTERVAL_MS);
    return () => window.clearInterval(timerId);
  }, [activeJobId, lastEvent?.status, loadSummary]);

  const metricMap = useMemo(() => {
    const map = new Map<string, DerivedMetricValuePayload>();
    for (const metric of payload?.metrics ?? []) {
      map.set(metric.metric_key, metric);
    }
    return map;
  }, [payload?.metrics]);

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

      <div className="metric-grid">
        {DISPLAY_KEYS.map((key) => {
          const metric = metricMap.get(key);
          return <MetricValueCard key={key} metricKey={key} metric={metric} />;
        })}
      </div>
    </div>
  );
}

function MetricValueCard({ metricKey, metric }: { metricKey: string; metric?: DerivedMetricValuePayload }) {
  const value = metric?.metric_value;
  const unit = String(metric?.provenance?.unit ?? "").toLowerCase();
  const isPercent = unit === "ratio" && metricKey !== "current_ratio" && metricKey !== "cash_ratio";

  return (
    <div className="metric-card">
      <div className="metric-label">{metricKey.replaceAll("_", " ")}</div>
      <div className="metric-value">{formatMetricValue(value, isPercent)}</div>
      {metric?.quality_flags?.length ? (
        <div className="text-muted" style={{ fontSize: 11 }}>
          {metric.quality_flags.join(", ")}
        </div>
      ) : null}
    </div>
  );
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
