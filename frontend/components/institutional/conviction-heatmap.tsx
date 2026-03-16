"use client";

import { useMemo } from "react";

import type { InstitutionalHoldingPayload } from "@/lib/types";
import { formatCompactNumber, formatDate } from "@/lib/format";

type ConvictionRow = {
  fund: string;
  reportingDate: string;
  sharesHeld: number | null;
  portfolioWeight: number | null;
  percentChange: number | null;
  score: number;
};

export function ConvictionHeatmap({ holdings }: { holdings: InstitutionalHoldingPayload[] }) {
  const rows = useMemo(() => buildConvictionRows(holdings), [holdings]);

  if (!rows.length) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 220 }}>
        <div className="grid-empty-kicker">Conviction</div>
        <div className="grid-empty-title">No conviction map yet</div>
        <div className="grid-empty-copy">This view appears when tracked 13F snapshots include position size and weight fields.</div>
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gap: 10 }}>
      {rows.map((row) => {
        const intensity = convictionIntensity(row.score);
        return (
          <div
            key={`${row.fund}-${row.reportingDate}`}
            className="filing-link-card"
            style={{
              display: "grid",
              gap: 8,
              borderColor: `rgba(0, 229, 255, ${0.16 + intensity * 0.36})`,
              background: `linear-gradient(90deg, rgba(0, 229, 255, ${0.06 + intensity * 0.22}), rgba(17, 17, 17, 0.92))`,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text)" }}>{row.fund}</div>
              <div className="text-muted">{formatDate(row.reportingDate)}</div>
            </div>

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <span className="pill">Conviction {row.score.toFixed(1)}/10</span>
              <span className="pill">Weight {formatPercent(row.portfolioWeight)}</span>
              <span className="pill">Change {formatSignedPercent(row.percentChange)}</span>
              <span className="pill">Shares {formatCompactNumber(row.sharesHeld)}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function buildConvictionRows(holdings: InstitutionalHoldingPayload[]): ConvictionRow[] {
  const latestByFund = new Map<string, InstitutionalHoldingPayload>();
  for (const row of holdings) {
    const existing = latestByFund.get(row.fund_name);
    if (!existing || row.reporting_date > existing.reporting_date) {
      latestByFund.set(row.fund_name, row);
    }
  }

  const rows: ConvictionRow[] = [...latestByFund.values()].map((row) => ({
    fund: row.fund_name,
    reportingDate: row.reporting_date,
    sharesHeld: row.shares_held,
    portfolioWeight: row.portfolio_weight,
    percentChange: row.percent_change,
    score: convictionScore(row),
  }));

  return rows.sort((left, right) => right.score - left.score).slice(0, 18);
}

function convictionScore(row: InstitutionalHoldingPayload): number {
  const weight = clamp((row.portfolio_weight ?? 0) / 8, 0, 1);
  const change = clamp((row.percent_change ?? 0) / 30, -1, 1);
  const changeContribution = change >= 0 ? change : change * 0.35;
  const score = (weight * 0.68 + (changeContribution + 1) * 0.16) * 10;
  return clamp(score, 0, 10);
}

function convictionIntensity(score: number): number {
  return clamp(score / 10, 0, 1);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function formatPercent(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "-";
  }
  return `${value.toFixed(2)}%`;
}

function formatSignedPercent(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "-";
  }
  if (value > 0) {
    return `+${value.toFixed(2)}%`;
  }
  return `${value.toFixed(2)}%`;
}