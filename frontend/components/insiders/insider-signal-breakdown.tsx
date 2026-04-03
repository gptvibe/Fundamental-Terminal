"use client";

import { useMemo } from "react";

import { MetricLabel } from "@/components/ui/metric-label";
import type { InsiderTradePayload } from "@/lib/types";
import { formatDate } from "@/lib/format";

export function InsiderSignalBreakdown({ trades }: { trades: InsiderTradePayload[] }) {
  const summary = useMemo(() => buildSignalBreakdown(trades), [trades]);

  if (!trades.length) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 220 }}>
        <div className="grid-empty-kicker">Signal quality</div>
        <div className="grid-empty-title">No insider activity to classify yet</div>
        <div className="grid-empty-copy">This panel separates open-market signal from lower-signal grants, exercises, and plan-driven transactions.</div>
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div className="metric-grid">
        <Metric label="Open-Market Trades" value={String(summary.signalTrades)} />
        <Metric label="Other Form 4 Entries" value={String(summary.otherTrades)} />
        <Metric label="10b5-1 Trades" value={String(summary.planTrades)} />
        <Metric label="Executive Signal Trades" value={String(summary.executiveSignalTrades)} />
      </div>

      <div className="metric-grid">
        <Metric label="Signal Buy Value" value={formatMoney(summary.signalBuyValue)} />
        <Metric label="Signal Sell Value" value={formatMoney(summary.signalSellValue)} />
        <Metric label="Largest Signal Trade" value={formatMoney(summary.largestSignalTradeValue)} />
        <Metric label="Latest Signal Date" value={summary.latestSignalDate ? formatDate(summary.latestSignalDate) : "--"} />
      </div>

      <ul className="insider-activity-list">
        {summary.summaryLines.map((line) => (
          <li key={line} className="insider-activity-item">
            <span className="insider-activity-bullet" />
            <span>{line}</span>
          </li>
        ))}
      </ul>
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

function buildSignalBreakdown(trades: InsiderTradePayload[]) {
  const signalTrades = trades.filter((trade) => isSignalBuy(trade) || isSignalSell(trade));
  const planTrades = trades.filter((trade) => trade.is_10b5_1);
  const executiveSignalTrades = signalTrades.filter((trade) => isExecutiveRole(trade.role));
  const signalBuyValue = round(signalTrades.filter(isSignalBuy).reduce((sum, trade) => sum + resolveTransactionValue(trade), 0));
  const signalSellValue = round(signalTrades.filter(isSignalSell).reduce((sum, trade) => sum + resolveTransactionValue(trade), 0));
  const largestSignalTradeValue = round(Math.max(0, ...signalTrades.map(resolveTransactionValue)));
  const latestSignalDate = signalTrades.reduce<string | null>((latest, trade) => {
    if (!trade.date) {
      return latest;
    }
    return !latest || trade.date > latest ? trade.date : latest;
  }, null);
  const otherTrades = trades.length - signalTrades.length;

  const summaryLines = [
    `${signalTrades.length.toLocaleString()} entries look like open-market signal trades, while ${otherTrades.toLocaleString()} look like grants, exercises, or other non-signal entries.`,
    `${planTrades.length.toLocaleString()} trades were tagged as 10b5-1 plan activity, which generally carries less discretionary signal.`,
    `${executiveSignalTrades.length.toLocaleString()} signal trades came from CEO, CFO, or other executive roles.`,
    signalBuyValue >= signalSellValue
      ? `Open-market buy value currently matches or exceeds sell value by ${formatMoney(signalBuyValue - signalSellValue)}.`
      : `Open-market sell value currently exceeds buy value by ${formatMoney(signalSellValue - signalBuyValue)}.`
  ];

  return {
    signalTrades: signalTrades.length,
    otherTrades,
    planTrades: planTrades.length,
    executiveSignalTrades: executiveSignalTrades.length,
    signalBuyValue,
    signalSellValue,
    largestSignalTradeValue,
    latestSignalDate,
    summaryLines,
  };
}

function isSignalBuy(trade: InsiderTradePayload) {
  const code = (trade.transaction_code ?? "").trim().toUpperCase();
  if (code) {
    return code === "P";
  }
  return trade.action.trim().toLowerCase() === "buy";
}

function isSignalSell(trade: InsiderTradePayload) {
  const code = (trade.transaction_code ?? "").trim().toUpperCase();
  if (code) {
    return code === "S";
  }
  return trade.action.trim().toLowerCase() === "sell";
}

function isExecutiveRole(role: string | null) {
  const normalized = (role ?? "").toUpperCase();
  return normalized.includes("CEO") || normalized.includes("CFO") || normalized.includes("CHIEF") || normalized.includes("OFFICER");
}

function resolveTransactionValue(trade: InsiderTradePayload) {
  if (typeof trade.value === "number" && Number.isFinite(trade.value)) {
    return Math.abs(trade.value);
  }
  if (typeof trade.shares === "number" && Number.isFinite(trade.shares) && typeof trade.price === "number" && Number.isFinite(trade.price)) {
    return Math.abs(trade.shares * trade.price);
  }
  return 0;
}

function formatMoney(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: Math.abs(value) >= 1_000 ? "compact" : "standard",
    maximumFractionDigits: 2,
  }).format(value);
}

function round(value: number) {
  return Math.round(value * 100) / 100;
}