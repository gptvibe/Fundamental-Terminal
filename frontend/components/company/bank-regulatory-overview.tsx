"use client";

import { useMemo, useState } from "react";

import { HistoricalSparklineCard } from "@/components/company/historical-sparkline-card";
import { SnapshotSurfaceStatus } from "@/components/company/snapshot-surface-status";
import { MetricLabel } from "@/components/ui/metric-label";
import { difference, formatSignedCompactDelta, formatSignedPointDelta } from "@/lib/financial-chart-state";
import { formatCompactNumber, formatPercent } from "@/lib/format";
import { dedupeSnapshotSurfaceWarnings, resolveSnapshotSurfaceMode, type SnapshotSurfaceCapabilities, type SnapshotSurfaceWarning } from "@/lib/snapshot-surface";
import type { FinancialPayload } from "@/lib/types";

const CAPABILITIES: SnapshotSurfaceCapabilities = {
  supports_selected_period: true,
  supports_compare_mode: true,
  supports_trend_mode: true,
};

type TrendView = "sparklines" | "table";

interface BankRegulatoryOverviewProps {
  latestFinancial?: FinancialPayload | null;
  financials?: FinancialPayload[];
  selectedFinancial?: FinancialPayload | null;
  comparisonFinancial?: FinancialPayload | null;
}

export function BankRegulatoryOverview({
  latestFinancial = null,
  financials = [],
  selectedFinancial = null,
  comparisonFinancial = null,
}: BankRegulatoryOverviewProps) {
  const [trendView, setTrendView] = useState<TrendView>("sparklines");
  const bankFinancials = financials.filter((statement) => statement.regulated_bank);
  const orderedFinancials = useMemo(
    () => [...bankFinancials].sort((left, right) => Date.parse(right.period_end) - Date.parse(left.period_end)),
    [bankFinancials]
  );
  const focusFinancial = selectedFinancial?.regulated_bank ? selectedFinancial : latestFinancial ?? bankFinancials[0] ?? null;
  const comparison = comparisonFinancial?.regulated_bank ? comparisonFinancial : null;
  const bank = focusFinancial?.regulated_bank ?? null;
  const trendRows = useMemo(
    () => orderedFinancials.slice(0, 6).map((statement) => ({
      key: `${statement.period_end}|${statement.filing_type}`,
      label: formatBankLabel(statement),
      netInterestMargin: statement.regulated_bank?.net_interest_margin ?? null,
      provisionBurden: safeRatio(statement.regulated_bank?.provision_for_credit_losses ?? null, statement.regulated_bank?.net_interest_income ?? null),
      cet1: statement.regulated_bank?.common_equity_tier1_ratio ?? null,
      coreDepositMix: safeRatio(statement.regulated_bank?.core_deposits ?? null, statement.regulated_bank?.deposits_total ?? null),
      deposits: statement.regulated_bank?.deposits_total ?? null,
      tangibleCommonEquity: statement.regulated_bank?.tangible_common_equity ?? null,
    })),
    [orderedFinancials]
  );

  if (!focusFinancial || !bank) {
    return <div className="text-muted">No regulated bank statement snapshot is available yet.</div>;
  }

  const warnings = buildWarnings(bankFinancials, comparisonFinancial, comparison);
  const mode = resolveSnapshotSurfaceMode({
    comparisonAvailable: comparison !== null,
    trendAvailable: trendRows.length > 1,
    capabilities: CAPABILITIES,
  });
  const focusKey = `${focusFinancial.period_end}|${focusFinancial.filing_type}`;
  const comparisonKey = comparison ? `${comparison.period_end}|${comparison.filing_type}` : null;

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <SnapshotSurfaceStatus capabilities={CAPABILITIES} mode={mode} warnings={warnings} />

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <span className="pill tone-cyan">Focus {formatBankLabel(focusFinancial)}</span>
        {comparison ? <span className="pill tone-gold">Compare {formatBankLabel(comparison)}</span> : null}
      </div>

      <div className="metric-grid">
        <MetricCard label="Net Interest Margin" value={formatPercent(bank.net_interest_margin)} />
        <MetricCard label="Provision Burden" value={formatPercent(safeRatio(bank.provision_for_credit_losses, bank.net_interest_income))} />
        <MetricCard label="Asset Quality" value={formatPercent(bank.nonperforming_assets_ratio)} />
        <MetricCard label="CET1" value={formatPercent(bank.common_equity_tier1_ratio)} />
        <MetricCard label="Tier 1" value={formatPercent(bank.tier1_risk_weighted_ratio)} />
        <MetricCard label="Total Capital" value={formatPercent(bank.total_risk_based_capital_ratio)} />
        <MetricCard label="Core Deposit Mix" value={formatPercent(safeRatio(bank.core_deposits, bank.deposits_total))} />
        <MetricCard label="Uninsured Deposits" value={formatPercent(safeRatio(bank.uninsured_deposits, bank.deposits_total))} />
        <MetricCard label="Tangible Common Equity" value={formatCompactNumber(bank.tangible_common_equity)} />
        <MetricCard label="Deposits" value={formatCompactNumber(bank.deposits_total)} />
      </div>

      {comparison?.regulated_bank ? (
        <div className="metric-grid">
          <MetricCard label="NIM Delta" value={formatSignedPointDelta(scaleToPoints(difference(bank.net_interest_margin, comparison.regulated_bank.net_interest_margin)))} />
          <MetricCard label="Provision Delta" value={formatSignedPointDelta(scaleToPoints(difference(safeRatio(bank.provision_for_credit_losses, bank.net_interest_income), safeRatio(comparison.regulated_bank.provision_for_credit_losses, comparison.regulated_bank.net_interest_income))))} />
          <MetricCard label="CET1 Delta" value={formatSignedPointDelta(scaleToPoints(difference(bank.common_equity_tier1_ratio, comparison.regulated_bank.common_equity_tier1_ratio)))} />
          <MetricCard label="Core Deposit Mix Delta" value={formatSignedPointDelta(scaleToPoints(difference(safeRatio(bank.core_deposits, bank.deposits_total), safeRatio(comparison.regulated_bank.core_deposits, comparison.regulated_bank.deposits_total))))} />
          <MetricCard label="Deposits Delta" value={formatSignedCompactDelta(difference(bank.deposits_total, comparison.regulated_bank.deposits_total))} />
          <MetricCard label="TCE Delta" value={formatSignedCompactDelta(difference(bank.tangible_common_equity, comparison.regulated_bank.tangible_common_equity))} />
        </div>
      ) : null}

      {trendRows.length ? (
        <>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <div className="cash-waterfall-toggle-group" role="tablist" aria-label="Regulated bank history view">
              <button type="button" className={`chart-chip${trendView === "sparklines" ? " chart-chip-active" : ""}`} onClick={() => setTrendView("sparklines")}>
                Sparklines
              </button>
              <button type="button" className={`chart-chip${trendView === "table" ? " chart-chip-active" : ""}`} onClick={() => setTrendView("table")}>
                Trend Table
              </button>
            </div>
            <span className="pill">Bank periods {trendRows.length}</span>
          </div>

          {trendView === "sparklines" ? (
            <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
              <HistoricalSparklineCard label="Net Interest Margin" value={formatPercent(bank.net_interest_margin)} delta={formatSignedPointDelta(scaleToPoints(difference(bank.net_interest_margin, comparison?.regulated_bank?.net_interest_margin ?? null)))} data={buildBankTrendSparklineData(trendRows, "netInterestMargin", focusKey, comparisonKey)} />
              <HistoricalSparklineCard label="Provision Burden" value={formatPercent(safeRatio(bank.provision_for_credit_losses, bank.net_interest_income))} delta={formatSignedPointDelta(scaleToPoints(difference(safeRatio(bank.provision_for_credit_losses, bank.net_interest_income), safeRatio(comparison?.regulated_bank?.provision_for_credit_losses ?? null, comparison?.regulated_bank?.net_interest_income ?? null))))} data={buildBankTrendSparklineData(trendRows, "provisionBurden", focusKey, comparisonKey)} color="var(--chart-series-2)" />
              <HistoricalSparklineCard label="CET1" value={formatPercent(bank.common_equity_tier1_ratio)} delta={formatSignedPointDelta(scaleToPoints(difference(bank.common_equity_tier1_ratio, comparison?.regulated_bank?.common_equity_tier1_ratio ?? null)))} data={buildBankTrendSparklineData(trendRows, "cet1", focusKey, comparisonKey)} color="var(--chart-series-3)" />
              <HistoricalSparklineCard label="Core Deposit Mix" value={formatPercent(safeRatio(bank.core_deposits, bank.deposits_total))} delta={formatSignedPointDelta(scaleToPoints(difference(safeRatio(bank.core_deposits, bank.deposits_total), safeRatio(comparison?.regulated_bank?.core_deposits ?? null, comparison?.regulated_bank?.deposits_total ?? null))))} data={buildBankTrendSparklineData(trendRows, "coreDepositMix", focusKey, comparisonKey)} color="var(--chart-series-4)" />
              <HistoricalSparklineCard label="Deposits" value={formatCompactNumber(bank.deposits_total)} delta={formatSignedCompactDelta(difference(bank.deposits_total, comparison?.regulated_bank?.deposits_total ?? null))} data={buildBankTrendSparklineData(trendRows, "deposits", focusKey, comparisonKey)} color="var(--chart-series-5)" />
              <HistoricalSparklineCard label="Tangible Common Equity" value={formatCompactNumber(bank.tangible_common_equity)} delta={formatSignedCompactDelta(difference(bank.tangible_common_equity, comparison?.regulated_bank?.tangible_common_equity ?? null))} data={buildBankTrendSparklineData(trendRows, "tangibleCommonEquity", focusKey, comparisonKey)} color="var(--chart-series-6)" />
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="company-data-table" style={{ minWidth: 760 }}>
                <thead>
                  <tr>
                    <th align="left">Period</th>
                    <th align="right">NIM</th>
                    <th align="right">Provision Burden</th>
                    <th align="right">CET1</th>
                    <th align="right">Core Deposit Mix</th>
                    <th align="right">Deposits</th>
                  </tr>
                </thead>
                <tbody>
                  {orderedFinancials.slice(0, 6).map((statement) => {
                    const rowBank = statement.regulated_bank;
                    const isFocus = focusFinancial.period_end === statement.period_end && focusFinancial.filing_type === statement.filing_type;
                    const isComparison = comparison && comparison.period_end === statement.period_end && comparison.filing_type === statement.filing_type;
                    return (
                      <tr
                        key={`${statement.period_end}|${statement.filing_type}`}
                        style={isFocus ? { background: "color-mix(in srgb, var(--accent) 8%, transparent)" } : isComparison ? { background: "color-mix(in srgb, var(--warning) 8%, transparent)" } : undefined}
                      >
                        <td>{formatBankLabel(statement)}</td>
                        <td style={{ textAlign: "right" }}>{formatPercent(rowBank?.net_interest_margin ?? null)}</td>
                        <td style={{ textAlign: "right" }}>{formatPercent(safeRatio(rowBank?.provision_for_credit_losses ?? null, rowBank?.net_interest_income ?? null))}</td>
                        <td style={{ textAlign: "right" }}>{formatPercent(rowBank?.common_equity_tier1_ratio ?? null)}</td>
                        <td style={{ textAlign: "right" }}>{formatPercent(safeRatio(rowBank?.core_deposits ?? null, rowBank?.deposits_total ?? null))}</td>
                        <td style={{ textAlign: "right" }}>{formatCompactNumber(rowBank?.deposits_total ?? null)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : null}

      <div className="text-muted" style={{ display: "grid", gap: 6 }}>
        <div>
          Reporting basis: {bank.reporting_basis.replaceAll("_", " ")} ({bank.source_id.replaceAll("_", " ")})
        </div>
        {bank.confidence_flags.length ? <div>Confidence flags: {bank.confidence_flags.join(", ")}</div> : null}
      </div>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-card">
      <div className="metric-label">
        <MetricLabel label={label} />
      </div>
      <div className="metric-value">{value}</div>
    </div>
  );
}

function safeRatio(numerator: number | null, denominator: number | null): number | null {
  if (numerator == null || denominator == null || denominator === 0) {
    return null;
  }
  return numerator / denominator;
}

function buildWarnings(
  bankFinancials: FinancialPayload[],
  requestedComparison: FinancialPayload | null,
  comparison: FinancialPayload | null
): SnapshotSurfaceWarning[] {
  const warnings: SnapshotSurfaceWarning[] = [];
  if (requestedComparison && !comparison) {
    warnings.push({
      code: "bank_comparison_missing",
      label: "Comparison period unavailable",
      detail: "The selected comparison period does not expose regulated-bank ratios in the current workspace window.",
      tone: "warning",
    });
  }
  if (bankFinancials.length < 2) {
    warnings.push({
      code: "bank_trend_sparse",
      label: "Sparse regulated-bank history",
      detail: "Only one regulated-bank filing is visible, so trend mode falls back to the selected period snapshot.",
      tone: "info",
    });
  }
  return dedupeSnapshotSurfaceWarnings(warnings);
}

function scaleToPoints(value: number | null): number | null {
  return value == null ? null : value * 100;
}

function formatBankLabel(statement: Pick<FinancialPayload, "period_end" | "filing_type">): string {
  return `${statement.filing_type} ${statement.period_end.slice(0, 10)}`;
}

function buildBankTrendSparklineData(
  rows: Array<{
    key: string;
    label: string;
    netInterestMargin: number | null;
    provisionBurden: number | null;
    cet1: number | null;
    coreDepositMix: number | null;
    deposits: number | null;
    tangibleCommonEquity: number | null;
  }>,
  metric: "netInterestMargin" | "provisionBurden" | "cet1" | "coreDepositMix" | "deposits" | "tangibleCommonEquity",
  focusKey: string,
  comparisonKey: string | null
) {
  return [...rows].reverse().map((row) => ({
    label: row.label,
    value: row[metric],
    isSelected: row.key === focusKey,
    isComparison: comparisonKey ? row.key === comparisonKey : false,
  }));
}