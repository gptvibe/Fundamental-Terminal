"use client";

import type { CSSProperties } from "react";
import { useMemo } from "react";

import { PanelEmptyState } from "@/components/company/panel-empty-state";
import { formatPercent } from "@/lib/format";
import type { FinancialPayload } from "@/lib/types";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);

type RatioMetricKey =
  | "grossMargin"
  | "operatingMargin"
  | "netMargin"
  | "fcfMargin"
  | "roa"
  | "roe"
  | "debtToAssets"
  | "currentRatio"
  | "revenueGrowth"
  | "netIncomeGrowth";

type RatioDirection = "higher" | "lower";
type CellTone = "positive" | "negative" | "neutral" | "na";

type RatioMetricConfig = {
  key: RatioMetricKey;
  label: string;
  direction: RatioDirection | null;
  formatValue: (value: number | null) => string;
  getValue: (statement: FinancialPayload, annuals: FinancialPayload[]) => number | null;
};

type RatioHistoryState = {
  annuals: FinancialPayload[];
  columns: FinancialPayload[];
  selected: FinancialPayload;
  comparison: FinancialPayload | null;
  selectedLabel: string;
  comparisonLabel: string | null;
  usedAnnualFallback: boolean;
  comparisonAnnualMissing: boolean;
};

const RATIO_ROWS: RatioMetricConfig[] = [
  {
    key: "grossMargin",
    label: "Gross Margin",
    direction: "higher",
    formatValue: formatPercent,
    getValue: (statement) => safeDivide(statement.gross_profit, statement.revenue),
  },
  {
    key: "operatingMargin",
    label: "Operating Margin",
    direction: "higher",
    formatValue: formatPercent,
    getValue: (statement) => safeDivide(statement.operating_income, statement.revenue),
  },
  {
    key: "netMargin",
    label: "Net Margin",
    direction: "higher",
    formatValue: formatPercent,
    getValue: (statement) => safeDivide(statement.net_income, statement.revenue),
  },
  {
    key: "fcfMargin",
    label: "FCF Margin",
    direction: "higher",
    formatValue: formatPercent,
    getValue: (statement) => safeDivide(statement.free_cash_flow, statement.revenue),
  },
  {
    key: "roa",
    label: "ROA",
    direction: "higher",
    formatValue: formatPercent,
    getValue: (statement) => safeDivide(statement.net_income, statement.total_assets),
  },
  {
    key: "roe",
    label: "ROE",
    direction: "higher",
    formatValue: formatPercent,
    getValue: (statement) => safeDivide(statement.net_income, statement.stockholders_equity),
  },
  {
    key: "debtToAssets",
    label: "Debt / Assets",
    direction: "lower",
    formatValue: formatPercent,
    getValue: (statement) => safeDivide(statement.total_liabilities, statement.total_assets),
  },
  {
    key: "currentRatio",
    label: "Current Ratio",
    direction: "higher",
    formatValue: formatMultiple,
    getValue: (statement) => safeDivide(statement.current_assets, statement.current_liabilities),
  },
  {
    key: "revenueGrowth",
    label: "Revenue Growth YoY",
    direction: "higher",
    formatValue: formatPercent,
    getValue: (statement, annuals) => growthRate(statement.revenue, previousAnnualMetric(annuals, statement, (item) => item.revenue)),
  },
  {
    key: "netIncomeGrowth",
    label: "Net Income Growth YoY",
    direction: "higher",
    formatValue: formatPercent,
    getValue: (statement, annuals) => growthRate(statement.net_income, previousAnnualMetric(annuals, statement, (item) => item.net_income)),
  },
];

const STICKY_COLUMN_STYLE: CSSProperties = {
  position: "sticky",
  left: 0,
  zIndex: 2,
  background: "var(--panel)",
};

interface RatioHistoryTableProps {
  financials: FinancialPayload[];
  visibleFinancials?: FinancialPayload[];
  selectedFinancial?: FinancialPayload | null;
  comparisonFinancial?: FinancialPayload | null;
  showContextChips?: boolean;
  showTableNote?: boolean;
}

export function RatioHistoryTable({
  financials,
  visibleFinancials = [],
  selectedFinancial = null,
  comparisonFinancial = null,
  showContextChips = true,
  showTableNote = true,
}: RatioHistoryTableProps) {
  const state = useMemo(
    () => buildRatioHistoryState(financials, visibleFinancials, selectedFinancial, comparisonFinancial),
    [comparisonFinancial, financials, selectedFinancial, visibleFinancials]
  );

  if (!state) {
    return <PanelEmptyState message="No annual filing history is available yet for multi-year ratio analysis." />;
  }

  return (
    <div style={{ display: "grid", gap: 12 }}>
      {showContextChips ? (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <span className="pill tone-cyan">Focus {state.selectedLabel}</span>
          {state.comparisonLabel ? <span className="pill tone-gold">Compare {state.comparisonLabel}</span> : null}
          {state.usedAnnualFallback ? <span className="pill tone-gold">Annual fallback applied</span> : null}
          {state.comparisonAnnualMissing ? <span className="pill tone-red">Comparison annual unavailable</span> : null}
          <span className="pill">Annual periods {state.columns.length}</span>
        </div>
      ) : null}

      {showTableNote ? (
        <div className="company-data-table-note">
          Columns reflect annual filings in the current shared range. Cell tones compare each period against the prior displayed annual value when the direction is meaningful.
        </div>
      ) : null}

      <div className="company-data-table-shell">
        <table className="company-data-table company-data-table-wide" aria-label="Ratio history table" style={{ minWidth: Math.max(760, 220 + state.columns.length * 132) }}>
          <thead>
            <tr>
              <th style={{ ...STICKY_COLUMN_STYLE, zIndex: 3 }}>Ratio</th>
              {state.columns.map((statement) => (
                <th key={buildAnnualKey(statement)} style={buildHeaderStyle(statement, state.selected, state.comparison)}>
                  {formatAnnualHeader(statement)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {RATIO_ROWS.map((row, rowIndex) => (
              <tr key={row.key} data-ratio-key={row.key}>
                <td style={buildStickyMetricCellStyle(rowIndex)}>
                  <span className="company-data-cell-strong">{row.label}</span>
                </td>
                {state.columns.map((statement, columnIndex) => {
                  const value = row.getValue(statement, state.annuals);
                  const priorValue = columnIndex > 0 ? row.getValue(state.columns[columnIndex - 1], state.annuals) : null;
                  const tone = resolveCellTone(value, priorValue, row.direction);
                  const periodKey = buildAnnualKey(statement);

                  return (
                    <td key={`${row.key}-${periodKey}`} className="is-numeric" data-period-key={periodKey}>
                      <span
                        data-tone={tone}
                        style={buildValueToneStyle(tone)}
                        title={buildToneTitle(row.label, value, priorValue, tone, row.formatValue)}
                      >
                        {row.formatValue(value)}
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function buildRatioHistoryState(
  financials: FinancialPayload[],
  visibleFinancials: FinancialPayload[],
  selectedFinancial: FinancialPayload | null,
  comparisonFinancial: FinancialPayload | null
): RatioHistoryState | null {
  const annuals = [...financials]
    .filter((statement) => ANNUAL_FORMS.has(statement.filing_type))
    .sort((left, right) => Date.parse(right.period_end) - Date.parse(left.period_end));

  const selected = coerceAnnualStatement(selectedFinancial, annuals);
  if (!selected) {
    return null;
  }

  const comparison = resolveComparisonStatement(selected, comparisonFinancial, annuals);
  const scopedAnnuals = annualTrendScope(annuals, visibleFinancials, selected, comparison);

  return {
    annuals,
    columns: [...scopedAnnuals].reverse(),
    selected,
    comparison,
    selectedLabel: formatAnnualHeader(selected),
    comparisonLabel: comparison ? formatAnnualHeader(comparison) : null,
    usedAnnualFallback: Boolean(selectedFinancial && !ANNUAL_FORMS.has(selectedFinancial.filing_type)),
    comparisonAnnualMissing: Boolean(comparisonFinancial && !comparison),
  };
}

function coerceAnnualStatement(selectedFinancial: FinancialPayload | null, annuals: FinancialPayload[]): FinancialPayload | null {
  if (!selectedFinancial) {
    return annuals[0] ?? null;
  }
  if (ANNUAL_FORMS.has(selectedFinancial.filing_type)) {
    return selectedFinancial;
  }
  const selectedYear = new Date(selectedFinancial.period_end).getUTCFullYear();
  return annuals.find((statement) => new Date(statement.period_end).getUTCFullYear() === selectedYear) ?? annuals[0] ?? null;
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
  const selectedIndex = annuals.findIndex((statement) => buildAnnualKey(statement) === buildAnnualKey(selected));
  if (selectedIndex < 0) {
    return annuals[1] ?? null;
  }
  return annuals[selectedIndex + 1] ?? null;
}

function annualTrendScope(
  annuals: FinancialPayload[],
  visibleFinancials: FinancialPayload[],
  selected: FinancialPayload,
  comparison: FinancialPayload | null
): FinancialPayload[] {
  const pinnedYears = new Set<number>([new Date(selected.period_end).getUTCFullYear()]);
  if (comparison) {
    pinnedYears.add(new Date(comparison.period_end).getUTCFullYear());
  }

  const visibleYears = new Set(
    visibleFinancials
      .map((statement) => new Date(statement.period_end).getUTCFullYear())
      .filter((year) => Number.isFinite(year))
  );

  const scopedAnnuals = visibleYears.size
    ? annuals.filter((statement) => {
        const year = new Date(statement.period_end).getUTCFullYear();
        return visibleYears.has(year) || pinnedYears.has(year);
      })
    : annuals;

  if (scopedAnnuals.length) {
    return scopedAnnuals;
  }

  const selectedIndex = annuals.findIndex((statement) => buildAnnualKey(statement) === buildAnnualKey(selected));
  if (selectedIndex < 0) {
    return annuals;
  }
  return annuals.slice(selectedIndex);
}

function previousAnnualMetric(
  annuals: FinancialPayload[],
  statement: FinancialPayload,
  selectMetric: (statement: FinancialPayload) => number | null
): number | null {
  const currentIndex = annuals.findIndex((item) => buildAnnualKey(item) === buildAnnualKey(statement));
  if (currentIndex < 0) {
    return null;
  }
  return selectMetric(annuals[currentIndex + 1] ?? nullStatement);
}

const nullStatement = {
  revenue: null,
  net_income: null,
} as FinancialPayload;

function buildAnnualKey(statement: Pick<FinancialPayload, "period_end" | "filing_type">): string {
  return `${statement.period_end}|${statement.filing_type}`;
}

function formatAnnualHeader(statement: Pick<FinancialPayload, "period_end" | "filing_type">): string {
  const year = new Date(statement.period_end).getUTCFullYear();
  return `${statement.filing_type} ${Number.isFinite(year) ? year : statement.period_end}`;
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

function formatMultiple(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "\u2014";
  }
  return `${value.toFixed(2)}x`;
}

function resolveCellTone(current: number | null, prior: number | null, direction: RatioDirection | null): CellTone {
  if (direction === null || current === null || prior === null || Number.isNaN(current) || Number.isNaN(prior)) {
    return "na";
  }
  const delta = current - prior;
  if (Math.abs(delta) < 1e-9) {
    return "neutral";
  }
  if (direction === "lower") {
    return delta < 0 ? "positive" : "negative";
  }
  return delta > 0 ? "positive" : "negative";
}

function buildHeaderStyle(
  statement: Pick<FinancialPayload, "period_end" | "filing_type">,
  selected: FinancialPayload,
  comparison: FinancialPayload | null
): CSSProperties {
  const key = buildAnnualKey(statement);
  if (key === buildAnnualKey(selected)) {
    return {
      background: "color-mix(in srgb, var(--accent) 12%, var(--panel))",
      color: "var(--accent)",
    };
  }
  if (comparison && key === buildAnnualKey(comparison)) {
    return {
      background: "color-mix(in srgb, var(--warning) 12%, var(--panel))",
      color: "var(--warning)",
    };
  }
  return {};
}

function buildStickyMetricCellStyle(rowIndex: number): CSSProperties {
  return {
    ...STICKY_COLUMN_STYLE,
    background: rowIndex % 2 === 0 ? "var(--panel)" : "color-mix(in srgb, var(--text) 2%, var(--panel))",
  };
}

function buildValueToneStyle(tone: CellTone): CSSProperties {
  if (tone === "positive") {
    return {
      display: "inline-block",
      padding: "4px 8px",
      borderRadius: 999,
      background: "color-mix(in srgb, var(--positive) 12%, transparent)",
      color: "color-mix(in srgb, var(--positive) 84%, var(--text))",
    };
  }
  if (tone === "negative") {
    return {
      display: "inline-block",
      padding: "4px 8px",
      borderRadius: 999,
      background: "color-mix(in srgb, var(--danger) 12%, transparent)",
      color: "color-mix(in srgb, var(--danger) 80%, var(--text))",
    };
  }
  if (tone === "neutral") {
    return {
      display: "inline-block",
      padding: "4px 8px",
      borderRadius: 999,
      background: "color-mix(in srgb, var(--accent) 8%, transparent)",
      color: "var(--text)",
    };
  }
  return {
    display: "inline-block",
    padding: "4px 8px",
    borderRadius: 999,
    color: "var(--text)",
  };
}

function buildToneTitle(
  label: string,
  current: number | null,
  prior: number | null,
  tone: CellTone,
  formatValue: (value: number | null) => string
): string | undefined {
  if (current === null) {
    return `${label}: unavailable for this period`;
  }
  if (tone === "na") {
    return `${label}: ${formatValue(current)}`;
  }
  if (prior === null) {
    return `${label}: ${formatValue(current)}`;
  }
  if (tone === "neutral") {
    return `${label}: unchanged versus prior annual value (${formatValue(prior)})`;
  }
  return `${label}: ${tone === "positive" ? "improved" : "deteriorated"} versus prior annual value (${formatValue(prior)})`;
}