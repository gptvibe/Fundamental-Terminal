"use client";

import { useMemo } from "react";
import type { CSSProperties } from "react";

import { difference, formatSignedCompactDelta } from "@/lib/financial-chart-state";
import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import type { FinancialPayload } from "@/lib/types";

type BankMetricConfig = {
  key: string;
  label: string;
  selectValue: (statement: FinancialPayload) => number | null | undefined;
  formatValue: (value: number | null | undefined) => string;
};

const BANK_METRICS: BankMetricConfig[] = [
  { key: "net_interest_income", label: "Net Interest Income", selectValue: (statement) => statement.regulated_bank?.net_interest_income ?? null, formatValue: formatCompactNumber },
  { key: "provision", label: "Provision", selectValue: (statement) => statement.regulated_bank?.provision_for_credit_losses ?? null, formatValue: formatCompactNumber },
  { key: "nim", label: "Net Interest Margin", selectValue: (statement) => statement.regulated_bank?.net_interest_margin ?? null, formatValue: formatPercent },
  { key: "deposits", label: "Deposits", selectValue: (statement) => statement.regulated_bank?.deposits_total ?? null, formatValue: formatCompactNumber },
  { key: "core_mix", label: "Core Deposit Mix", selectValue: (statement) => safeRatio(statement.regulated_bank?.core_deposits ?? null, statement.regulated_bank?.deposits_total ?? null), formatValue: formatPercent },
  { key: "uninsured_mix", label: "Uninsured Mix", selectValue: (statement) => safeRatio(statement.regulated_bank?.uninsured_deposits ?? null, statement.regulated_bank?.deposits_total ?? null), formatValue: formatPercent },
  { key: "cet1", label: "CET1", selectValue: (statement) => statement.regulated_bank?.common_equity_tier1_ratio ?? null, formatValue: formatPercent },
  { key: "total_capital", label: "Total Capital", selectValue: (statement) => statement.regulated_bank?.total_risk_based_capital_ratio ?? null, formatValue: formatPercent },
  { key: "net_income", label: "Net Income", selectValue: (statement) => statement.net_income ?? null, formatValue: formatCompactNumber },
];

interface BankFinancialStatementsTableProps {
  financials: FinancialPayload[];
  ticker: string;
  showComparison?: boolean;
  selectedPeriodKey?: string | null;
  comparisonPeriodKey?: string | null;
  selectedFinancial?: FinancialPayload | null;
  comparisonFinancial?: FinancialPayload | null;
}

export function BankFinancialStatementsTable({
  financials,
  ticker,
  showComparison = false,
  selectedPeriodKey = null,
  comparisonPeriodKey = null,
  selectedFinancial = null,
  comparisonFinancial = null,
}: BankFinancialStatementsTableProps) {
  const activeFinancial = selectedFinancial ?? findFinancialByKey(financials, selectedPeriodKey) ?? financials[0] ?? null;
  const activeComparisonFinancial = showComparison
    ? comparisonFinancial ?? findFinancialByKey(financials, comparisonPeriodKey)
    : null;
  const exportedFinancials = useMemo(
    () => buildVisibleStatements(activeFinancial, activeComparisonFinancial),
    [activeComparisonFinancial, activeFinancial]
  );
  const jsonPayload = useMemo(() => JSON.stringify(exportedFinancials, null, 2), [exportedFinancials]);
  const csvPayload = useMemo(() => buildBankFinancialsCsv(exportedFinancials), [exportedFinancials]);

  return (
    <div className="financial-statements-stack">
      <div className="financial-export-row">
        <div className="financial-trend-table-note">Download the currently focused regulated-bank statement view for review and model work.</div>
        <div className="financial-export-actions">
          <button
            type="button"
            className="ticker-button financial-export-button"
            onClick={() => triggerDownload(`${ticker}-regulated-bank-financials.csv`, csvPayload, "text/csv;charset=utf-8")}
          >
            Download CSV
          </button>
          <button
            type="button"
            className="ticker-button financial-export-button"
            onClick={() => triggerDownload(`${ticker}-regulated-bank-financials.json`, jsonPayload, "application/json;charset=utf-8")}
          >
            Download JSON
          </button>
        </div>
      </div>

      {(activeFinancial || activeComparisonFinancial) ? (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {activeFinancial ? <span className="pill tone-cyan">Focus {formatStatementLabel(activeFinancial)}</span> : null}
          {activeComparisonFinancial ? <span className="pill tone-gold">Compare {formatStatementLabel(activeComparisonFinancial)}</span> : null}
          {showComparison && !activeComparisonFinancial ? <span className="pill tone-red">No comparison period is available in the current view</span> : null}
        </div>
      ) : null}

      <div className="financial-table-shell">
        <table className="financial-table" style={{ minWidth: 820 }}>
          <thead>
            <tr>
              <th>Metric</th>
              <th>{activeFinancial ? formatStatementHeader(activeFinancial) : "Selected Period"}</th>
              {activeComparisonFinancial ? <th>{formatStatementHeader(activeComparisonFinancial)}</th> : null}
              {activeComparisonFinancial ? <th>Absolute Change</th> : null}
              {activeComparisonFinancial ? <th>Percent Change</th> : null}
            </tr>
          </thead>
          <tbody>
            {BANK_METRICS.map((metric) => {
              const activeValue = activeFinancial ? metric.selectValue(activeFinancial) : null;
              const comparisonValue = activeComparisonFinancial ? metric.selectValue(activeComparisonFinancial) : null;
              const absoluteChange = activeComparisonFinancial ? difference(activeValue, comparisonValue) : null;
              const relativeChange = activeComparisonFinancial ? calculateRelativeChange(activeValue, comparisonValue) : null;
              const toneStyle = resolveBankRowStyle(absoluteChange);

              return (
                <tr key={metric.key}>
                  <td>{metric.label}</td>
                  <td>{metric.formatValue(activeValue)}</td>
                  {activeComparisonFinancial ? <td>{metric.formatValue(comparisonValue)}</td> : null}
                  {activeComparisonFinancial ? <td style={toneStyle}>{formatSignedCompactDelta(absoluteChange)}</td> : null}
                  {activeComparisonFinancial ? <td style={toneStyle}>{formatPercent(relativeChange)}</td> : null}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function buildBankFinancialsCsv(financials: FinancialPayload[]): string {
  const header = [
    "period_end",
    "filing_type",
    "net_interest_income",
    "provision_for_credit_losses",
    "net_interest_margin",
    "deposits_total",
    "core_deposit_ratio",
    "uninsured_deposit_ratio",
    "common_equity_tier1_ratio",
    "total_risk_based_capital_ratio",
    "net_income",
  ];

  const rows = financials.map((statement) => {
    const bank = statement.regulated_bank ?? null;
    return [
      statement.period_end,
      statement.filing_type,
      bank?.net_interest_income ?? "",
      bank?.provision_for_credit_losses ?? "",
      bank?.net_interest_margin ?? "",
      bank?.deposits_total ?? "",
      safeRatio(bank?.core_deposits ?? null, bank?.deposits_total ?? null) ?? "",
      safeRatio(bank?.uninsured_deposits ?? null, bank?.deposits_total ?? null) ?? "",
      bank?.common_equity_tier1_ratio ?? "",
      bank?.total_risk_based_capital_ratio ?? "",
      statement.net_income ?? "",
    ];
  });

  return [header, ...rows]
    .map((row) => row.map((value) => csvEscape(value)).join(","))
    .join("\n");
}

function csvEscape(value: unknown): string {
  const text = String(value ?? "");
  if (!/[",\n]/.test(text)) {
    return text;
  }
  return `"${text.replaceAll("\"", "\"\"")}"`;
}

function triggerDownload(fileName: string, payload: string, mimeType: string) {
  const blob = new Blob([payload], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

function safeRatio(numerator: number | null, denominator: number | null): number | null {
  if (numerator == null || denominator == null || denominator === 0) {
    return null;
  }
  return numerator / denominator;
}

function resolveBankRowStyle(
  value: number | null
): CSSProperties | undefined {
  if (value == null || Number.isNaN(value)) {
    return { color: "var(--text-muted)", fontWeight: 600 };
  }
  if (value > 0) {
    return { color: "var(--positive)", fontWeight: 700 };
  }
  if (value < 0) {
    return { color: "var(--negative)", fontWeight: 700 };
  }
  return { color: "var(--text-muted)", fontWeight: 600 };
}

function calculateRelativeChange(current: number | null | undefined, previous: number | null | undefined): number | null {
  if (current == null || previous == null || Number.isNaN(current) || Number.isNaN(previous) || previous === 0) {
    return null;
  }
  return (current - previous) / Math.abs(previous);
}

function findFinancialByKey(financials: FinancialPayload[], key: string | null): FinancialPayload | null {
  if (!key) {
    return null;
  }
  return financials.find((statement) => buildStatementKey(statement) === key) ?? null;
}

function buildVisibleStatements(
  activeFinancial: FinancialPayload | null,
  comparisonFinancial: FinancialPayload | null
): FinancialPayload[] {
  const visibleStatements = [activeFinancial, comparisonFinancial].filter((statement): statement is FinancialPayload => Boolean(statement));
  const seenKeys = new Set<string>();
  return visibleStatements.filter((statement) => {
    const statementKey = buildStatementKey(statement);
    if (seenKeys.has(statementKey)) {
      return false;
    }
    seenKeys.add(statementKey);
    return true;
  });
}

function buildStatementKey(statement: Pick<FinancialPayload, "period_end" | "filing_type">): string {
  return `${statement.period_end}|${statement.filing_type}`;
}

function formatStatementLabel(statement: Pick<FinancialPayload, "period_end" | "filing_type">): string {
  return `${statement.filing_type} ${formatDate(statement.period_end)}`;
}

function formatStatementHeader(statement: Pick<FinancialPayload, "period_end" | "filing_type">): string {
  return `${statement.filing_type} ${formatDate(statement.period_end)}`;
}