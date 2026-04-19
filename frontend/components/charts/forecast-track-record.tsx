"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { CHART_AXIS_COLOR, CHART_GRID_COLOR, chartTick } from "@/lib/chart-theme";
import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import type {
  CompanyChartsForecastAccuracyResponse,
  CompanyChartsForecastAccuracySamplePayload,
} from "@/lib/types";

type ForecastTrackRecordSortKey =
  | "target_fiscal_year"
  | "absolute_error"
  | "absolute_percentage_error"
  | "directionally_correct";

type ForecastTrackRecordSortDirection = "asc" | "desc";

interface ForecastTrackRecordProps {
  data: CompanyChartsForecastAccuracyResponse | null;
  loading?: boolean;
  error?: string | null;
  defaultMetricKey?: string;
}

interface TimelineRow {
  label: string;
  fiscalYear: number;
  predictedValue: number | null;
  actualValue: number | null;
}

const EMPTY_FORECAST_METRICS: CompanyChartsForecastAccuracyResponse["metrics"] = [];

const SORTABLE_COLUMNS: Array<{ key: ForecastTrackRecordSortKey; label: string }> = [
  { key: "target_fiscal_year", label: "Target FY" },
  { key: "absolute_error", label: "Abs Error" },
  { key: "absolute_percentage_error", label: "APE" },
  { key: "directionally_correct", label: "Direction" },
];

export function ForecastTrackRecord({
  data,
  loading = false,
  error = null,
  defaultMetricKey,
}: ForecastTrackRecordProps) {
  const metricOptions = useMemo(() => data?.metrics ?? EMPTY_FORECAST_METRICS, [data?.metrics]);
  const initialMetric =
    defaultMetricKey && metricOptions.some((metric) => metric.key === defaultMetricKey)
      ? defaultMetricKey
      : metricOptions[0]?.key ?? "";
  const [selectedMetric, setSelectedMetric] = useState(initialMetric);
  const [sortKey, setSortKey] = useState<ForecastTrackRecordSortKey>("target_fiscal_year");
  const [sortDirection, setSortDirection] = useState<ForecastTrackRecordSortDirection>("desc");
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!metricOptions.length) {
      return;
    }
    const metricStillExists = metricOptions.some((metric) => metric.key === selectedMetric);
    if (!metricStillExists) {
      setSelectedMetric(initialMetric);
    }
  }, [initialMetric, metricOptions, selectedMetric]);

  const activeMetric = metricOptions.find((metric) => metric.key === selectedMetric) ?? metricOptions[0] ?? null;
  const metricKey = activeMetric?.key ?? "";

  const metricSamples = useMemo(() => {
    if (!data || !metricKey) {
      return [];
    }
    return data.samples.filter((sample) => sample.metric_key === metricKey);
  }, [data, metricKey]);

  const timelineRows = useMemo<TimelineRow[]>(() => {
    return [...metricSamples]
      .sort((left, right) => left.target_fiscal_year - right.target_fiscal_year)
      .map((sample) => ({
        label: `FY${sample.target_fiscal_year}`,
        fiscalYear: sample.target_fiscal_year,
        predictedValue: sample.predicted_value,
        actualValue: sample.actual_value,
      }));
  }, [metricSamples]);

  const sortedRows = useMemo(() => {
    return [...metricSamples].sort((left, right) => {
      const multiplier = sortDirection === "asc" ? 1 : -1;
      if (sortKey === "target_fiscal_year") {
        return multiplier * (left.target_fiscal_year - right.target_fiscal_year);
      }
      if (sortKey === "directionally_correct") {
        const leftValue = directionSortValue(left.directionally_correct);
        const rightValue = directionSortValue(right.directionally_correct);
        return multiplier * (leftValue - rightValue);
      }
      const leftValue = numericSortValue(left[sortKey]);
      const rightValue = numericSortValue(right[sortKey]);
      return multiplier * (leftValue - rightValue);
    });
  }, [metricSamples, sortDirection, sortKey]);

  const isInsufficientHistory = !data || data.status !== "ok" || data.aggregate.sample_count === 0;

  if (loading) {
    return <div className="workspace-card-stack">Loading forecast track record...</div>;
  }

  if (error) {
    return <div className="workspace-card-stack">Forecast track record unavailable: {error}</div>;
  }

  if (!data) {
    return <div className="workspace-card-stack">No forecast track record data.</div>;
  }

  if (isInsufficientHistory) {
    return (
      <section className="workspace-card-stack" data-testid="forecast-track-record-insufficient">
        <h3>Forecast Track Record</h3>
        <p>
          {data.insufficient_history_reason ??
            "Not enough realized one-year-forward history is available yet to show a track record."}
        </p>
        <p className="text-muted">
          This module does not fabricate forecast outcomes. It only reports realized historical forecast-vs-actual samples.
        </p>
        <MethodologyFooter data={data} />
      </section>
    );
  }

  return (
    <section className="workspace-card-stack" data-testid="forecast-track-record">
      <h3>Forecast Track Record</h3>
      <div className="workspace-pill-row" data-testid="forecast-track-record-summary">
        <span className="pill">Snapshots {data.aggregate.snapshot_count}</span>
        <span className="pill">Samples {data.aggregate.sample_count}</span>
        <span className="pill">Aggregate MAPE {formatPercent(data.aggregate.mean_absolute_percentage_error)}</span>
        <span className="pill">Directional Accuracy {formatPercent(data.aggregate.directional_accuracy)}</span>
      </div>

      <div className="studio-scenario-action-row">
        <label htmlFor="forecast-track-record-metric">Metric</label>
        <select
          id="forecast-track-record-metric"
          data-testid="forecast-track-record-metric-select"
          value={metricKey}
          onChange={(event) => setSelectedMetric(event.target.value)}
        >
          {metricOptions.map((metric) => (
            <option key={metric.key} value={metric.key}>
              {metric.label}
            </option>
          ))}
        </select>
      </div>

      <div className="models-forecast-impact-card forecast-track-record-chart-card">
        <div className="metric-label">{activeMetric?.label ?? "Selected metric"} - Predicted vs Actual</div>
        <div className="forecast-track-record-chart-shell">
          <ResponsiveContainer>
            <LineChart data={timelineRows} margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
              <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
              <XAxis dataKey="label" stroke={CHART_AXIS_COLOR} tick={chartTick(10)} />
              <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick(10)} tickFormatter={(value) => formatCompactNumber(asNumber(value))} />
              <Tooltip
                formatter={(value: unknown) => formatCompactNumber(asNumber(value))}
                labelFormatter={(label: string | number) => `${label}`}
              />
              <Line type="monotone" dataKey="predictedValue" stroke="var(--warning)" strokeWidth={2.4} dot={false} connectNulls />
              <Line type="monotone" dataKey="actualValue" stroke="var(--accent)" strokeWidth={2.4} dot={false} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="studio-table-wrapper">
        <table className="studio-scenarios-table" data-testid="forecast-track-record-table">
          <thead>
            <tr>
              {SORTABLE_COLUMNS.map((column) => (
                <th key={column.key}>
                  <button
                    type="button"
                    className="studio-secondary-button"
                    onClick={() => {
                      if (sortKey === column.key) {
                        setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
                        return;
                      }
                      setSortKey(column.key);
                      setSortDirection("desc");
                    }}
                  >
                    {column.label}
                  </button>
                </th>
              ))}
              <th>Predicted</th>
              <th>Actual</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((sample) => {
              const rowId = `${sample.metric_key}-${sample.anchor_fiscal_year}-${sample.target_fiscal_year}-${sample.cutoff_as_of}`;
              const expanded = Boolean(expandedRows[rowId]);
              return (
                <Fragment key={rowId}>
                  <tr data-testid={`forecast-track-record-row-${rowId}`}>
                    <td>{sample.target_fiscal_year}</td>
                    <td>{formatCompactNumber(sample.absolute_error)}</td>
                    <td>{formatPercent(sample.absolute_percentage_error)}</td>
                    <td>{directionLabel(sample.directionally_correct)}</td>
                    <td>{formatCompactNumber(sample.predicted_value)}</td>
                    <td>{formatCompactNumber(sample.actual_value)}</td>
                    <td>
                      <button
                        type="button"
                        className="studio-secondary-button"
                        onClick={() => {
                          setExpandedRows((current) => ({
                            ...current,
                            [rowId]: !current[rowId],
                          }));
                        }}
                      >
                        {expanded ? "Collapse" : "Expand"}
                      </button>
                    </td>
                  </tr>
                  {expanded ? (
                    <tr data-testid={`forecast-track-record-expanded-${rowId}`}>
                      <td colSpan={7}>
                        <div className="text-muted">
                          Anchor FY {sample.anchor_fiscal_year} | Cutoff {formatDate(sample.cutoff_as_of)}
                        </div>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <MethodologyFooter data={data} />
    </section>
  );
}

function MethodologyFooter({ data }: { data: CompanyChartsForecastAccuracyResponse }) {
  return (
    <div className="text-muted" data-testid="forecast-track-record-methodology">
      One-year-forward point-in-time walk-forward validation. Only realized annual outcomes are counted. Max snapshots {data.max_backtests}. As of {data.as_of ?? "latest"}; refreshed {formatDate(data.last_refreshed_at)}.
    </div>
  );
}

function numericSortValue(value: number | null | undefined): number {
  if (value == null || Number.isNaN(value)) {
    return Number.NEGATIVE_INFINITY;
  }
  return value;
}

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  return null;
}

function directionSortValue(value: boolean | null): number {
  if (value === true) {
    return 1;
  }
  if (value === false) {
    return 0;
  }
  return -1;
}

function directionLabel(value: boolean | null): string {
  if (value === true) {
    return "Correct";
  }
  if (value === false) {
    return "Miss";
  }
  return "N/A";
}
