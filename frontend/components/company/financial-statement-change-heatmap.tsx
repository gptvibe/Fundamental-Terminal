"use client";

import { useMemo, useState } from "react";

import { MetricLabel } from "@/components/ui/metric-label";
import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import type { FinancialPayload } from "@/lib/types";

type StatementKind = "income" | "balance" | "cashflow";
type ChangeMode = "absolute" | "percent";

type HeatmapMetric = {
  key: keyof FinancialPayload;
  label: string;
  formatValue: (value: number | null | undefined) => string;
};

type HeatmapCell = {
  periodIndex: number;
  periodLabel: string;
  periodEnd: string;
  filingType: string;
  source: string;
  currentValue: number | null;
  previousValue: number | null;
  absoluteChange: number | null;
  percentChange: number | null;
  selectedChange: number | null;
};

type HeatmapRow = {
  key: string;
  label: string;
  cells: HeatmapCell[];
};

const INCOME_METRICS: HeatmapMetric[] = [
  { key: "revenue", label: "Revenue", formatValue: formatCompactNumber },
  { key: "gross_profit", label: "Gross Profit", formatValue: formatCompactNumber },
  { key: "operating_income", label: "Operating Income", formatValue: formatCompactNumber },
  { key: "net_income", label: "Net Income", formatValue: formatCompactNumber },
  { key: "eps", label: "EPS", formatValue: formatPerShareValue },
  { key: "sga", label: "SG&A", formatValue: formatCompactNumber },
  { key: "research_and_development", label: "R&D", formatValue: formatCompactNumber },
  { key: "interest_expense", label: "Interest Expense", formatValue: formatCompactNumber },
  { key: "income_tax_expense", label: "Income Tax Expense", formatValue: formatCompactNumber },
];

const BALANCE_METRICS: HeatmapMetric[] = [
  { key: "total_assets", label: "Total Assets", formatValue: formatCompactNumber },
  { key: "current_assets", label: "Current Assets", formatValue: formatCompactNumber },
  { key: "total_liabilities", label: "Total Liabilities", formatValue: formatCompactNumber },
  { key: "current_liabilities", label: "Current Liabilities", formatValue: formatCompactNumber },
  { key: "cash_and_cash_equivalents", label: "Cash & Equivalents", formatValue: formatCompactNumber },
  { key: "accounts_receivable", label: "Accounts Receivable", formatValue: formatCompactNumber },
  { key: "inventory", label: "Inventory", formatValue: formatCompactNumber },
  { key: "accounts_payable", label: "Accounts Payable", formatValue: formatCompactNumber },
  { key: "long_term_debt", label: "Long-Term Debt", formatValue: formatCompactNumber },
  { key: "stockholders_equity", label: "Stockholders Equity", formatValue: formatCompactNumber },
];

const CASHFLOW_METRICS: HeatmapMetric[] = [
  { key: "operating_cash_flow", label: "Operating Cash Flow", formatValue: formatCompactNumber },
  { key: "depreciation_and_amortization", label: "Depreciation & Amortization", formatValue: formatCompactNumber },
  { key: "capex", label: "Capex", formatValue: formatCompactNumber },
  { key: "acquisitions", label: "Acquisitions", formatValue: formatCompactNumber },
  { key: "debt_changes", label: "Debt Changes", formatValue: formatCompactNumber },
  { key: "dividends", label: "Dividends", formatValue: formatCompactNumber },
  { key: "share_buybacks", label: "Share Buybacks", formatValue: formatCompactNumber },
  { key: "stock_based_compensation", label: "Stock-Based Compensation", formatValue: formatCompactNumber },
  { key: "free_cash_flow", label: "Free Cash Flow", formatValue: formatCompactNumber },
];

const STATEMENT_OPTIONS: Array<{ key: StatementKind; label: string }> = [
  { key: "income", label: "Income Statement" },
  { key: "balance", label: "Balance Sheet" },
  { key: "cashflow", label: "Cash Flow" },
];

const MODE_OPTIONS: Array<{ key: ChangeMode; label: string }> = [
  { key: "absolute", label: "Absolute Change" },
  { key: "percent", label: "Percent Change" },
];

interface FinancialStatementChangeHeatmapProps {
  financials: FinancialPayload[];
}

export function FinancialStatementChangeHeatmap({ financials }: FinancialStatementChangeHeatmapProps) {
  const [statementKind, setStatementKind] = useState<StatementKind>("income");
  const [changeMode, setChangeMode] = useState<ChangeMode>("absolute");

  const metrics = useMemo(() => {
    if (statementKind === "income") {
      return INCOME_METRICS;
    }
    if (statementKind === "balance") {
      return BALANCE_METRICS;
    }
    return CASHFLOW_METRICS;
  }, [statementKind]);

  const rows = useMemo(() => buildHeatmapRows(financials, metrics, changeMode), [changeMode, financials, metrics]);

  const periods = useMemo(
    () =>
      financials.map((statement, index) => ({
        key: `${statement.period_end}:${index}`,
        periodLabel: formatPeriodLabel(statement),
      })),
    [financials]
  );

  const maxAbsChange = useMemo(() => {
    let max = 0;
    for (const row of rows) {
      for (const cell of row.cells) {
        const value = Math.abs(cell.selectedChange ?? 0);
        if (Number.isFinite(value) && value > max) {
          max = value;
        }
      }
    }
    return max;
  }, [rows]);

  if (!financials.length) {
    return <div className="text-muted">No statement history is available yet for the change heatmap.</div>;
  }

  if (!rows.length || periods.length < 2) {
    return <div className="text-muted">Need at least two comparable fiscal periods to render the change heatmap.</div>;
  }

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        {STATEMENT_OPTIONS.map((option) => (
          <button
            key={option.key}
            type="button"
            className={`chart-chip${statementKind === option.key ? " chart-chip-active" : ""}`}
            onClick={() => setStatementKind(option.key)}
          >
            {option.label}
          </button>
        ))}
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        {MODE_OPTIONS.map((option) => (
          <button
            key={option.key}
            type="button"
            className={`chart-chip${changeMode === option.key ? " chart-chip-active" : ""}`}
            onClick={() => setChangeMode(option.key)}
          >
            {option.label}
          </button>
        ))}
        <span className="pill">Rows: {rows.length}</span>
        <span className="pill">Columns: {periods.length}</span>
      </div>

      <div className="financial-table-shell">
        <table className="financial-table" style={{ minWidth: 980 }}>
          <thead>
            <tr>
              <th style={{ minWidth: 200 }}>Line Item</th>
              {periods.map((period) => (
                <th key={period.key}>{period.periodLabel}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key}>
                <td>
                  <MetricLabel label={row.label} metricKey={row.key} />
                </td>
                {row.cells.map((cell) => {
                  const intensity = resolveIntensity(cell.selectedChange, maxAbsChange);
                  const tone = resolveCellTone(cell.selectedChange);
                  const cellStyle = resolveCellStyle(intensity, tone);
                  const cellValue = formatCellChange(cell.selectedChange, changeMode);
                  const sourceHref = isSafeExternalLink(cell.source) ? cell.source : null;
                  const title = buildCellTitle({ cell, rowLabel: row.label, changeMode });

                  const content = (
                    <div style={{ display: "grid", gap: 2 }}>
                      <span>{cellValue}</span>
                      {cell.absoluteChange != null || cell.percentChange != null ? (
                        <span style={{ fontSize: 11, opacity: 0.8 }}>
                          {formatCompactNumber(cell.currentValue)} / {formatCompactNumber(cell.previousValue)}
                        </span>
                      ) : (
                        <span style={{ fontSize: 11, opacity: 0.7 }}>N/A</span>
                      )}
                    </div>
                  );

                  return (
                    <td key={`${row.key}:${cell.periodIndex}`} style={cellStyle} title={title}>
                      {sourceHref ? (
                        <a
                          href={sourceHref}
                          target="_blank"
                          rel="noreferrer"
                          style={{ color: "inherit", textDecoration: "none", display: "block" }}
                        >
                          {content}
                        </a>
                      ) : (
                        content
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <span className="pill">Intensity: low to high across visible cells</span>
        <span className="pill">Green = increase</span>
        <span className="pill">Red = decrease</span>
        <span className="pill">Click a cell to open filing/source URL when available</span>
      </div>
    </div>
  );
}

function buildHeatmapRows(financials: FinancialPayload[], metrics: HeatmapMetric[], mode: ChangeMode): HeatmapRow[] {
  return metrics
    .map((metric) => {
      const cells: HeatmapCell[] = financials.map((statement, index) => {
        const previousStatement = financials[index + 1] ?? null;
        const currentValue = asFiniteNumber(statement[metric.key]);
        const previousValue = previousStatement ? asFiniteNumber(previousStatement[metric.key]) : null;
        const absoluteChange = computeAbsoluteChange(currentValue, previousValue);
        const percentChange = computePercentChange(currentValue, previousValue);

        return {
          periodIndex: index,
          periodLabel: formatPeriodLabel(statement),
          periodEnd: statement.period_end,
          filingType: statement.filing_type,
          source: statement.source,
          currentValue,
          previousValue,
          absoluteChange,
          percentChange,
          selectedChange: mode === "absolute" ? absoluteChange : percentChange,
        };
      });

      const hasAnyChange = cells.some((cell) => cell.selectedChange != null);
      if (!hasAnyChange) {
        return null;
      }

      return {
        key: String(metric.key),
        label: metric.label,
        cells,
      };
    })
    .filter((row): row is HeatmapRow => row !== null);
}

function asFiniteNumber(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  return value;
}

function computeAbsoluteChange(currentValue: number | null, previousValue: number | null): number | null {
  if (currentValue == null || previousValue == null) {
    return null;
  }
  return currentValue - previousValue;
}

function computePercentChange(currentValue: number | null, previousValue: number | null): number | null {
  if (currentValue == null || previousValue == null || previousValue === 0) {
    return null;
  }
  return (currentValue - previousValue) / Math.abs(previousValue);
}

function resolveIntensity(change: number | null, maxAbsChange: number): number {
  if (change == null || maxAbsChange <= 0) {
    return 0;
  }
  return Math.min(1, Math.abs(change) / maxAbsChange);
}

function resolveCellTone(change: number | null): "neutral" | "positive" | "negative" {
  if (change == null || change === 0) {
    return "neutral";
  }
  return change > 0 ? "positive" : "negative";
}

function resolveCellStyle(intensity: number, tone: "neutral" | "positive" | "negative") {
  if (tone === "neutral" || intensity <= 0) {
    return {
      background: "color-mix(in srgb, var(--panel) 88%, var(--panel-border) 12%)",
      color: "var(--text-muted)",
      verticalAlign: "top",
    };
  }

  const alpha = 0.16 + intensity * 0.34;
  const color = tone === "positive" ? `rgba(29, 201, 112, ${alpha.toFixed(3)})` : `rgba(224, 82, 99, ${alpha.toFixed(3)})`;

  return {
    background: color,
    color: "var(--text)",
    verticalAlign: "top",
  };
}

function formatPeriodLabel(statement: FinancialPayload): string {
  return `${statement.filing_type} ${formatDate(statement.period_end)}`;
}

function formatPerShareValue(value: number | null | undefined): string {
  if (value == null) {
    return "?";
  }
  return value.toFixed(2);
}

function formatCellChange(value: number | null, mode: ChangeMode): string {
  if (value == null) {
    return "-";
  }
  if (mode === "percent") {
    return formatPercent(value);
  }
  return formatCompactNumber(value);
}

function isSafeExternalLink(value: string | null | undefined): boolean {
  if (!value) {
    return false;
  }
  return value.startsWith("http://") || value.startsWith("https://");
}

function buildCellTitle({
  cell,
  rowLabel,
  changeMode,
}: {
  cell: HeatmapCell;
  rowLabel: string;
  changeMode: ChangeMode;
}): string {
  const changeLabel = changeMode === "percent" ? formatPercent(cell.percentChange) : formatCompactNumber(cell.absoluteChange);
  return [
    `${rowLabel} - ${cell.periodLabel}`,
    `Change: ${changeLabel}`,
    `Current: ${formatCompactNumber(cell.currentValue)}`,
    `Previous: ${formatCompactNumber(cell.previousValue)}`,
    `Period End: ${formatDate(cell.periodEnd)}`,
    `Filing: ${cell.filingType}`,
    isSafeExternalLink(cell.source) ? `Source: ${cell.source}` : "Source: unavailable",
  ].join("\n");
}
