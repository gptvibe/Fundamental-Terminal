"use client";

import { useMemo, useState } from "react";

import { HistoricalSparklineCard, type HistoricalSparklinePoint } from "@/components/company/historical-sparkline-card";
import { SnapshotSurfaceStatus } from "@/components/company/snapshot-surface-status";
import { difference, formatSignedCompactDelta, formatSignedPointDelta } from "@/lib/financial-chart-state";
import type { FinancialPayload } from "@/lib/types";
import { formatCompactNumber, formatPercent } from "@/lib/format";
import { dedupeSnapshotSurfaceWarnings, resolveSnapshotSurfaceMode, type SnapshotSurfaceCapabilities, type SnapshotSurfaceWarning } from "@/lib/snapshot-surface";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);
const CAPABILITIES: SnapshotSurfaceCapabilities = {
  supports_selected_period: true,
  supports_compare_mode: true,
  supports_trend_mode: true,
};

type QualitySummaryState = {
  selected: FinancialPayload;
  comparison: FinancialPayload | null;
  selectedLabel: string;
  comparisonLabel: string | null;
  annuals: FinancialPayload[];
  trendRows: Array<{
    key: string;
    label: string;
    grossMargin: number | null;
    operatingMargin: number | null;
    fcfMargin: number | null;
    debtToAssets: number | null;
    roa: number | null;
    revenueGrowth: number | null;
    sharesOutstanding: number | null;
  }>;
  usedAnnualFallback: boolean;
};

type TrendView = "sparklines" | "table";

interface FinancialQualitySummaryProps {
  financials: FinancialPayload[];
  selectedFinancial?: FinancialPayload | null;
  comparisonFinancial?: FinancialPayload | null;
  visibleFinancials?: FinancialPayload[];
}

export function FinancialQualitySummary({
  financials,
  selectedFinancial = null,
  comparisonFinancial = null,
  visibleFinancials = [],
}: FinancialQualitySummaryProps) {
  const [trendView, setTrendView] = useState<TrendView>("sparklines");
  const summary = useMemo(() => buildSummary(financials, visibleFinancials, selectedFinancial, comparisonFinancial), [comparisonFinancial, financials, selectedFinancial, visibleFinancials]);

  if (!summary) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 220 }}>
        <div className="grid-empty-kicker">Quality summary</div>
        <div className="grid-empty-title">Not enough annual history yet</div>
        <div className="grid-empty-copy">This panel appears when annual filings provide at least one full period of normalized financial metrics.</div>
      </div>
    );
  }

  const warnings = buildWarnings(summary, selectedFinancial, comparisonFinancial);
  const mode = resolveSnapshotSurfaceMode({
    comparisonAvailable: summary.comparison !== null,
    trendAvailable: summary.trendRows.length > 1,
    capabilities: CAPABILITIES,
  });

  const marginDelta = difference(metricValue(summary.selected, "operatingMargin"), metricValue(summary.comparison, "operatingMargin"));
  const grossMarginDelta = difference(metricValue(summary.selected, "grossMargin"), metricValue(summary.comparison, "grossMargin"));
  const fcfMarginDelta = difference(metricValue(summary.selected, "fcfMargin"), metricValue(summary.comparison, "fcfMargin"));
  const debtDelta = difference(metricValue(summary.selected, "debtToAssets"), metricValue(summary.comparison, "debtToAssets"));
  const roaDelta = difference(metricValue(summary.selected, "roa"), metricValue(summary.comparison, "roa"));
  const sharesDelta = difference(summary.selected.shares_outstanding, summary.comparison?.shares_outstanding ?? null);
  const selectedKey = buildAnnualKey(summary.selected);
  const comparisonKey = summary.comparison ? buildAnnualKey(summary.comparison) : null;

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <SnapshotSurfaceStatus capabilities={CAPABILITIES} mode={mode} warnings={warnings} />

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <span className="pill tone-cyan">Focus {summary.selectedLabel}</span>
        {summary.comparisonLabel ? <span className="pill tone-gold">Compare {summary.comparisonLabel}</span> : null}
      </div>

      <div className="metric-grid">
        <Metric label="Gross Margin" value={formatPercent(metricValue(summary.selected, "grossMargin"))} />
        <Metric label="Operating Margin" value={formatPercent(metricValue(summary.selected, "operatingMargin"))} />
        <Metric label="FCF Margin" value={formatPercent(metricValue(summary.selected, "fcfMargin"))} />
        <Metric label="Debt / Assets" value={formatPercent(metricValue(summary.selected, "debtToAssets"))} />
      </div>

      <div className="metric-grid">
        <Metric label="ROA" value={formatPercent(metricValue(summary.selected, "roa"))} />
        <Metric label="YoY Revenue" value={formatPercent(growthRate(summary.selected.revenue, summary.comparison?.revenue ?? null))} />
        <Metric label="YoY Net Income" value={formatPercent(growthRate(summary.selected.net_income, summary.comparison?.net_income ?? null))} />
        <Metric label="Shares Outstanding" value={formatCompactNumber(summary.selected.shares_outstanding)} />
      </div>

      {summary.comparison ? (
        <div className="metric-grid">
          <Metric label="Gross Margin Delta" value={formatSignedPointDelta(grossMarginDelta == null ? null : grossMarginDelta * 100)} />
          <Metric label="Operating Margin Delta" value={formatSignedPointDelta(marginDelta == null ? null : marginDelta * 100)} />
          <Metric label="FCF Margin Delta" value={formatSignedPointDelta(fcfMarginDelta == null ? null : fcfMarginDelta * 100)} />
          <Metric label="Debt / Assets Delta" value={formatSignedPointDelta(debtDelta == null ? null : debtDelta * 100)} />
          <Metric label="ROA Delta" value={formatSignedPointDelta(roaDelta == null ? null : roaDelta * 100)} />
          <Metric label="Shares Delta" value={formatSignedCompactDelta(sharesDelta)} />
        </div>
      ) : null}

      {summary.trendRows.length ? (
        <>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <div className="cash-waterfall-toggle-group" role="tablist" aria-label="Financial quality history view">
              <button type="button" className={`chart-chip${trendView === "sparklines" ? " chart-chip-active" : ""}`} onClick={() => setTrendView("sparklines")}>
                Sparklines
              </button>
              <button type="button" className={`chart-chip${trendView === "table" ? " chart-chip-active" : ""}`} onClick={() => setTrendView("table")}>
                Trend Table
              </button>
            </div>
            <span className="pill">Annual periods {summary.trendRows.length}</span>
          </div>

          {trendView === "sparklines" ? (
            <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
              <HistoricalSparklineCard label="Gross Margin" value={formatPercent(metricValue(summary.selected, "grossMargin"))} delta={formatSignedPointDelta(grossMarginDelta == null ? null : grossMarginDelta * 100)} data={buildTrendSparklineData(summary.trendRows, "grossMargin", selectedKey, comparisonKey)} />
              <HistoricalSparklineCard label="Operating Margin" value={formatPercent(metricValue(summary.selected, "operatingMargin"))} delta={formatSignedPointDelta(marginDelta == null ? null : marginDelta * 100)} data={buildTrendSparklineData(summary.trendRows, "operatingMargin", selectedKey, comparisonKey)} color="var(--chart-series-2)" />
              <HistoricalSparklineCard label="FCF Margin" value={formatPercent(metricValue(summary.selected, "fcfMargin"))} delta={formatSignedPointDelta(fcfMarginDelta == null ? null : fcfMarginDelta * 100)} data={buildTrendSparklineData(summary.trendRows, "fcfMargin", selectedKey, comparisonKey)} color="var(--chart-series-3)" />
              <HistoricalSparklineCard label="Debt / Assets" value={formatPercent(metricValue(summary.selected, "debtToAssets"))} delta={formatSignedPointDelta(debtDelta == null ? null : debtDelta * 100)} data={buildTrendSparklineData(summary.trendRows, "debtToAssets", selectedKey, comparisonKey)} color="var(--chart-series-4)" />
              <HistoricalSparklineCard label="ROA" value={formatPercent(metricValue(summary.selected, "roa"))} delta={formatSignedPointDelta(roaDelta == null ? null : roaDelta * 100)} data={buildTrendSparklineData(summary.trendRows, "roa", selectedKey, comparisonKey)} color="var(--chart-series-5)" />
              <HistoricalSparklineCard label="Shares Outstanding" value={formatCompactNumber(summary.selected.shares_outstanding)} delta={formatSignedCompactDelta(sharesDelta)} data={buildTrendSparklineData(summary.trendRows, "sharesOutstanding", selectedKey, comparisonKey)} color="var(--chart-series-6)" />
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="company-data-table" style={{ minWidth: 760 }}>
                <thead>
                  <tr>
                    <th align="left">Period</th>
                    <th align="right">Gross Margin</th>
                    <th align="right">Op. Margin</th>
                    <th align="right">FCF Margin</th>
                    <th align="right">Debt / Assets</th>
                    <th align="right">ROA</th>
                    <th align="right">YoY Revenue</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.trendRows.map((row) => {
                    const isSelected = row.key === selectedKey;
                    const isComparison = comparisonKey ? row.key === comparisonKey : false;
                    return (
                      <tr
                        key={row.key}
                        style={isSelected ? { background: "color-mix(in srgb, var(--accent) 8%, transparent)" } : isComparison ? { background: "color-mix(in srgb, var(--warning) 8%, transparent)" } : undefined}
                      >
                        <td>{row.label}</td>
                        <td style={{ textAlign: "right" }}>{formatPercent(row.grossMargin)}</td>
                        <td style={{ textAlign: "right" }}>{formatPercent(row.operatingMargin)}</td>
                        <td style={{ textAlign: "right" }}>{formatPercent(row.fcfMargin)}</td>
                        <td style={{ textAlign: "right" }}>{formatPercent(row.debtToAssets)}</td>
                        <td style={{ textAlign: "right" }}>{formatPercent(row.roa)}</td>
                        <td style={{ textAlign: "right" }}>{formatPercent(row.revenueGrowth)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
    </div>
  );
}

function buildSummary(
  financials: FinancialPayload[],
  visibleFinancials: FinancialPayload[],
  selectedFinancial: FinancialPayload | null,
  comparisonFinancial: FinancialPayload | null
): QualitySummaryState | null {
  const annuals = financials
    .filter((item) => ANNUAL_FORMS.has(item.filing_type))
    .sort((left, right) => Date.parse(right.period_end) - Date.parse(left.period_end));

  const selected = coerceAnnualStatement(selectedFinancial, annuals);
  const previous = resolveComparisonStatement(selected, comparisonFinancial, annuals);
  if (!selected) {
    return null;
  }

  const trendScope = annualTrendScope(annuals, visibleFinancials, selected);

  return {
    selected,
    comparison: previous,
    selectedLabel: formatSummaryLabel(selected),
    comparisonLabel: previous ? formatSummaryLabel(previous) : null,
    annuals,
    trendRows: trendScope.slice(0, 5).map((statement) => ({
      key: buildAnnualKey(statement),
      label: formatSummaryLabel(statement),
      grossMargin: safeDivide(statement.gross_profit, statement.revenue),
      operatingMargin: safeDivide(statement.operating_income, statement.revenue),
      fcfMargin: safeDivide(statement.free_cash_flow, statement.revenue),
      debtToAssets: safeDivide(statement.total_liabilities, statement.total_assets),
      roa: safeDivide(statement.net_income, statement.total_assets),
      revenueGrowth: growthRate(statement.revenue, nextAnnualRevenue(annuals, statement)),
      sharesOutstanding: statement.shares_outstanding,
    })),
    usedAnnualFallback: Boolean(selectedFinancial && !ANNUAL_FORMS.has(selectedFinancial.filing_type)),
  };
}

function coerceAnnualStatement(
  selectedFinancial: FinancialPayload | null,
  annuals: FinancialPayload[]
): FinancialPayload | null {
  if (!selectedFinancial) {
    return annuals[0] ?? null;
  }
  if (ANNUAL_FORMS.has(selectedFinancial.filing_type)) {
    return selectedFinancial;
  }
  const selectedYear = new Date(selectedFinancial.period_end).getUTCFullYear();
  return annuals.find((item) => new Date(item.period_end).getUTCFullYear() === selectedYear) ?? annuals[0] ?? null;
}

function resolveComparisonStatement(
  selected: FinancialPayload | null,
  comparisonFinancial: FinancialPayload | null,
  annuals: FinancialPayload[]
): FinancialPayload | null {
  if (!selected) {
    return null;
  }
  if (comparisonFinancial && ANNUAL_FORMS.has(comparisonFinancial.filing_type)) {
    return comparisonFinancial;
  }
  const selectedKey = `${selected.period_end}|${selected.filing_type}`;
  const selectedIndex = annuals.findIndex((item) => `${item.period_end}|${item.filing_type}` === selectedKey);
  if (selectedIndex < 0) {
    return annuals[1] ?? null;
  }
  return annuals[selectedIndex + 1] ?? null;
}

function annualTrendScope(
  annuals: FinancialPayload[],
  visibleFinancials: FinancialPayload[],
  selected: FinancialPayload
): FinancialPayload[] {
  const visibleYears = new Set(
    visibleFinancials
      .map((statement) => new Date(statement.period_end).getUTCFullYear())
      .filter((year) => Number.isFinite(year))
  );

  const scopedAnnuals = visibleYears.size
    ? annuals.filter((statement) => visibleYears.has(new Date(statement.period_end).getUTCFullYear()))
    : annuals;

  if (scopedAnnuals.length) {
    return scopedAnnuals;
  }

  const selectedIndex = annuals.findIndex((statement) => buildAnnualKey(statement) === buildAnnualKey(selected));
  if (selectedIndex < 0) {
    return annuals;
  }
  return annuals.slice(selectedIndex, selectedIndex + 5);
}

function nextAnnualRevenue(annuals: FinancialPayload[], statement: FinancialPayload): number | null {
  const currentIndex = annuals.findIndex((item) => buildAnnualKey(item) === buildAnnualKey(statement));
  if (currentIndex < 0) {
    return null;
  }
  return annuals[currentIndex + 1]?.revenue ?? null;
}

function formatSummaryLabel(statement: FinancialPayload): string {
  const year = new Date(statement.period_end).getUTCFullYear();
  return Number.isFinite(year) ? `${statement.filing_type} ${year}` : `${statement.filing_type} ${statement.period_end}`;
}

function buildAnnualKey(statement: Pick<FinancialPayload, "period_end" | "filing_type">): string {
  return `${statement.period_end}|${statement.filing_type}`;
}

function metricValue(summary: FinancialPayload | null, metric: "grossMargin" | "operatingMargin" | "fcfMargin" | "debtToAssets" | "roa"): number | null {
  if (!summary) {
    return null;
  }
  if (metric === "grossMargin") {
    return safeDivide(summary.gross_profit, summary.revenue);
  }
  if (metric === "operatingMargin") {
    return safeDivide(summary.operating_income, summary.revenue);
  }
  if (metric === "fcfMargin") {
    return safeDivide(summary.free_cash_flow, summary.revenue);
  }
  if (metric === "debtToAssets") {
    return safeDivide(summary.total_liabilities, summary.total_assets);
  }
  return safeDivide(summary.net_income, summary.total_assets);
}

function buildWarnings(
  summary: QualitySummaryState,
  selectedFinancial: FinancialPayload | null,
  comparisonFinancial: FinancialPayload | null
): SnapshotSurfaceWarning[] {
  const warnings: SnapshotSurfaceWarning[] = [];
  if (summary.usedAnnualFallback && selectedFinancial) {
    warnings.push({
      code: "annual_only_fallback",
      label: "Annual fallback applied",
      detail: `Quality summary uses the annual filing for ${new Date(selectedFinancial.period_end).getUTCFullYear()} because these metrics are normalized on annual statements.`,
      tone: "info",
    });
  }
  if (comparisonFinancial && !summary.comparison) {
    warnings.push({
      code: "comparison_annual_missing",
      label: "Comparison annual unavailable",
      detail: "The selected comparison period does not have a comparable annual filing in the current history window.",
      tone: "warning",
    });
  }
  if (summary.trendRows.length < 2) {
    warnings.push({
      code: "quality_trend_sparse",
      label: "Sparse annual history",
      detail: "Only one comparable annual filing is visible, so the trend table is limited to the selected year.",
      tone: "info",
    });
  }
  return dedupeSnapshotSurfaceWarnings(warnings);
}

function safeDivide(numerator: number | null, denominator: number | null): number | null {
  if (numerator === null || denominator === null || denominator === 0) {
    return null;
  }
  return numerator / denominator;
}

function growthRate(current: number | null, previous: number | null): number | null {
  if (current === null || previous === null || previous === 0) {
    return null;
  }
  return (current - previous) / Math.abs(previous);
}

function buildTrendSparklineData(
  rows: QualitySummaryState["trendRows"],
  metric: keyof QualitySummaryState["trendRows"][number],
  selectedKey: string,
  comparisonKey: string | null
): HistoricalSparklinePoint[] {
  return [...rows].reverse().map((row) => ({
    label: row.label,
    value: typeof row[metric] === "number" ? (row[metric] as number) : row[metric] == null ? null : Number(row[metric]),
    isSelected: row.key === selectedKey,
    isComparison: comparisonKey ? row.key === comparisonKey : false,
  }));
}