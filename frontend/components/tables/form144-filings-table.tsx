"use client";

import { useState } from "react";

import { formatDate } from "@/lib/format";
import type { Form144FilingPayload, RefreshState } from "@/lib/types";

type SortKey = "planned_sale_date" | "filer_name" | "shares_to_be_sold" | "aggregate_market_value" | "shares_owned_after_sale";
type SortDirection = "asc" | "desc";

interface Form144FilingsTableProps {
  ticker: string;
  filings: Form144FilingPayload[];
  loading?: boolean;
  error?: string | null;
  refresh?: RefreshState | null;
}

export function Form144FilingsTable({
  ticker,
  filings,
  loading = false,
  error = null,
  refresh = null
}: Form144FilingsTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("planned_sale_date");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  const sorted = [...filings].sort((a, b) => compare(a, b, sortKey, sortDirection));

  function handleSortToggle(nextKey: SortKey) {
    if (sortKey === nextKey) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(nextKey);
    setSortDirection(nextKey === "filer_name" ? "asc" : "desc");
  }

  if (error) {
    return <div className="text-muted">{error}</div>;
  }

  if (loading && !filings.length) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 220 }}>
        <div className="grid-empty-kicker">Form 144</div>
        <div className="grid-empty-title">Loading planned sales</div>
        <div className="grid-empty-copy">Loading the latest Form 144 planned sale filings for {ticker}.</div>
      </div>
    );
  }

  if (!filings.length) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 240 }}>
        <div className="grid-empty-kicker">Form 144</div>
        <div className="grid-empty-title">No Form 144 filings yet</div>
        <div className="grid-empty-copy">
          {refresh?.triggered
            ? "We're updating the latest Form 144 filings now. This panel will fill in when the refresh finishes."
            : `No Form 144 planned-sale filings are available for ${ticker} yet.`}
        </div>
      </div>
    );
  }

  return (
    <div className="insider-transactions-shell">
      <div className="insider-toolbar">
        <div className="insider-toolbar-meta">
          <span>{sorted.length} filings</span>
          <span>{refresh?.triggered ? "updating" : "up to date"}</span>
        </div>
      </div>

      <div className="insider-table-shell">
        <table className="insider-table">
          <thead>
            <tr>
              <SortableHeader label="Planned Sale Date" sortKey="planned_sale_date" activeKey={sortKey} direction={sortDirection} onToggle={handleSortToggle} />
              <th>Filing Date</th>
              <SortableHeader label="Filer" sortKey="filer_name" activeKey={sortKey} direction={sortDirection} onToggle={handleSortToggle} />
              <th>Relationship</th>
              <th>Security</th>
              <SortableHeader label="Shares to Sell" sortKey="shares_to_be_sold" activeKey={sortKey} direction={sortDirection} onToggle={handleSortToggle} align="right" />
              <SortableHeader label="Market Value" sortKey="aggregate_market_value" activeKey={sortKey} direction={sortDirection} onToggle={handleSortToggle} align="right" />
              <SortableHeader label="Shares After" sortKey="shares_owned_after_sale" activeKey={sortKey} direction={sortDirection} onToggle={handleSortToggle} align="right" />
              <th>Broker</th>
              <th>Filing</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((filing, index) => (
              <tr key={`${filing.accession_number ?? index}-${index}`}>
                <td>{filing.planned_sale_date ? formatDate(filing.planned_sale_date) : "--"}</td>
                <td>{filing.filing_date ? formatDate(filing.filing_date) : "--"}</td>
                <td className="insider-name-cell">{filing.filer_name ?? "--"}</td>
                <td>{filing.relationship_to_issuer ?? "--"}</td>
                <td>{filing.security_title ?? "--"}</td>
                <td className="numeric-cell">{formatInteger(filing.shares_to_be_sold)}</td>
                <td className="numeric-cell">{formatCurrency(filing.aggregate_market_value)}</td>
                <td className="numeric-cell">{formatInteger(filing.shares_owned_after_sale)}</td>
                <td>{filing.broker_name ?? "--"}</td>
                <td>
                  <div className="filing-meta-cell">
                    <span className="filing-form-pill">144</span>
                    {filing.source_url ? (
                      <a className="filing-link" href={filing.source_url} target="_blank" rel="noreferrer">
                        {filing.accession_number ?? "SEC Filing"}
                      </a>
                    ) : (
                      <span className="filing-link is-muted">{filing.accession_number ?? "--"}</span>
                    )}
                  </div>
                </td>
              </tr>
            ))}
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

function compare(a: Form144FilingPayload, b: Form144FilingPayload, key: SortKey, dir: SortDirection): number {
  const aVal = sortValue(a, key);
  const bVal = sortValue(b, key);
  const d = dir === "asc" ? 1 : -1;
  if (aVal === null && bVal === null) return 0;
  if (aVal === null) return 1;
  if (bVal === null) return -1;
  if (typeof aVal === "number" && typeof bVal === "number") return (aVal - bVal) * d;
  return String(aVal).localeCompare(String(bVal)) * d;
}

function sortValue(filing: Form144FilingPayload, key: SortKey): number | string | null {
  switch (key) {
    case "planned_sale_date":
      return filing.planned_sale_date ? Date.parse(filing.planned_sale_date) : null;
    case "filer_name":
      return (filing.filer_name ?? "").toLowerCase();
    case "shares_to_be_sold":
      return filing.shares_to_be_sold;
    case "aggregate_market_value":
      return filing.aggregate_market_value;
    case "shares_owned_after_sale":
      return filing.shares_owned_after_sale;
    default:
      return null;
  }
}

function formatInteger(value: number | null) {
  if (value === null || Number.isNaN(value)) return "--";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}

function formatCurrency(value: number | null) {
  if (value === null || Number.isNaN(value)) return "--";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
}
