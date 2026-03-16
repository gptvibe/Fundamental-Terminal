"use client";

import { useMemo } from "react";

import type { FinancialPayload } from "@/lib/types";
import { formatCompactNumber, formatPercent } from "@/lib/format";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);

export function FinancialQualitySummary({ financials }: { financials: FinancialPayload[] }) {
  const summary = useMemo(() => buildSummary(financials), [financials]);

  if (!summary) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 220 }}>
        <div className="grid-empty-kicker">Quality summary</div>
        <div className="grid-empty-title">Not enough annual history yet</div>
        <div className="grid-empty-copy">This panel appears when annual filings provide at least one full period of normalized financial metrics.</div>
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <div className="metric-grid">
        <Metric label="Gross Margin" value={formatPercent(summary.grossMargin)} />
        <Metric label="Operating Margin" value={formatPercent(summary.operatingMargin)} />
        <Metric label="FCF Margin" value={formatPercent(summary.fcfMargin)} />
        <Metric label="Debt / Assets" value={formatPercent(summary.debtToAssets)} />
      </div>

      <div className="metric-grid">
        <Metric label="ROA" value={formatPercent(summary.roa)} />
        <Metric label="YoY Revenue" value={formatPercent(summary.revenueGrowth)} />
        <Metric label="YoY Net Income" value={formatPercent(summary.netIncomeGrowth)} />
        <Metric label="Shares Outstanding" value={formatCompactNumber(summary.sharesOutstanding)} />
      </div>
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

function buildSummary(financials: FinancialPayload[]) {
  const annuals = financials
    .filter((item) => ANNUAL_FORMS.has(item.filing_type))
    .sort((left, right) => Date.parse(right.period_end) - Date.parse(left.period_end));

  const latest = annuals[0] ?? null;
  const previous = annuals[1] ?? null;
  if (!latest) {
    return null;
  }

  return {
    grossMargin: safeDivide(latest.gross_profit, latest.revenue),
    operatingMargin: safeDivide(latest.operating_income, latest.revenue),
    fcfMargin: safeDivide(latest.free_cash_flow, latest.revenue),
    debtToAssets: safeDivide(latest.total_liabilities, latest.total_assets),
    roa: safeDivide(latest.net_income, latest.total_assets),
    revenueGrowth: growthRate(latest.revenue, previous?.revenue ?? null),
    netIncomeGrowth: growthRate(latest.net_income, previous?.net_income ?? null),
    sharesOutstanding: latest.shares_outstanding,
  };
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