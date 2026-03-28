"use client";

import { formatCompactNumber, formatPercent } from "@/lib/format";
import type { FinancialPayload } from "@/lib/types";

export function BankRegulatoryOverview({ latestFinancial }: { latestFinancial: FinancialPayload | null }) {
  const bank = latestFinancial?.regulated_bank ?? null;
  if (!latestFinancial || !bank) {
    return <div className="text-muted">No regulated bank statement snapshot is available yet.</div>;
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
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
      <div className="metric-label">{label}</div>
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