"use client";

import { useMemo } from "react";

import { MetricLabel } from "@/components/ui/metric-label";
import type { InstitutionalHoldingPayload } from "@/lib/types";
import { formatDate } from "@/lib/format";

export function NewVsExitedPositions({ holdings }: { holdings: InstitutionalHoldingPayload[] }) {
  const summary = useMemo(() => buildPositionSummary(holdings), [holdings]);

  if (!summary) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 220 }}>
        <div className="grid-empty-kicker">Position changes</div>
        <div className="grid-empty-title">Not enough quarterly history yet</div>
        <div className="grid-empty-copy">This panel compares the latest reporting quarter with the previous one to show new and exited tracked positions.</div>
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div className="metric-grid">
        <Metric label="Latest Quarter" value={formatDate(summary.latestQuarter)} />
        <Metric label="Previous Quarter" value={formatDate(summary.previousQuarter)} />
        <Metric label="New Positions" value={String(summary.newPositions)} />
        <Metric label="Exited Positions" value={String(summary.exitedPositions)} />
      </div>

      <div className="metric-grid">
        <Metric label="Funds Increasing" value={String(summary.increasingFunds)} />
        <Metric label="Funds Decreasing" value={String(summary.decreasingFunds)} />
        <Metric label="Net Share Flow" value={formatShares(summary.netShareFlow)} />
        <Metric label="Tracked Funds" value={String(summary.latestFunds)} />
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-card">
      <div className="metric-label">
        <MetricLabel label={label} />
      </div>
      <div className="metric-value">{value}</div>
    </div>
  );
}

function buildPositionSummary(holdings: InstitutionalHoldingPayload[]) {
  const reportingDates = [...new Set(holdings.map((holding) => holding.reporting_date))].sort((left, right) => Date.parse(right) - Date.parse(left));
  const latestQuarter = reportingDates[0];
  const previousQuarter = reportingDates[1];
  if (!latestQuarter || !previousQuarter) {
    return null;
  }

  const latestRows = holdings.filter((holding) => holding.reporting_date === latestQuarter);
  const previousRows = holdings.filter((holding) => holding.reporting_date === previousQuarter);
  const latestMap = new Map(latestRows.map((holding) => [holding.fund_name, holding]));
  const previousMap = new Map(previousRows.map((holding) => [holding.fund_name, holding]));

  let newPositions = 0;
  let exitedPositions = 0;
  let increasingFunds = 0;
  let decreasingFunds = 0;
  let netShareFlow = 0;

  for (const holding of latestRows) {
    const previous = previousMap.get(holding.fund_name);
    const latestShares = holding.shares_held ?? 0;
    const previousShares = previous?.shares_held ?? 0;
    if (latestShares > 0 && previousShares <= 0) {
      newPositions += 1;
    }
    if (latestShares > previousShares) {
      increasingFunds += 1;
    }
    if (latestShares < previousShares) {
      decreasingFunds += 1;
    }
    netShareFlow += latestShares - previousShares;
  }

  for (const holding of previousRows) {
    const latest = latestMap.get(holding.fund_name);
    const latestShares = latest?.shares_held ?? 0;
    const previousShares = holding.shares_held ?? 0;
    if (previousShares > 0 && latestShares <= 0) {
      exitedPositions += 1;
    }
  }

  return {
    latestQuarter,
    previousQuarter,
    latestFunds: latestRows.length,
    newPositions,
    exitedPositions,
    increasingFunds,
    decreasingFunds,
    netShareFlow,
  };
}

function formatShares(value: number) {
  const absolute = Math.abs(value);
  const formatted = new Intl.NumberFormat("en-US", {
    notation: absolute >= 1_000 ? "compact" : "standard",
    maximumFractionDigits: 2,
  }).format(absolute);
  if (value > 0) {
    return `+${formatted}`;
  }
  if (value < 0) {
    return `-${formatted}`;
  }
  return formatted;
}