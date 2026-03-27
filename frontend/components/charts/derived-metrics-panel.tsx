"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { PanelEmptyState } from "@/components/company/panel-empty-state";
import { SourceFreshnessSummary } from "@/components/ui/source-freshness-summary";
import { useJobStream } from "@/hooks/use-job-stream";
import { getCompanyMetricsTimeseries } from "@/lib/api";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { formatCompactNumber, formatDate } from "@/lib/format";
import type { CompanyMetricsTimeseriesResponse, MetricsValuesPayload } from "@/lib/types";

type Cadence = "quarterly" | "annual" | "ttm";

type MetricKey = keyof MetricsValuesPayload;

type MetricOption = {
  key: MetricKey;
  label: string;
  isPercent: boolean;
};

const METRIC_OPTIONS: MetricOption[] = [
  { key: "revenue_growth", label: "Revenue Growth", isPercent: true },
  { key: "gross_margin", label: "Gross Margin", isPercent: true },
  { key: "operating_margin", label: "Operating Margin", isPercent: true },
  { key: "fcf_margin", label: "FCF Margin", isPercent: true },
  { key: "roic_proxy", label: "ROIC Proxy", isPercent: true },
  { key: "leverage_ratio", label: "Leverage Ratio", isPercent: false },
  { key: "current_ratio", label: "Current Ratio", isPercent: false },
  { key: "share_dilution", label: "Share Dilution", isPercent: true },
  { key: "sbc_burden", label: "SBC Burden", isPercent: true },
  { key: "buyback_yield", label: "Buyback Yield", isPercent: true },
  { key: "dividend_yield", label: "Dividend Yield", isPercent: true },
  { key: "working_capital_days", label: "Working Capital Days", isPercent: false },
  { key: "accrual_ratio", label: "Accrual Ratio", isPercent: true },
  { key: "cash_conversion", label: "Cash Conversion", isPercent: false },
  { key: "segment_concentration", label: "Segment Concentration", isPercent: true },
];

const CADENCE_ORDER: Cadence[] = ["quarterly", "annual", "ttm"];
const MAX_POINTS = 24;
const REFRESH_POLL_INTERVAL_MS = 3000;
const STRICT_DISABLED_METRIC_KEYS = new Set<MetricKey>(["buyback_yield", "dividend_yield"]);

interface DerivedMetricsPanelProps {
  ticker: string;
  reloadKey?: string;
}

export function DerivedMetricsPanel({ ticker, reloadKey }: DerivedMetricsPanelProps) {
  const [payload, setPayload] = useState<CompanyMetricsTimeseriesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cadence, setCadence] = useState<Cadence>("ttm");
  const [metric, setMetric] = useState<MetricKey>("revenue_growth");
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const { lastEvent } = useJobStream(activeJobId);

  const loadMetrics = useCallback(
    async (showLoading: boolean) => {
      try {
        if (showLoading) {
          setLoading(true);
        }
        setError(null);
        const nextPayload = await getCompanyMetricsTimeseries(ticker, {
          cadence,
          maxPoints: MAX_POINTS,
        });
        setPayload(nextPayload);
        setActiveJobId(nextPayload.refresh.job_id);
      } catch (nextError) {
        setError(nextError instanceof Error ? nextError.message : "Unable to load derived metrics");
      } finally {
        if (showLoading) {
          setLoading(false);
        }
      }
    },
    [cadence, ticker]
  );

  useEffect(() => {
    let cancelled = false;

    async function load() {
      await loadMetrics(true);
      if (cancelled) {
        return;
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [ticker, reloadKey, cadence, loadMetrics]);

  useEffect(() => {
    if (!activeJobId || !lastEvent) {
      return;
    }
    if (lastEvent.status !== "completed" && lastEvent.status !== "failed") {
      return;
    }
    void loadMetrics(false);
  }, [activeJobId, lastEvent, loadMetrics]);

  useEffect(() => {
    if (!activeJobId) {
      return;
    }
    if (lastEvent?.status === "completed" || lastEvent?.status === "failed") {
      return;
    }

    const intervalId = window.setInterval(() => {
      void loadMetrics(false);
    }, REFRESH_POLL_INTERVAL_MS);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [activeJobId, lastEvent?.status, loadMetrics]);

  const availableCadences = useMemo(() => CADENCE_ORDER, []);
  const strictOfficialMode = Boolean(payload?.company?.strict_official_mode);

  useEffect(() => {
    if (!strictOfficialMode || !STRICT_DISABLED_METRIC_KEYS.has(metric)) {
      return;
    }
    const fallbackMetric = METRIC_OPTIONS.find((option) => !STRICT_DISABLED_METRIC_KEYS.has(option.key));
    if (fallbackMetric) {
      setMetric(fallbackMetric.key);
    }
  }, [metric, strictOfficialMode]);

  useEffect(() => {
    if (!availableCadences.length) {
      return;
    }
    if (!availableCadences.includes(cadence)) {
      setCadence(availableCadences[0]);
    }
  }, [availableCadences, cadence]);

  const selectedOption = METRIC_OPTIONS.find((option) => option.key === metric) ?? METRIC_OPTIONS[0];

  const series = useMemo(
    () =>
      (payload?.series ?? [])
        .sort((left, right) => left.period_end.localeCompare(right.period_end)),
    [payload?.series]
  );

  const chartData = useMemo(
    () =>
      series.map((point) => ({
        date: point.period_end,
        value: point.metrics[metric],
      })),
    [metric, series]
  );

  const latest = series.at(-1) ?? null;

  if (error) {
    return <div className="text-muted">{error}</div>;
  }
  if (loading) {
    return <div className="text-muted">Loading derived metrics...</div>;
  }
  if (!payload?.series.length) {
    return <PanelEmptyState message="No cached derived metrics are available yet. Refresh to queue SEC financial backfill and metrics recomputation." />;
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <div className="cash-waterfall-toggle-group">
          {CADENCE_ORDER.map((value) => (
            <button
              key={value}
              type="button"
              className={`chart-chip${cadence === value ? " chart-chip-active" : ""}`}
              onClick={() => setCadence(value)}
              disabled={!availableCadences.includes(value)}
            >
              {value.toUpperCase()}
            </button>
          ))}
        </div>

        <label className="pill" style={{ display: "flex", gap: 8, alignItems: "center" }}>
          Metric
          <select
            aria-label="Select derived metric"
            value={metric}
            onChange={(event) => setMetric(event.target.value as MetricKey)}
            style={{ background: "transparent", color: "var(--text)", border: "none", outline: "none" }}
          >
            {METRIC_OPTIONS.map((option) => (
              <option key={option.key} value={option.key} disabled={strictOfficialMode && STRICT_DISABLED_METRIC_KEYS.has(option.key)}>
                {strictOfficialMode && STRICT_DISABLED_METRIC_KEYS.has(option.key)
                  ? `${option.label} (strict mode unavailable)`
                  : option.label}
              </option>
            ))}
          </select>
        </label>

        <span className="pill">Points: {series.length}</span>
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

      {strictOfficialMode ? (
        <div className="text-muted">
          Strict official mode disables price-derived yield overlays. Buyback yield and dividend yield stay unavailable until an official equity-price source is configured.
        </div>
      ) : null}

      {latest ? (
        <div className="metric-grid">
          <MetricCard label="Latest Period" value={formatDate(latest.period_end)} />
          <MetricCard label={selectedOption.label} value={formatMetric(latest.metrics[metric], selectedOption.isPercent)} />
          <MetricCard label="Coverage" value={`${Math.round(latest.quality.coverage_ratio * 100)}%`} />
          <MetricCard label="Financials Check" value={payload.last_financials_check ? formatDate(payload.last_financials_check) : "?"} />
          <MetricCard label="Price Check" value={strictOfficialMode ? "Disabled in strict mode" : payload.last_price_check ? formatDate(payload.last_price_check) : "?"} />
          <MetricCard
            label="Provenance"
            value={`${latest.provenance.statement_type} • ${latest.provenance.price_source ?? "no-price"}`}
          />
        </div>
      ) : null}

      <div style={{ width: "100%", height: 320 }}>
        <ResponsiveContainer>
          <LineChart data={chartData} margin={{ top: 8, right: 12, left: 4, bottom: 8 }}>
            <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
            <XAxis dataKey="date" stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatDate(String(value))} />
            <YAxis
              stroke={CHART_AXIS_COLOR}
              tick={chartTick()}
              tickFormatter={(value) => formatMetric(Number(value), selectedOption.isPercent)}
            />
            <Tooltip
              {...RECHARTS_TOOLTIP_PROPS}
              formatter={(value: number) => formatMetric(value, selectedOption.isPercent)}
              labelFormatter={(value) => formatDate(String(value))}
            />
            <Line
              type="monotone"
              dataKey="value"
              name={selectedOption.label}
              stroke="#00E5FF"
              strokeWidth={2.2}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {latest?.quality.flags.length ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {latest.quality.flags.map((flag) => (
            <span className="pill" key={flag}>{flag}</span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function formatMetric(value: number | null, isPercent: boolean): string {
  if (value == null) {
    return "?";
  }
  if (isPercent) {
    return `${(value * 100).toFixed(1)}%`;
  }
  if (Math.abs(value) >= 1000) {
    return formatCompactNumber(value);
  }
  return value.toFixed(2);
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
    </div>
  );
}
