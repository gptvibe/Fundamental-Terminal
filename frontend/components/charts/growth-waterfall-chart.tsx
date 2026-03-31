"use client";

import { useMemo, useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { PanelEmptyState } from "@/components/company/panel-empty-state";
import { SnapshotSurfaceStatus } from "@/components/company/snapshot-surface-status";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, CHART_LEGEND_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { difference, formatSignedCompactDelta, formatSignedPointDelta, type SharedFinancialChartState } from "@/lib/financial-chart-state";
import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import { dedupeSnapshotSurfaceWarnings, resolveSnapshotSurfaceMode, type SnapshotSurfaceCapabilities, type SnapshotSurfaceWarning } from "@/lib/snapshot-surface";
import type { FinancialPayload } from "@/lib/types";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);
const CAPABILITIES: SnapshotSurfaceCapabilities = {
  supports_selected_period: true,
  supports_compare_mode: true,
  supports_trend_mode: true,
};

type MetricKey = "revenue" | "net_income" | "free_cash_flow";

type AnnualGrowthPoint = {
  period: string;
  periodEnd: string;
  filingType: string;
  value: number | null;
  growthRate: number | null;
  isSelected: boolean;
  isComparison: boolean;
};

type MetricOption = {
  key: MetricKey;
  label: string;
  barColor: string;
  lineColor: string;
  getValue: (statement: FinancialPayload) => number | null | undefined;
};

const METRIC_OPTIONS: MetricOption[] = [
  {
    key: "revenue",
    label: "Revenue",
    barColor: "var(--accent)",
    lineColor: "var(--warning)",
    getValue: (statement) => statement.revenue,
  },
  {
    key: "net_income",
    label: "Net Income",
    barColor: "var(--positive)",
    lineColor: "var(--accent)",
    getValue: (statement) => statement.net_income,
  },
  {
    key: "free_cash_flow",
    label: "Free Cash Flow",
    barColor: "var(--warning)",
    lineColor: "var(--positive)",
    getValue: (statement) => statement.free_cash_flow,
  },
];

interface GrowthWaterfallChartProps {
  financials: FinancialPayload[];
  visibleFinancials?: FinancialPayload[];
  chartState?: SharedFinancialChartState;
}

export function GrowthWaterfallChart({
  financials,
  visibleFinancials = [],
  chartState,
}: GrowthWaterfallChartProps) {
  const [metricKey, setMetricKey] = useState<MetricKey>("revenue");

  const annualFinancials = useMemo(
    () =>
      financials
        .filter((statement) => ANNUAL_FORMS.has(statement.filing_type))
        .sort((left, right) => Date.parse(right.period_end) - Date.parse(left.period_end)),
    [financials]
  );
  const selectedAnnual = useMemo(
    () => coerceAnnualStatement(chartState?.selectedFinancial ?? null, annualFinancials),
    [annualFinancials, chartState?.selectedFinancial]
  );
  const comparisonAnnual = useMemo(
    () => resolveComparisonStatement(selectedAnnual, chartState?.comparisonFinancial ?? null, annualFinancials),
    [annualFinancials, chartState?.comparisonFinancial, selectedAnnual]
  );
  const scopedAnnuals = useMemo(
    () => annualTrendScope(annualFinancials, visibleFinancials, selectedAnnual, comparisonAnnual),
    [annualFinancials, comparisonAnnual, selectedAnnual, visibleFinancials]
  );
  const metric = useMemo(
    () => METRIC_OPTIONS.find((option) => option.key === metricKey) ?? METRIC_OPTIONS[0],
    [metricKey]
  );
  const chartData = useMemo(
    () => buildChartData(scopedAnnuals, metric, selectedAnnual, comparisonAnnual),
    [comparisonAnnual, metric, scopedAnnuals, selectedAnnual]
  );
  const focusPoint = chartData.find((point) => point.isSelected) ?? null;
  const comparisonPoint = chartData.find((point) => point.isComparison) ?? null;
  const summaryPoint = focusPoint ?? chartData.at(-1) ?? null;
  const hasMetricHistory = chartData.some((point) => point.value !== null);
  const warnings = useMemo(
    () =>
      buildWarnings({
        selectedFinancial: chartState?.selectedFinancial ?? null,
        comparisonFinancial: chartState?.comparisonFinancial ?? null,
        selectedAnnual,
        comparisonAnnual,
        trendPointCount: chartData.length,
        metricLabel: metric.label,
      }),
    [chartData.length, chartState?.comparisonFinancial, chartState?.selectedFinancial, comparisonAnnual, metric.label, selectedAnnual]
  );
  const mode = resolveSnapshotSurfaceMode({
    comparisonAvailable: comparisonPoint !== null,
    trendAvailable: chartData.length > 1,
    capabilities: CAPABILITIES,
  });

  if (!annualFinancials.length || !selectedAnnual) {
    return <PanelEmptyState message="No annual filing history is available yet for value-plus-growth comparison." />;
  }

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <SnapshotSurfaceStatus capabilities={CAPABILITIES} mode={mode} warnings={warnings} />

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {METRIC_OPTIONS.map((option) => (
          <button
            key={option.key}
            type="button"
            className={`chart-chip${metric.key === option.key ? " chart-chip-active" : ""}`}
            aria-pressed={metric.key === option.key}
            onClick={() => setMetricKey(option.key)}
          >
            {option.label}
          </button>
        ))}
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <span className="pill tone-cyan">Focus {formatAnnualLabel(selectedAnnual)}</span>
        {comparisonAnnual ? <span className="pill tone-gold">Compare {formatAnnualLabel(comparisonAnnual)}</span> : null}
        <span className="pill">Visible annual periods {chartData.length}</span>
        <span className="pill">Metric {metric.label}</span>
      </div>

      {summaryPoint ? (
        <div className="cash-waterfall-meta">
          <span className="pill">Period {summaryPoint.period}</span>
          <span className="pill">{metric.label} {formatCompactNumber(summaryPoint.value)}</span>
          <span className="pill">YoY Growth {formatPercent(summaryPoint.growthRate)}</span>
          <span className="pill">Filed {formatDate(summaryPoint.periodEnd)}</span>
        </div>
      ) : null}

      {summaryPoint && comparisonPoint ? (
        <div className="cash-waterfall-meta">
          <span className="pill tone-gold">{metric.label} Δ {formatSignedCompactDelta(difference(summaryPoint.value, comparisonPoint.value))}</span>
          <span className="pill tone-gold">YoY Δ {formatSignedPointDelta(toGrowthPointDelta(summaryPoint.growthRate, comparisonPoint.growthRate))}</span>
        </div>
      ) : null}

      {hasMetricHistory ? (
        <div style={{ width: "100%", height: 340 }}>
          <ResponsiveContainer>
            <ComposedChart data={chartData} margin={{ top: 10, right: 18, left: 4, bottom: 8 }}>
              <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
              <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
              <YAxis
                yAxisId="value"
                stroke={CHART_AXIS_COLOR}
                tick={chartTick()}
                tickFormatter={(value) => formatCompactNumber(Number(value))}
                width={78}
              />
              <YAxis
                yAxisId="growth"
                orientation="right"
                stroke={CHART_AXIS_COLOR}
                tick={chartTick()}
                tickFormatter={(value) => formatPercent(Number(value))}
                width={64}
              />
              <ReferenceLine yAxisId="value" y={0} stroke="var(--panel-border)" />
              {comparisonPoint ? <ReferenceLine x={comparisonPoint.period} yAxisId="value" stroke="var(--warning)" strokeDasharray="4 3" /> : null}
              {focusPoint ? <ReferenceLine x={focusPoint.period} yAxisId="value" stroke="var(--accent)" strokeDasharray="4 3" /> : null}
              <Tooltip
                {...RECHARTS_TOOLTIP_PROPS}
                formatter={(value, name) => {
                  const numericValue = coerceTooltipNumber(value);
                  if (name === "YoY Growth") {
                    return formatPercent(numericValue);
                  }
                  return formatCompactNumber(numericValue);
                }}
              />
              <Legend formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}>{value}</span>} />
              <Bar yAxisId="value" dataKey="value" name={metric.label} fill={metric.barColor} radius={[4, 4, 0, 0]} />
              <Line
                yAxisId="growth"
                type="monotone"
                dataKey="growthRate"
                name="YoY Growth"
                stroke={metric.lineColor}
                strokeWidth={2.4}
                dot={{ r: 3, fill: metric.lineColor, strokeWidth: 0 }}
                activeDot={{ r: 5, fill: metric.lineColor, stroke: "var(--panel)", strokeWidth: 2 }}
                connectNulls
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <PanelEmptyState
          message={`No annual ${metric.label.toLowerCase()} history is available in the current shared range yet.`}
          kicker="Selected metric"
          title="Nothing to chart"
          minHeight={280}
        />
      )}
    </div>
  );
}

function buildChartData(
  annuals: FinancialPayload[],
  metric: MetricOption,
  selectedAnnual: FinancialPayload | null,
  comparisonAnnual: FinancialPayload | null
): AnnualGrowthPoint[] {
  const selectedKey = selectedAnnual ? buildAnnualKey(selectedAnnual) : null;
  const comparisonKey = comparisonAnnual ? buildAnnualKey(comparisonAnnual) : null;
  const ascendingAnnuals = [...annuals].reverse();

  return ascendingAnnuals.map((statement, index) => {
    const previous = ascendingAnnuals[index - 1] ?? null;
    const value = metric.getValue(statement) ?? null;
    const previousValue = previous ? metric.getValue(previous) ?? null : null;

    return {
      period: String(new Date(statement.period_end).getUTCFullYear()),
      periodEnd: statement.period_end,
      filingType: statement.filing_type,
      value,
      growthRate: growthRate(value, previousValue),
      isSelected: buildAnnualKey(statement) === selectedKey,
      isComparison: buildAnnualKey(statement) === comparisonKey,
    };
  });
}

function buildAnnualKey(statement: Pick<FinancialPayload, "period_end" | "filing_type">): string {
  return `${statement.period_end}|${statement.filing_type}`;
}

function coerceAnnualStatement(selectedFinancial: FinancialPayload | null, annualFinancials: FinancialPayload[]): FinancialPayload | null {
  if (!selectedFinancial) {
    return annualFinancials[0] ?? null;
  }
  if (ANNUAL_FORMS.has(selectedFinancial.filing_type)) {
    return selectedFinancial;
  }
  const selectedYear = new Date(selectedFinancial.period_end).getUTCFullYear();
  return annualFinancials.find((statement) => new Date(statement.period_end).getUTCFullYear() === selectedYear) ?? annualFinancials[0] ?? null;
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
  const selectedIndex = annualFinancials.findIndex((statement) => buildAnnualKey(statement) === buildAnnualKey(selectedAnnual));
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

  const scopedAnnuals = visibleYears.size
    ? annualFinancials.filter((statement) => {
        const year = new Date(statement.period_end).getUTCFullYear();
        return visibleYears.has(year) || pinnedYears.has(year);
      })
    : annualFinancials;

  return scopedAnnuals.length ? scopedAnnuals : annualFinancials;
}

function growthRate(current: number | null | undefined, previous: number | null | undefined): number | null {
  if (current === null || current === undefined || previous === null || previous === undefined || previous === 0) {
    return null;
  }
  return (current - previous) / Math.abs(previous);
}

function coerceTooltipNumber(value: unknown): number | null {
  if (Array.isArray(value)) {
    return coerceTooltipNumber(value[0]);
  }
  if (value === null || value === undefined) {
    return null;
  }
  const numericValue = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numericValue) ? numericValue : null;
}

function toGrowthPointDelta(current: number | null, previous: number | null): number | null {
  const delta = difference(current, previous);
  return delta == null ? null : delta * 100;
}

function formatAnnualLabel(statement: Pick<FinancialPayload, "period_end" | "filing_type">): string {
  return `${statement.filing_type} ${new Date(statement.period_end).getUTCFullYear()}`;
}

function buildWarnings({
  selectedFinancial,
  comparisonFinancial,
  selectedAnnual,
  comparisonAnnual,
  trendPointCount,
  metricLabel,
}: {
  selectedFinancial: FinancialPayload | null;
  comparisonFinancial: FinancialPayload | null;
  selectedAnnual: FinancialPayload | null;
  comparisonAnnual: FinancialPayload | null;
  trendPointCount: number;
  metricLabel: string;
}): SnapshotSurfaceWarning[] {
  const warnings: SnapshotSurfaceWarning[] = [];

  if (selectedFinancial && selectedAnnual && !ANNUAL_FORMS.has(selectedFinancial.filing_type)) {
    warnings.push({
      code: "selected_annual_fallback",
      label: "Annual fallback applied",
      detail: `The selected ${selectedFinancial.filing_type} filing is mapped to ${formatAnnualLabel(selectedAnnual)} so year-over-year growth stays comparable.`,
      tone: "info",
    });
  }

  if (comparisonFinancial && comparisonAnnual && !ANNUAL_FORMS.has(comparisonFinancial.filing_type)) {
    warnings.push({
      code: "comparison_annual_fallback",
      label: "Comparison fallback applied",
      detail: `The comparison ${comparisonFinancial.filing_type} filing is mapped to ${formatAnnualLabel(comparisonAnnual)} for a fiscal-year growth baseline.`,
      tone: "info",
    });
  }

  if (trendPointCount < 2) {
    warnings.push({
      code: "need_more_annual_history",
      label: "Need more annual history",
      detail: `${metricLabel} growth needs at least two annual filings in the current scope before the YoY line becomes meaningful.`,
      tone: "warning",
    });
  }

  return dedupeSnapshotSurfaceWarnings(warnings);
}