"use client";

import type { CSSProperties } from "react";
import { useMemo } from "react";

import { PanelEmptyState } from "@/components/company/panel-empty-state";
import { SnapshotSurfaceStatus } from "@/components/company/snapshot-surface-status";
import { buildAnnualKey, buildAnnualSurfaceWarnings, formatAnnualHeader, resolveAnnualFinancialScope } from "@/lib/annual-financial-scope";
import { showAppToast } from "@/lib/app-toast";
import { buildPlainTextTable, copyTextToClipboard, exportRowsToCsv, normalizeExportFileStem, type ExportRow } from "@/lib/export";
import type { SharedFinancialChartState } from "@/lib/financial-chart-state";
import { formatPercent } from "@/lib/format";
import { dedupeSnapshotSurfaceWarnings, resolveSnapshotSurfaceMode, type SnapshotSurfaceCapabilities } from "@/lib/snapshot-surface";
import type { FinancialPayload } from "@/lib/types";

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
  annualScope: ReturnType<typeof resolveAnnualFinancialScope>;
};

const CAPABILITIES: SnapshotSurfaceCapabilities = {
  supports_selected_period: true,
  supports_compare_mode: true,
  supports_trend_mode: true,
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
  chartState?: SharedFinancialChartState;
  selectedFinancial?: FinancialPayload | null;
  comparisonFinancial?: FinancialPayload | null;
  showContextChips?: boolean;
  showTableNote?: boolean;
  ticker?: string;
}

export function RatioHistoryTable({
  financials,
  visibleFinancials = [],
  chartState,
  selectedFinancial = null,
  comparisonFinancial = null,
  showContextChips = true,
  showTableNote = true,
  ticker,
}: RatioHistoryTableProps) {
  const resolvedSelectedFinancial = chartState?.selectedFinancial ?? selectedFinancial;
  const resolvedComparisonFinancial = chartState?.comparisonFinancial ?? comparisonFinancial;
  const state = useMemo(
    () => buildRatioHistoryState(financials, visibleFinancials, resolvedSelectedFinancial, resolvedComparisonFinancial),
    [financials, resolvedComparisonFinancial, resolvedSelectedFinancial, visibleFinancials]
  );
  const warnings = useMemo(
    () => {
      if (!state) {
        return [];
      }

      return dedupeSnapshotSurfaceWarnings(
        buildAnnualSurfaceWarnings({
          chartState,
          scope: state.annualScope,
          selectedFinancial: resolvedSelectedFinancial,
          comparisonFinancial: resolvedComparisonFinancial,
          trendPointCount: state.columns.length,
          sparseHistoryDetail: "Only one comparable annual filing is visible, so the matrix is limited to a single fiscal-year column.",
        })
      );
    },
    [chartState, resolvedComparisonFinancial, resolvedSelectedFinancial, state]
  );
  const mode = resolveSnapshotSurfaceMode({
    comparisonAvailable: state?.comparison !== null,
    trendAvailable: (state?.columns.length ?? 0) > 1,
    capabilities: CAPABILITIES,
  });

  if (!state) {
    return <PanelEmptyState message="No annual filing history is available yet for multi-year ratio analysis." />;
  }

  const exportStem = normalizeExportFileStem(ticker, "company");
  const csvRows = buildRatioHistoryExportRows(state);
  const plainTextPayload = buildRatioHistoryPlainText(state);

  async function handleCopyTable() {
    try {
      await copyTextToClipboard(plainTextPayload);
      showAppToast({ message: "Copied ratio history table.", tone: "info" });
    } catch (error) {
      showAppToast({
        message: error instanceof Error ? error.message : "Unable to copy the ratio history table.",
        tone: "danger",
      });
    }
  }

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <SnapshotSurfaceStatus capabilities={CAPABILITIES} mode={mode} warnings={warnings} />

      <div className="financial-export-row">
        <div className="company-data-table-note">Export the currently visible annual ratio matrix for the shared range selection.</div>
        <div className="financial-export-actions">
          <button
            type="button"
            className="ticker-button financial-export-button"
            onClick={() => exportRowsToCsv(`${exportStem}-ratio-history.csv`, csvRows)}
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

      {showContextChips ? (
        <div className="financial-inline-pills">
          <span className="pill tone-cyan">Focus {state.selectedLabel}</span>
          {state.comparisonLabel ? <span className="pill tone-gold">Compare {state.comparisonLabel}</span> : null}
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
  const annualScope = resolveAnnualFinancialScope({
    financials,
    visibleFinancials,
    selectedFinancial,
    comparisonFinancial,
  });
  const annuals = annualScope.annuals;
  const selected = annualScope.selectedAnnual;
  if (!selected) {
    return null;
  }

  const comparison = annualScope.comparisonAnnual;
  const scopedAnnuals = annualScope.scopedAnnuals;

  return {
    annuals,
    columns: [...scopedAnnuals].reverse(),
    selected,
    comparison,
    selectedLabel: formatAnnualHeader(selected),
    comparisonLabel: comparison ? formatAnnualHeader(comparison) : null,
    annualScope,
  };
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

function buildRatioHistoryExportRows(state: RatioHistoryState): ExportRow[] {
  return RATIO_ROWS.map((row) => {
    const exportRow: ExportRow = { ratio: row.label };

    for (const statement of state.columns) {
      exportRow[formatAnnualHeader(statement)] = row.formatValue(row.getValue(statement, state.annuals));
    }

    return exportRow;
  });
}

function buildRatioHistoryPlainText(state: RatioHistoryState): string {
  const headers = ["Ratio", ...state.columns.map((statement) => formatAnnualHeader(statement))];
  const rows = RATIO_ROWS.map((row) => [
    row.label,
    ...state.columns.map((statement) => row.formatValue(row.getValue(statement, state.annuals))),
  ]);

  return [
    "Ratio History",
    `Focus: ${state.selectedLabel}`,
    `Compare: ${state.comparisonLabel ?? "Not selected"}`,
    "",
    buildPlainTextTable(headers, rows),
  ].join("\n");
}