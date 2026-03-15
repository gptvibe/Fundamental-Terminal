"use client";

import { useMemo, useState } from "react";

import { formatDate } from "@/lib/format";
import type { InsiderTradePayload, RefreshState } from "@/lib/types";

type SortKey = "date" | "filing_date" | "name" | "role" | "action" | "shares" | "price" | "value" | "ownership_after" | "is_10b5_1";
type SortDirection = "asc" | "desc";
type NormalizedAction = "buy" | "sell" | "other";

type FilingLagPoint = {
  key: string;
  filingDate: string;
  lagDays: number;
};

type FilingLagSummary = {
  points: FilingLagPoint[];
  median: number | null;
  max: number;
};

const EMPTY_ROLE_VALUE = "__none__";

const TRANSACTION_CODE_HELP: Record<string, string> = {
  P: "Open market or private purchase.",
  S: "Open market or private sale.",
  A: "Grant, award, or other acquisition from the issuer.",
  D: "Disposition back to the issuer or other exempt disposition.",
  F: "Payment of exercise price or tax by delivering or withholding securities.",
  M: "Exercise or conversion of a derivative security.",
  C: "Conversion of a derivative security.",
  G: "Gift of securities.",
  J: "Other acquisition or disposition described in footnotes.",
  K: "Equity swap or similar derivative position.",
  L: "Small acquisition under Rule 16a-6.",
  W: "Acquisition or disposition by will or laws of descent.",
  X: "Exercise of an in-the-money derivative security.",
  Z: "Deposit into or withdrawal from a voting trust."
};

interface InsiderTransactionsTableProps {
  ticker: string;
  trades: InsiderTradePayload[];
  loading?: boolean;
  error?: string | null;
  refresh?: RefreshState | null;
}

export function InsiderTransactionsTable({
  ticker,
  trades,
  loading = false,
  error = null,
  refresh = null
}: InsiderTransactionsTableProps) {
  const [roleFilter, setRoleFilter] = useState<string>("all");
  const [actionFilter, setActionFilter] = useState<"all" | NormalizedAction>("all");
  const [sortKey, setSortKey] = useState<SortKey>("date");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  const roleOptions = useMemo(() => {
    const roles = Array.from(new Set(trades.map((trade) => trade.role ?? EMPTY_ROLE_VALUE)));
    return roles.sort((left, right) => roleLabel(left).localeCompare(roleLabel(right)));
  }, [trades]);

  const filteredTrades = useMemo(() => {
    const nextTrades = trades.filter((trade) => {
      const roleMatches = roleFilter === "all" || (trade.role ?? EMPTY_ROLE_VALUE) === roleFilter;
      const actionMatches = actionFilter === "all" || normalizeAction(trade.action) === actionFilter;
      return roleMatches && actionMatches;
    });

    return [...nextTrades].sort((left, right) => compareTrades(left, right, sortKey, sortDirection));
  }, [actionFilter, roleFilter, sortDirection, sortKey, trades]);

  const buyCount = filteredTrades.filter((trade) => normalizeAction(trade.action) === "buy").length;
  const sellCount = filteredTrades.filter((trade) => normalizeAction(trade.action) === "sell").length;
  const filingLagSummary = useMemo(() => buildFilingLagSummary(trades), [trades]);

  function handleSortToggle(nextKey: SortKey) {
    if (sortKey === nextKey) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }

    setSortKey(nextKey);
    setSortDirection(nextKey === "name" || nextKey === "role" || nextKey === "action" ? "asc" : "desc");
  }

  if (error) {
    return <div className="text-muted">{error}</div>;
  }

  if (loading && !trades.length) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 220 }}>
        <div className="grid-empty-kicker">Insider tape</div>
        <div className="grid-empty-title">Loading insider transactions</div>
        <div className="grid-empty-copy">Loading the latest Form 4 activity for {ticker}.</div>
      </div>
    );
  }

  if (!trades.length) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 240 }}>
        <div className="grid-empty-kicker">Insider tape</div>
        <div className="grid-empty-title">No insider transactions yet</div>
        <div className="grid-empty-copy">
          {refresh?.triggered
            ? "We're updating the latest Form 4 filings now. This panel will fill in when the refresh finishes."
            : `No Form 4 trades are available for ${ticker} yet.`}
        </div>
      </div>
    );
  }

  return (
    <div className="insider-transactions-shell">
      <div className="insider-toolbar">
        <div className="insider-filter-row">
          <label className="insider-filter-field">
            <span className="insider-filter-label">Role</span>
            <select className="insider-filter-select" value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}>
              <option value="all">All roles</option>
              {roleOptions.map((role) => (
                <option key={role} value={role}>
                  {roleLabel(role)}
                </option>
              ))}
            </select>
          </label>

          <label className="insider-filter-field">
            <span className="insider-filter-label">Action</span>
            <select
              className="insider-filter-select"
              value={actionFilter}
              onChange={(event) => setActionFilter(event.target.value as "all" | NormalizedAction)}
            >
              <option value="all">All actions</option>
              <option value="buy">Buy</option>
              <option value="sell">Sell</option>
              <option value="other">Other</option>
            </select>
          </label>
        </div>

        <div className="insider-toolbar-meta">
          <span>{filteredTrades.length} trades</span>
          <span>{buyCount} buys</span>
          <span>{sellCount} sells</span>
          <span>{refresh?.triggered ? "updating" : "up to date"}</span>
        </div>
      </div>

      {filingLagSummary.points.length ? (
        <div className="filing-lag-strip">
          <div className="filing-lag-header">
            <span>Filing lag</span>
            <span>{filingLagSummary.median != null ? `${filingLagSummary.median}d median` : "Lag unavailable"}</span>
            <span>{filingLagSummary.max}d max</span>
          </div>
          <div className="filing-lag-bars">
            {filingLagSummary.points.map((point) => (
              <div
                key={point.key}
                className="filing-lag-bar"
                style={{ height: `${resolveLagHeight(point.lagDays, filingLagSummary.max)}px` }}
                title={`Filed ${formatDate(point.filingDate)} - ${point.lagDays} day lag`}
              />
            ))}
          </div>
        </div>
      ) : null}

      <div className="insider-table-shell">
        <table className="insider-table">
          <thead>
            <tr>
              <SortableHeader label="Date" sortKey="date" activeKey={sortKey} direction={sortDirection} onToggle={handleSortToggle} />
              <SortableHeader label="Filing" sortKey="filing_date" activeKey={sortKey} direction={sortDirection} onToggle={handleSortToggle} />
              <SortableHeader label="Insider Name" sortKey="name" activeKey={sortKey} direction={sortDirection} onToggle={handleSortToggle} />
              <SortableHeader label="Role" sortKey="role" activeKey={sortKey} direction={sortDirection} onToggle={handleSortToggle} />
              <SortableHeader label="Action" sortKey="action" activeKey={sortKey} direction={sortDirection} onToggle={handleSortToggle} />
              <SortableHeader label="Shares" sortKey="shares" activeKey={sortKey} direction={sortDirection} onToggle={handleSortToggle} align="right" />
              <SortableHeader label="Price" sortKey="price" activeKey={sortKey} direction={sortDirection} onToggle={handleSortToggle} align="right" />
              <SortableHeader label="Value" sortKey="value" activeKey={sortKey} direction={sortDirection} onToggle={handleSortToggle} align="right" />
              <SortableHeader
                label="Ownership After"
                sortKey="ownership_after"
                activeKey={sortKey}
                direction={sortDirection}
                onToggle={handleSortToggle}
                align="right"
              />
              <SortableHeader label="10b5-1 Plan" sortKey="is_10b5_1" activeKey={sortKey} direction={sortDirection} onToggle={handleSortToggle} />
            </tr>
          </thead>
          <tbody>
            {filteredTrades.map((trade, index) => {
              const action = normalizeAction(trade.action);
              return (
                <tr key={`${trade.name}-${trade.date ?? "na"}-${trade.transaction_code ?? "none"}-${index}`}>
                  <td>{trade.date ? formatDate(trade.date) : "--"}</td>
                  <td>
                    <div className="filing-meta-cell">
                      <span className="filing-form-pill">{trade.filing_type ? trade.filing_type : "Form 4"}</span>
                      <span className="filing-date">{trade.filing_date ? formatDate(trade.filing_date) : "--"}</span>
                      {trade.source ? (
                        <a className="filing-link" href={trade.source} target="_blank" rel="noreferrer">
                          {trade.accession_number ? trade.accession_number : "SEC Filing"}
                        </a>
                      ) : (
                        <span className="filing-link is-muted">{trade.accession_number ? trade.accession_number : "--"}</span>
                      )}
                    </div>
                  </td>
                  <td className="insider-name-cell">{trade.name}</td>
                  <td>{trade.role ?? "Unspecified"}</td>
                  <td>
                    <div className="insider-action-cell">
                      <span className={`insider-action-pill insider-action-${action}`}>{actionLabel(action)}</span>
                      {trade.transaction_code ? (
                        <span className="transaction-code-chip" tabIndex={0} title={transactionCodeExplanation(trade.transaction_code)}>
                          {trade.transaction_code}
                          <span className="transaction-code-tooltip">{transactionCodeExplanation(trade.transaction_code)}</span>
                        </span>
                      ) : null}
                    </div>
                  </td>
                  <td className="numeric-cell">{formatInteger(trade.shares)}</td>
                  <td className="numeric-cell">{formatCurrency(trade.price)}</td>
                  <td className="numeric-cell">{formatCurrency(trade.value)}</td>
                  <td className="numeric-cell">{formatInteger(trade.ownership_after)}</td>
                  <td>
                    <span className={`insider-plan-pill ${trade.is_10b5_1 ? "insider-plan-pill-yes" : "insider-plan-pill-no"}`}>
                      {trade.is_10b5_1 ? "Yes" : "No"}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SortableHeader({
  label,
  sortKey,
  activeKey,
  direction,
  onToggle,
  align = "left"
}: {
  label: string;
  sortKey: SortKey;
  activeKey: SortKey;
  direction: SortDirection;
  onToggle: (sortKey: SortKey) => void;
  align?: "left" | "right";
}) {
  const isActive = activeKey === sortKey;
  const indicator = isActive ? (direction === "asc" ? "↑" : "↓") : "↕";

  return (
    <th className={align === "right" ? "align-right" : undefined}>
      <button type="button" className={`insider-sort-button ${isActive ? "insider-sort-button-active" : ""}`} onClick={() => onToggle(sortKey)}>
        <span>{label}</span>
        <span className="insider-sort-indicator">{indicator}</span>
      </button>
    </th>
  );
}

function compareTrades(left: InsiderTradePayload, right: InsiderTradePayload, sortKey: SortKey, sortDirection: SortDirection): number {
  const leftValue = sortValue(left, sortKey);
  const rightValue = sortValue(right, sortKey);
  const direction = sortDirection === "asc" ? 1 : -1;

  if (leftValue === null && rightValue === null) {
    return 0;
  }
  if (leftValue === null) {
    return 1;
  }
  if (rightValue === null) {
    return -1;
  }

  if (typeof leftValue === "number" && typeof rightValue === "number") {
    return (leftValue - rightValue) * direction;
  }

  return String(leftValue).localeCompare(String(rightValue)) * direction;
}

function sortValue(trade: InsiderTradePayload, sortKey: SortKey): number | string | null {
  switch (sortKey) {
    case "date":
      return trade.date ? Date.parse(trade.date) : null;
    case "filing_date":
      return trade.filing_date ? Date.parse(trade.filing_date) : null;
    case "name":
      return trade.name.toLowerCase();
    case "role":
      return (trade.role ?? "").toLowerCase();
    case "action":
      return normalizeAction(trade.action);
    case "shares":
      return trade.shares;
    case "price":
      return trade.price;
    case "value":
      return trade.value;
    case "ownership_after":
      return trade.ownership_after;
    case "is_10b5_1":
      return trade.is_10b5_1 ? 1 : 0;
    default:
      return null;
  }
}

function normalizeAction(action: string): NormalizedAction {
  const normalized = action.trim().toLowerCase();
  if (normalized === "buy") {
    return "buy";
  }
  if (normalized === "sell") {
    return "sell";
  }
  return "other";
}

function actionLabel(action: NormalizedAction) {
  switch (action) {
    case "buy":
      return "Buy";
    case "sell":
      return "Sell";
    default:
      return "Other";
  }
}

function roleLabel(role: string) {
  return role === EMPTY_ROLE_VALUE ? "Unspecified" : role;
}

function transactionCodeExplanation(code: string) {
  return TRANSACTION_CODE_HELP[code.toUpperCase()] ?? "SEC Form 4 transaction code; see filing footnotes for exact context.";
}

function formatInteger(value: number | null) {
  if (value === null || Number.isNaN(value)) {
    return "--";
  }

  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}

function formatCurrency(value: number | null) {
  if (value === null || Number.isNaN(value)) {
    return "--";
  }

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2
  }).format(value);
}

const DATE_ONLY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

function buildFilingLagSummary(trades: InsiderTradePayload[]): FilingLagSummary {
  const byAccession = new Map<string, { filingDate: string; transactionDate: string }>();

  for (const trade of trades) {
    if (!trade.filing_date || !trade.date) {
      continue;
    }
    const key = trade.accession_number
      ? trade.accession_number
      : trade.source
      ? trade.source
      : `${trade.name}-${trade.date}-${trade.transaction_code ? trade.transaction_code : "na"}`;
    const existing = byAccession.get(key);
    if (!existing || trade.date < existing.transactionDate) {
      byAccession.set(key, { filingDate: trade.filing_date, transactionDate: trade.date });
    }
  }

  const points: FilingLagPoint[] = [];
  for (const [key, entry] of byAccession) {
    const filingDate = parseLagDate(entry.filingDate);
    const transactionDate = parseLagDate(entry.transactionDate);
    if (!filingDate || !transactionDate) {
      continue;
    }
    const lagDays = Math.max(0, Math.round((filingDate.getTime() - transactionDate.getTime()) / 86400000));
    points.push({ key, filingDate: entry.filingDate, lagDays });
  }

  const ordered = points.sort((left, right) => Date.parse(left.filingDate) - Date.parse(right.filingDate));
  const trimmed = ordered.slice(Math.max(0, ordered.length - 12));
  const lags = trimmed.map((point) => point.lagDays).sort((a, b) => a - b);
  const median = lags.length ? lags[Math.floor((lags.length - 1) / 2)] : null;
  const max = trimmed.reduce((value, point) => Math.max(value, point.lagDays), 0);

  return { points: trimmed, median, max };
}

function parseLagDate(value: string) {
  if (!value) {
    return null;
  }
  if (DATE_ONLY_PATTERN.test(value)) {
    const [year, month, day] = value.split("-").map(Number);
    return new Date(Date.UTC(year, month - 1, day));
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed;
}

function resolveLagHeight(value: number, max: number) {
  if (!max) {
    return 8;
  }
  return Math.max(8, Math.round((value / max) * 32) + 6);
}





