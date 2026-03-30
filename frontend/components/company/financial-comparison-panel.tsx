"use client";

import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { PanelEmptyState } from "@/components/company/panel-empty-state";
import { SnapshotSurfaceStatus } from "@/components/company/snapshot-surface-status";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { difference, formatSignedCompactDelta } from "@/lib/financial-chart-state";
import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import { dedupeSnapshotSurfaceWarnings, resolveSnapshotSurfaceMode, type SnapshotSurfaceCapabilities, type SnapshotSurfaceWarning } from "@/lib/snapshot-surface";
import type { FinancialPayload } from "@/lib/types";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);

type MetricRowConfig = {
  key: string;
  label: string;
  getValue: (statement: FinancialPayload) => number | null | undefined;
  formatValue: (value: number | null | undefined) => string;
  formatDelta?: (value: number | null | undefined) => string;
};

const METRIC_ROWS: MetricRowConfig[] = [
  { key: "revenue", label: "Revenue", getValue: (statement) => statement.revenue, formatValue: formatCompactNumber },
  { key: "gross_profit", label: "Gross Profit", getValue: (statement) => statement.gross_profit, formatValue: formatCompactNumber },
  { key: "operating_income", label: "Operating Income", getValue: (statement) => statement.operating_income, formatValue: formatCompactNumber },
  { key: "net_income", label: "Net Income", getValue: (statement) => statement.net_income, formatValue: formatCompactNumber },
  { key: "free_cash_flow", label: "Free Cash Flow", getValue: (statement) => statement.free_cash_flow, formatValue: formatCompactNumber },
  { key: "total_assets", label: "Total Assets", getValue: (statement) => statement.total_assets, formatValue: formatCompactNumber },
  { key: "total_liabilities", label: "Total Liabilities", getValue: (statement) => statement.total_liabilities, formatValue: formatCompactNumber },
  {
    key: "eps",
    label: "EPS",
    getValue: (statement) => statement.eps,
    formatValue: formatPerShareValue,
    formatDelta: formatPerShareDelta,
  },
  { key: "shares_outstanding", label: "Shares Outstanding", getValue: (statement) => statement.shares_outstanding, formatValue: formatCompactNumber },
];

interface FinancialComparisonPanelProps {
  financials: FinancialPayload[];
  visibleFinancials?: FinancialPayload[];
  selectedFinancial?: FinancialPayload | null;
  comparisonFinancial?: FinancialPayload | null;
}

const CAPABILITIES: SnapshotSurfaceCapabilities = {
  supports_selected_period: true,
  supports_compare_mode: true,
  supports_trend_mode: true,
};

export function FinancialComparisonPanel({
  financials,
  visibleFinancials = [],
  selectedFinancial = null,
  comparisonFinancial = null,
}: FinancialComparisonPanelProps) {
  const annualFinancials = useMemo(
    () =>
      financials
        .filter((statement) => ANNUAL_FORMS.has(statement.filing_type))
        .sort((left, right) => Date.parse(right.period_end) - Date.parse(left.period_end)),
    [financials]
  );

  const [metricKey, setMetricKey] = useState<string>(METRIC_ROWS[0]?.key ?? "revenue");
  const leftFinancial = useMemo(() => coerceAnnualStatement(selectedFinancial, annualFinancials), [annualFinancials, selectedFinancial]);
  const rightFinancial = useMemo(() => resolveComparisonStatement(leftFinancial, comparisonFinancial, annualFinancials), [annualFinancials, comparisonFinancial, leftFinancial]);
  const trendFinancials = useMemo(
    () => annualTrendScope(annualFinancials, visibleFinancials, leftFinancial, rightFinancial),
    [annualFinancials, leftFinancial, rightFinancial, visibleFinancials]
  );
  const metric = useMemo(
    () => METRIC_ROWS.find((row) => row.key === metricKey) ?? METRIC_ROWS[0],
    [metricKey]
  );

  if (!annualFinancials.length || !leftFinancial) {
    return <PanelEmptyState message="No annual filing history is available yet for year-over-year comparison." />;
  }

  const warnings = buildWarnings({
    selectedFinancial,
    comparisonFinancial,
    selectedAnnual: leftFinancial,
    comparisonAnnual: rightFinancial,
    trendFinancials,
  });
  const mode = resolveSnapshotSurfaceMode({
    comparisonAvailable: rightFinancial !== null,
    trendAvailable: trendFinancials.length > 1,
    capabilities: CAPABILITIES,
  });
  const chartData = [...trendFinancials]
    .reverse()
    .map((statement) => ({
      label: formatAnnualHeader(statement),
      periodEnd: statement.period_end,
      filingType: statement.filing_type,
      value: metric.getValue(statement) ?? null,
      isSelected: buildPeriodKey(statement) === buildPeriodKey(leftFinancial),
      isComparison: rightFinancial ? buildPeriodKey(statement) === buildPeriodKey(rightFinancial) : false,
    }));
  const selectedPoint = chartData.find((point): point is (typeof chartData)[number] & { value: number } => point.isSelected && point.value != null) ?? null;
  const comparisonPoint = chartData.find((point): point is (typeof chartData)[number] & { value: number } => point.isComparison && point.value != null) ?? null;

  return (
    <div className="financial-statements-stack">
      <SnapshotSurfaceStatus capabilities={CAPABILITIES} mode={mode} warnings={warnings} />

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <span className="pill tone-cyan">Focus {formatAnnualLabel(leftFinancial)}</span>
        {rightFinancial ? <span className="pill tone-gold">Compare {formatAnnualLabel(rightFinancial)}</span> : <span className="pill tone-red">Need a second annual filing for full deltas</span>}
      </div>

      <div className="financial-period-toolbar-grid secondary-grid">
        <label className="financial-period-toolbar-select" htmlFor="financial-comparison-metric">
          <span className="financial-period-toolbar-select-label">Metric</span>
          <select id="financial-comparison-metric" value={metric.key} onChange={(event) => setMetricKey(event.target.value)}>
            {METRIC_ROWS.map((row) => (
              <option key={row.key} value={row.key}>
                {row.label}
              </option>
            ))}
          </select>
        </label>

        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span className="pill">Annual periods {trendFinancials.length}</span>
          <span className="pill">Chart {metric.label}</span>
        </div>
      </div>

      <div style={{ width: "100%", height: 320 }}>
        <ResponsiveContainer>
          <LineChart data={chartData} margin={{ top: 8, right: 12, left: 4, bottom: 8 }}>
            <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
            <XAxis dataKey="label" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
            <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => metric.formatValue(Number(value))} />
            <Tooltip
              {...RECHARTS_TOOLTIP_PROPS}
              formatter={(value: number) => metric.formatValue(value)}
              labelFormatter={(value) => String(value)}
            />
            <Line type="monotone" dataKey="value" name={metric.label} stroke="var(--accent)" strokeWidth={2.2} dot={false} connectNulls isAnimationActive={false} />
            {selectedPoint ? <ReferenceDot x={selectedPoint.label} y={selectedPoint.value} r={4} fill="var(--accent)" stroke="var(--accent)" isFront /> : null}
            {comparisonPoint ? <ReferenceDot x={comparisonPoint.label} y={comparisonPoint.value} r={4} fill="var(--warning)" stroke="var(--warning)" isFront /> : null}
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="financial-table-shell">
        <table className="financial-table" style={{ minWidth: 920 }}>
          <thead>
            <tr>
              <th>Metric</th>
              <th>{formatAnnualHeader(leftFinancial)}</th>
              <th>{rightFinancial ? formatAnnualHeader(rightFinancial) : "Period B"}</th>
              <th>Absolute Change</th>
              <th>Percent Change</th>
            </tr>
          </thead>
          <tbody>
            {METRIC_ROWS.map((metric) => {
              const leftValue = leftFinancial ? metric.getValue(leftFinancial) : null;
              const rightValue = rightFinancial ? metric.getValue(rightFinancial) : null;
              const delta = difference(leftValue, rightValue);
              const relativeChange = calculateRelativeChange(leftValue, rightValue);
              const tone = getChangeTone(delta);

              return (
                <tr key={metric.key}>
                  <td>{metric.label}</td>
                  <td>{metric.formatValue(leftValue)}</td>
                  <td>{metric.formatValue(rightValue)}</td>
                  <td style={tone.style}>{formatMetricDelta(metric, delta)}</td>
                  <td style={tone.style}>{formatPercent(relativeChange)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function buildPeriodKey(statement: Pick<FinancialPayload, "period_end" | "filing_type">): string {
  return `${statement.period_end}|${statement.filing_type}`;
}

function coerceAnnualStatement(selectedFinancial: FinancialPayload | null, annualFinancials: FinancialPayload[]): FinancialPayload | null {
  if (!selectedFinancial) {
    return annualFinancials[0] ?? null;
  }
  if (ANNUAL_FORMS.has(selectedFinancial.filing_type)) {
    return selectedFinancial;
  }
  const year = new Date(selectedFinancial.period_end).getUTCFullYear();
  return annualFinancials.find((statement) => new Date(statement.period_end).getUTCFullYear() === year) ?? annualFinancials[0] ?? null;
}

function resolveComparisonStatement(
  selectedAnnual: FinancialPayload | null,
  comparisonFinancial: FinancialPayload | null,
  annualFinancials: FinancialPayload[]
): FinancialPayload | null {
  if (!selectedAnnual) {
    return null;
  }
  if (comparisonFinancial && ANNUAL_FORMS.has(comparisonFinancial.filing_type)) {
    return comparisonFinancial;
  }
  const selectedIndex = annualFinancials.findIndex((statement) => buildPeriodKey(statement) === buildPeriodKey(selectedAnnual));
  if (selectedIndex < 0) {
    return annualFinancials[1] ?? null;
  }
  return annualFinancials[selectedIndex + 1] ?? null;
}

function annualTrendScope(
  annualFinancials: FinancialPayload[],
  visibleFinancials: FinancialPayload[],
  selectedAnnual: FinancialPayload | null,
  comparisonAnnual: FinancialPayload | null
): FinancialPayload[] {
  const pinnedYears = new Set<number>();
  if (selectedAnnual) {
    pinnedYears.add(new Date(selectedAnnual.period_end).getUTCFullYear());
  }
  if (comparisonAnnual) {
    pinnedYears.add(new Date(comparisonAnnual.period_end).getUTCFullYear());
  }

  const visibleYears = new Set(
    visibleFinancials
      .map((statement) => new Date(statement.period_end).getUTCFullYear())
      .filter((year) => Number.isFinite(year))
  );

  const scoped = visibleYears.size
    ? annualFinancials.filter((statement) => {
        const year = new Date(statement.period_end).getUTCFullYear();
        return visibleYears.has(year) || pinnedYears.has(year);
      })
    : annualFinancials.slice(0, 6);

  return scoped.length ? scoped.slice(0, 6) : annualFinancials.slice(0, 6);
}

function formatAnnualLabel(statement: Pick<FinancialPayload, "period_end" | "filing_type">): string {
  return `${statement.filing_type} ${formatDate(statement.period_end)}`;
}

function formatAnnualHeader(statement: Pick<FinancialPayload, "period_end" | "filing_type">): string {
  return `${statement.filing_type} ${new Date(statement.period_end).getUTCFullYear()}`;
}

function buildWarnings({
  selectedFinancial,
  comparisonFinancial,
  selectedAnnual,
  comparisonAnnual,
  trendFinancials,
}: {
  selectedFinancial: FinancialPayload | null;
  comparisonFinancial: FinancialPayload | null;
  selectedAnnual: FinancialPayload | null;
  comparisonAnnual: FinancialPayload | null;
  trendFinancials: FinancialPayload[];
}): SnapshotSurfaceWarning[] {
  const warnings: SnapshotSurfaceWarning[] = [];
  if (selectedFinancial && selectedAnnual && !ANNUAL_FORMS.has(selectedFinancial.filing_type)) {
    warnings.push({
      code: "comparison_annual_fallback",
      label: "Annual fallback applied",
      detail: `Annual comparison uses ${formatAnnualLabel(selectedAnnual)} because this surface compares normalized fiscal years.`,
      tone: "info",
    });
  }
  if (comparisonFinancial && !comparisonAnnual) {
    warnings.push({
      code: "comparison_period_missing",
      label: "Comparison annual unavailable",
      detail: "The selected comparison period does not have a matching annual filing in the current history window.",
      tone: "warning",
    });
  }
  if (trendFinancials.length < 2) {
    warnings.push({
      code: "comparison_history_sparse",
      label: "Sparse annual history",
      detail: "Only one comparable annual filing is visible, so the chart falls back to the focused year snapshot.",
      tone: "info",
    });
  }
  return dedupeSnapshotSurfaceWarnings(warnings);
}

function formatPerShareValue(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "\u2014";
  }
  return value.toFixed(2);
}

function formatPerShareDelta(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "\u2014";
  }
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
}

function formatMetricDelta(metric: MetricRowConfig, value: number | null): string {
  if (metric.formatDelta) {
    return metric.formatDelta(value);
  }
  return formatSignedCompactDelta(value);
}

function calculateRelativeChange(current: number | null | undefined, previous: number | null | undefined): number | null {
  if (current == null || previous == null || Number.isNaN(current) || Number.isNaN(previous) || previous === 0) {
    return null;
  }
  return (current - previous) / Math.abs(previous);
}

function getChangeTone(value: number | null): { style: React.CSSProperties } {
  if (value == null || Number.isNaN(value) || value === 0) {
    return { style: { color: "var(--text-muted)", fontWeight: 600 } };
  }
  return {
    style: {
      color: value > 0 ? "var(--positive)" : "var(--negative)",
      fontWeight: 700,
    },
  };
}