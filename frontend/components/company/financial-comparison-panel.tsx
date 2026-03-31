"use client";

import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { PanelEmptyState } from "@/components/company/panel-empty-state";
import { SnapshotSurfaceStatus } from "@/components/company/snapshot-surface-status";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { buildAnnualSurfaceWarnings, formatAnnualHeader, formatAnnualLabel, resolveAnnualFinancialScope } from "@/lib/annual-financial-scope";
import { buildPlainTextTable, copyTextToClipboard, exportRowsToCsv, normalizeExportFileStem, type ExportRow } from "@/lib/export";
import { difference, formatSignedCompactDelta, type SharedFinancialChartState } from "@/lib/financial-chart-state";
import { formatCompactNumber, formatPercent } from "@/lib/format";
import { showAppToast } from "@/lib/app-toast";
import { dedupeSnapshotSurfaceWarnings, resolveSnapshotSurfaceMode, type SnapshotSurfaceCapabilities, type SnapshotSurfaceWarning } from "@/lib/snapshot-surface";
import type { FinancialPayload } from "@/lib/types";

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
  chartState?: SharedFinancialChartState;
  selectedFinancial?: FinancialPayload | null;
  comparisonFinancial?: FinancialPayload | null;
  ticker?: string;
}

const CAPABILITIES: SnapshotSurfaceCapabilities = {
  supports_selected_period: true,
  supports_compare_mode: true,
  supports_trend_mode: true,
};

export function FinancialComparisonPanel({
  financials,
  visibleFinancials = [],
  chartState,
  selectedFinancial = null,
  comparisonFinancial = null,
  ticker,
}: FinancialComparisonPanelProps) {
  const [metricKey, setMetricKey] = useState<string>(METRIC_ROWS[0]?.key ?? "revenue");
  const resolvedSelectedFinancial = chartState?.selectedFinancial ?? selectedFinancial;
  const resolvedComparisonFinancial = chartState?.comparisonFinancial ?? comparisonFinancial;
  const annualScope = useMemo(
    () => resolveAnnualFinancialScope({
      financials,
      visibleFinancials,
      selectedFinancial: resolvedSelectedFinancial,
      comparisonFinancial: resolvedComparisonFinancial,
    }),
    [financials, resolvedComparisonFinancial, resolvedSelectedFinancial, visibleFinancials]
  );
  const annualFinancials = annualScope.annuals;
  const leftFinancial = annualScope.selectedAnnual;
  const rightFinancial = annualScope.comparisonAnnual;
  const trendFinancials = annualScope.scopedAnnuals;
  const metric = useMemo(
    () => METRIC_ROWS.find((row) => row.key === metricKey) ?? METRIC_ROWS[0],
    [metricKey]
  );

  if (!annualFinancials.length || !leftFinancial) {
    return <PanelEmptyState message="No annual filing history is available yet for year-over-year comparison." />;
  }

  const warnings = buildWarnings({
    chartState,
    selectedFinancial: resolvedSelectedFinancial,
    comparisonFinancial: resolvedComparisonFinancial,
    annualScope,
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
  const exportStem = normalizeExportFileStem(ticker, "company");
  const csvRows = buildFinancialComparisonExportRows(chartData, metric, leftFinancial, rightFinancial);
  const plainTextPayload = buildFinancialComparisonPlainText(chartData, metric, leftFinancial, rightFinancial);

  async function handleCopyTable() {
    try {
      await copyTextToClipboard(plainTextPayload);
      showAppToast({ message: "Copied annual financial comparison data.", tone: "info" });
    } catch (error) {
      showAppToast({
        message: error instanceof Error ? error.message : "Unable to copy annual financial comparison data.",
        tone: "danger",
      });
    }
  }

  return (
    <div className="financial-statements-stack">
      <SnapshotSurfaceStatus capabilities={CAPABILITIES} mode={mode} warnings={warnings} />

      <div className="financial-export-row">
        <div className="financial-trend-table-note">Export the current annual comparison table and the visible metric trend for the selected range.</div>
        <div className="financial-export-actions">
          <button
            type="button"
            className="ticker-button financial-export-button"
            onClick={() => exportRowsToCsv(`${exportStem}-annual-financial-comparison.csv`, csvRows)}
          >
            Export CSV
          </button>
          <button
            type="button"
            className="ticker-button financial-export-button"
            onClick={handleCopyTable}
          >
            Copy Table
          </button>
        </div>
      </div>

      <div className="financial-inline-pills">
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

        <div className="financial-inline-pills">
          <span className="pill">Annual periods {trendFinancials.length}</span>
          <span className="pill">Chart {metric.label}</span>
        </div>
      </div>

      <div className="financial-chart-shell financial-chart-shell-medium">
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

function buildWarnings({
  chartState,
  selectedFinancial,
  comparisonFinancial,
  annualScope,
  trendFinancials,
}: {
  chartState?: SharedFinancialChartState;
  selectedFinancial: FinancialPayload | null;
  comparisonFinancial: FinancialPayload | null;
  annualScope: ReturnType<typeof resolveAnnualFinancialScope>;
  trendFinancials: FinancialPayload[];
}): SnapshotSurfaceWarning[] {
  return dedupeSnapshotSurfaceWarnings(
    buildAnnualSurfaceWarnings({
      chartState,
      scope: annualScope,
      selectedFinancial,
      comparisonFinancial,
      trendPointCount: trendFinancials.length,
      sparseHistoryDetail: "Only one comparable annual filing is visible, so the chart falls back to the focused year snapshot.",
    })
  );
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

function buildFinancialComparisonExportRows(
  chartData: Array<{
    label: string;
    periodEnd: string;
    filingType: string;
    value: number | null;
    isSelected: boolean;
    isComparison: boolean;
  }>,
  metric: MetricRowConfig,
  leftFinancial: FinancialPayload,
  rightFinancial: FinancialPayload | null
): ExportRow[] {
  const focusLabel = formatAnnualHeader(leftFinancial);
  const compareLabel = rightFinancial ? formatAnnualHeader(rightFinancial) : "Period B";
  const trendRows: ExportRow[] = chartData.map((point) => ({
    section: "trend",
    metric: metric.label,
    period: point.label,
    period_end: point.periodEnd,
    filing_type: point.filingType,
    focus_period: focusLabel,
    compare_period: compareLabel,
    focus_value: "",
    compare_value: "",
    value: metric.formatValue(point.value),
    absolute_change: "",
    percent_change: "",
    is_focus: point.isSelected ? "yes" : "",
    is_compare: point.isComparison ? "yes" : "",
  }));
  const comparisonRows: ExportRow[] = METRIC_ROWS.map((row) => {
    const leftValue = row.getValue(leftFinancial);
    const rightValue = rightFinancial ? row.getValue(rightFinancial) : null;
    const delta = difference(leftValue, rightValue);
    const relativeChange = calculateRelativeChange(leftValue, rightValue);

    return {
      section: "comparison",
      metric: row.label,
      period: "",
      period_end: "",
      filing_type: "",
      focus_period: focusLabel,
      compare_period: compareLabel,
      focus_value: row.formatValue(leftValue),
      compare_value: row.formatValue(rightValue),
      value: "",
      absolute_change: formatMetricDelta(row, delta),
      percent_change: formatPercent(relativeChange),
      is_focus: "",
      is_compare: "",
    } satisfies ExportRow;
  });

  return [...comparisonRows, ...trendRows];
}

function buildFinancialComparisonPlainText(
  chartData: Array<{
    label: string;
    periodEnd: string;
    value: number | null;
    isSelected: boolean;
    isComparison: boolean;
  }>,
  metric: MetricRowConfig,
  leftFinancial: FinancialPayload,
  rightFinancial: FinancialPayload | null
): string {
  const focusLabel = formatAnnualHeader(leftFinancial);
  const compareLabel = rightFinancial ? formatAnnualHeader(rightFinancial) : "Period B";
  const trendTable = buildPlainTextTable(
    ["Period", "Period End", metric.label, "Focus", "Compare"],
    chartData.map((point) => [
      point.label,
      point.periodEnd,
      metric.formatValue(point.value),
      point.isSelected ? "Yes" : "",
      point.isComparison ? "Yes" : "",
    ])
  );
  const comparisonTable = buildPlainTextTable(
    ["Metric", focusLabel, compareLabel, "Absolute Change", "Percent Change"],
    METRIC_ROWS.map((row) => {
      const leftValue = row.getValue(leftFinancial);
      const rightValue = rightFinancial ? row.getValue(rightFinancial) : null;
      const delta = difference(leftValue, rightValue);
      const relativeChange = calculateRelativeChange(leftValue, rightValue);

      return [
        row.label,
        row.formatValue(leftValue),
        row.formatValue(rightValue),
        formatMetricDelta(row, delta),
        formatPercent(relativeChange),
      ];
    })
  );

  return [
    "Annual Financial Comparison",
    `Focus: ${focusLabel}`,
    `Compare: ${compareLabel}`,
    "",
    `Metric Trend (${metric.label})`,
    trendTable,
    "",
    "Selected vs Compare",
    comparisonTable,
  ].join("\n");
}