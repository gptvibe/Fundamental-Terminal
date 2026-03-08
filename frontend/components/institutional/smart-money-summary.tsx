"use client";

import { useMemo } from "react";

import { buildSmartMoneySummary } from "@/lib/smart-money";
import type { InstitutionalHoldingPayload, RefreshState } from "@/lib/types";

interface SmartMoneySummaryProps {
  holdings: InstitutionalHoldingPayload[];
  loading?: boolean;
  error?: string | null;
  refresh?: RefreshState | null;
}

export function SmartMoneySummary({
  holdings,
  loading = false,
  error = null,
  refresh = null
}: SmartMoneySummaryProps) {
  const summary = useMemo(() => buildSmartMoneySummary(holdings), [holdings]);

  if (error) {
    return <div className="text-muted">{error}</div>;
  }

  if (loading && !summary) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 220 }}>
        <div className="grid-empty-kicker">Smart money</div>
        <div className="grid-empty-title">Reading institutional position changes</div>
        <div className="grid-empty-copy">Comparing cached 13F fund positions across reporting periods.</div>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 220 }}>
        <div className="grid-empty-kicker">Smart money</div>
        <div className="grid-empty-title">No smart-money signal available yet</div>
        <div className="grid-empty-copy">
          {refresh?.triggered
            ? "The backend is refreshing cached 13F data now. This module will populate when that run completes."
            : "No cached institutional position-change data is available for this ticker yet."}
        </div>
      </div>
    );
  }

  return (
    <div className={`smart-money-shell smart-money-${summary.sentiment}`}>
      <div className="smart-money-header">
        <span className={`smart-money-badge smart-money-badge-${summary.sentiment}`}>{labelForSentiment(summary.sentiment)}</span>
        <div className="smart-money-meta">
          <span>13F deltas</span>
          <span>{summary.fund_increasing} adding</span>
          <span>{summary.fund_decreasing} trimming</span>
        </div>
      </div>

      <div className="smart-money-metrics-grid">
        <MetricCard label="Institutional Buy" value={formatCurrencyCompact(summary.total_buy_value)} tone="bullish" />
        <MetricCard label="Institutional Sell" value={formatCurrencyCompact(summary.total_sell_value)} tone="bearish" />
        <MetricCard label="Net Institutional" value={formatSignedCurrencyCompact(summary.net_institutional_flow)} tone={toneForNet(summary.net_institutional_flow)} />
        <MetricCard label="Funds Up / Down" value={`${summary.fund_increasing} / ${summary.fund_decreasing}`} tone="neutral" />
      </div>

      <ul className="smart-money-list">
        {summary.summary_lines.map((line) => (
          <li key={line} className="smart-money-item">
            <span className="smart-money-bullet" />
            <span>{line}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function MetricCard({ label, value, tone }: { label: string; value: string; tone: "bullish" | "bearish" | "neutral" }) {
  return (
    <div className={`smart-money-metric-card smart-money-metric-card-${tone}`}>
      <div className="smart-money-metric-label">{label}</div>
      <div className="smart-money-metric-value">{value}</div>
    </div>
  );
}

function labelForSentiment(sentiment: "bullish" | "neutral" | "bearish") {
  switch (sentiment) {
    case "bullish":
      return "Bullish";
    case "bearish":
      return "Bearish";
    default:
      return "Neutral";
  }
}

function toneForNet(value: number): "bullish" | "bearish" | "neutral" {
  if (value > 0) {
    return "bullish";
  }
  if (value < 0) {
    return "bearish";
  }
  return "neutral";
}

function formatCurrencyCompact(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: Math.abs(value) >= 1_000 ? "compact" : "standard",
    maximumFractionDigits: 2
  }).format(value);
}

function formatSignedCurrencyCompact(value: number) {
  if (value > 0) {
    return `+${formatCurrencyCompact(value)}`;
  }
  if (value < 0) {
    return `-${formatCurrencyCompact(Math.abs(value))}`;
  }
  return formatCurrencyCompact(0);
}
