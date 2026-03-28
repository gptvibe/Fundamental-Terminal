"use client";

import { useMemo } from "react";

import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import type { FinancialPayload } from "@/lib/types";

export function BankFinancialStatementsTable({ financials, ticker }: { financials: FinancialPayload[]; ticker: string }) {
  const jsonPayload = useMemo(() => JSON.stringify(financials, null, 2), [financials]);
  const csvPayload = useMemo(() => buildBankFinancialsCsv(financials), [financials]);

  return (
    <div className="financial-statements-stack">
      <div className="financial-export-row">
        <div className="financial-trend-table-note">Download the cached regulated-bank statement history for review and model work.</div>
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

      <div className="financial-table-shell" style={{ maxHeight: 420, overflowY: "auto" }}>
        <table className="financial-table">
          <thead>
            <tr>
              <th>Period End</th>
              <th>Form</th>
              <th>NII</th>
              <th>Provision</th>
              <th>NIM</th>
              <th>Deposits</th>
              <th>Core Mix</th>
              <th>Uninsured Mix</th>
              <th>CET1</th>
              <th>Total Capital</th>
              <th>Net Income</th>
            </tr>
          </thead>
          <tbody>
            {financials.map((row) => {
              const bank = row.regulated_bank ?? null;
              return (
                <tr key={`${row.period_end}-${row.filing_type}-${row.source}`}>
                  <td>{formatDate(row.period_end)}</td>
                  <td className="form-cell">{row.filing_type}</td>
                  <td>{formatCompactNumber(bank?.net_interest_income ?? null)}</td>
                  <td>{formatCompactNumber(bank?.provision_for_credit_losses ?? null)}</td>
                  <td>{formatPercent(bank?.net_interest_margin ?? null)}</td>
                  <td>{formatCompactNumber(bank?.deposits_total ?? null)}</td>
                  <td>{formatPercent(safeRatio(bank?.core_deposits ?? null, bank?.deposits_total ?? null))}</td>
                  <td>{formatPercent(safeRatio(bank?.uninsured_deposits ?? null, bank?.deposits_total ?? null))}</td>
                  <td>{formatPercent(bank?.common_equity_tier1_ratio ?? null)}</td>
                  <td>{formatPercent(bank?.total_risk_based_capital_ratio ?? null)}</td>
                  <td>{formatCompactNumber(row.net_income)}</td>
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