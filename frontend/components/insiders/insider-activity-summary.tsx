"use client";

import { MetricLabel } from "@/components/ui/metric-label";
import type { InsiderActivitySummaryPayload, RefreshState } from "@/lib/types";

interface InsiderActivitySummaryProps {
  summary: InsiderActivitySummaryPayload | null;
  loading?: boolean;
  error?: string | null;
  refresh?: RefreshState | null;
}

export function InsiderActivitySummary({ summary, loading = false, error = null, refresh = null }: InsiderActivitySummaryProps) {
  if (error) {
    return <div className="text-muted">{error}</div>;
  }

  if (loading && !summary) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 220 }}>
        <div className="grid-empty-kicker">Insider signals</div>
        <div className="grid-empty-title">Calculating insider activity summary</div>
        <div className="grid-empty-copy">Reading cached Form 4 activity and building rule-based insights.</div>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 220 }}>
        <div className="grid-empty-kicker">Insider signals</div>
        <div className="grid-empty-title">No insider summary available yet</div>
        <div className="grid-empty-copy">
          {refresh?.triggered
            ? "The backend is refreshing cached insider activity now. This card will populate when the run completes."
            : "No cached insider activity summary is available for this company yet."}
        </div>
      </div>
    );
  }

  return (
    <div className={`insider-activity-shell insider-activity-${summary.sentiment}`}>
      <div className="insider-activity-header">
        <span className={`insider-activity-badge insider-activity-badge-${summary.sentiment}`}>{labelForSentiment(summary.sentiment)}</span>
        <div className="insider-activity-meta">
          <span>Open-market signal</span>
          <span>Excludes grants/exercises</span>
          <span>{summary.metrics.unique_insiders_buying} buyers</span>
          <span>{summary.metrics.unique_insiders_selling} sellers</span>
        </div>
      </div>

      <div className="insider-activity-metrics-grid">
        <MetricCard label="Open-Market Buy" value={formatCurrencyCompact(summary.metrics.total_buy_value)} tone="bullish" />
        <MetricCard label="Open-Market Sell" value={formatCurrencyCompact(summary.metrics.total_sell_value)} tone="bearish" />
        <MetricCard label="Net Signal" value={formatSignedCurrencyCompact(summary.metrics.net_value)} tone={toneForNet(summary.metrics.net_value)} />
        <MetricCard
          label="Buyer / Seller Count"
          value={`${summary.metrics.unique_insiders_buying} / ${summary.metrics.unique_insiders_selling}`}
          tone="neutral"
        />
      </div>

      <ul className="insider-activity-list">
        {summary.summary_lines.slice(0, 4).map((line) => (
          <li key={line} className="insider-activity-item">
            <span className="insider-activity-bullet" />
            <span>{line}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function MetricCard({ label, value, tone }: { label: string; value: string; tone: "bullish" | "bearish" | "neutral" }) {
  return (
    <div className={`insider-activity-metric-card insider-activity-metric-card-${tone}`}>
      <div className="insider-activity-metric-label">
        <MetricLabel label={label} />
      </div>
      <div className="insider-activity-metric-value">{value}</div>
    </div>
  );
}

function labelForSentiment(sentiment: InsiderActivitySummaryPayload["sentiment"]) {
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
