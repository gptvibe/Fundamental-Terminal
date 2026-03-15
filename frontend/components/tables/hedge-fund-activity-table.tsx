"use client";

import { useMemo, useState } from "react";

import { formatDate, formatPercent } from "@/lib/format";
import type { InstitutionalHoldingPayload, RefreshState } from "@/lib/types";

type SortKey = "fund_name" | "shares_held" | "change_in_shares" | "percent_change" | "portfolio_weight" | "quarter" | "filing_date";
type SortDirection = "asc" | "desc";

type ReportingLagPoint = {
  key: string;
  filingDate: string;
  lagDays: number;
};

type ReportingLagSummary = {
  points: ReportingLagPoint[];
  median: number | null;
  max: number;
};

interface HedgeFundActivityTableProps {
  ticker: string;
  holdings: InstitutionalHoldingPayload[];
  loading?: boolean;
  error?: string | null;
  refresh?: RefreshState | null;
}

export function HedgeFundActivityTable({
  ticker,
  holdings,
  loading = false,
  error = null,
  refresh = null
}: HedgeFundActivityTableProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("quarter");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  const filteredHoldings = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase();
    const nextRows = holdings.filter((holding) => holding.fund_name.toLowerCase().includes(normalizedQuery));
    return [...nextRows].sort((left, right) => compareHoldings(left, right, sortKey, sortDirection));
  }, [holdings, searchQuery, sortDirection, sortKey]);

  const increaseCount = filteredHoldings.filter((holding) => (holding.change_in_shares ?? 0) > 0).length;
  const decreaseCount = filteredHoldings.filter((holding) => (holding.change_in_shares ?? 0) < 0).length;
  const reportingLagSummary = useMemo(() => buildReportingLagSummary(holdings), [holdings]);

  function handleSortToggle(nextKey: SortKey) {
    if (sortKey === nextKey) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }

    setSortKey(nextKey);
    setSortDirection(nextKey === "fund_name" ? "asc" : "desc");
  }

  if (error) {
    return <div className="text-muted">{error}</div>;
  }

  if (loading && !holdings.length) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 220 }}>
        <div className="grid-empty-kicker">13F table</div>
        <div className="grid-empty-title">Loading ownership activity</div>
        <div className="grid-empty-copy">Loading the latest reported 13F holdings for {ticker}.</div>
      </div>
    );
  }

  if (!holdings.length) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 240 }}>
        <div className="grid-empty-kicker">13F table</div>
        <div className="grid-empty-title">No ownership activity yet</div>
        <div className="grid-empty-copy">
          {refresh?.triggered
            ? "We're updating the latest 13F filings now. This panel will fill in when the refresh finishes."
            : `No reported 13F holdings are available for ${ticker} yet.`}
        </div>
      </div>
    );
  }

  return (
    <div className="insider-transactions-shell">
      <div className="insider-toolbar">
        <div className="insider-filter-row">
          <label className="insider-filter-field">
            <span className="insider-filter-label">Search fund</span>
            <input
              className="insider-filter-input"
              type="search"
              placeholder="Renaissance, Bridgewater, Berkshire..."
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
          </label>
        </div>

        <div className="insider-toolbar-meta">
          <span>{filteredHoldings.length} rows</span>
          <span>{increaseCount} increases</span>
          <span>{decreaseCount} decreases</span>
        </div>
      </div>

      {reportingLagSummary.points.length ? (
        <div className="filing-lag-strip">
          <div className="filing-lag-header">
            <span>Reporting lag</span>
            <span>{reportingLagSummary.median != null ? `${reportingLagSummary.median}d median` : "Lag unavailable"}</span>
            <span>{reportingLagSummary.max}d max</span>
          </div>
          <div className="filing-lag-bars">
            {reportingLagSummary.points.map((point) => (
              <div
                key={point.key}
                className="filing-lag-bar"
                style={{ height: `${resolveLagHeight(point.lagDays, reportingLagSummary.max)}px` }}
                title={`Filed ${formatDate(point.filingDate)} - ${point.lagDays} day lag`}
              />
            ))}
          </div>
        </div>
      ) : null}

      <div className="insider-table-shell">
        <table className="insider-table hedge-fund-table">
          <thead>
            <tr>
              <SortableHeader label="Fund Name" sortKey="fund_name" activeKey={sortKey} direction={sortDirection} onToggle={handleSortToggle} />
              <SortableHeader label="Shares Held" sortKey="shares_held" activeKey={sortKey} direction={sortDirection} onToggle={handleSortToggle} align="right" />
              <SortableHeader label="Change in Shares" sortKey="change_in_shares" activeKey={sortKey} direction={sortDirection} onToggle={handleSortToggle} align="right" />
              <SortableHeader label="% Change" sortKey="percent_change" activeKey={sortKey} direction={sortDirection} onToggle={handleSortToggle} align="right" />
              <SortableHeader label="Portfolio Weight" sortKey="portfolio_weight" activeKey={sortKey} direction={sortDirection} onToggle={handleSortToggle} align="right" />
              <SortableHeader label="Quarter" sortKey="quarter" activeKey={sortKey} direction={sortDirection} onToggle={handleSortToggle} />
              <SortableHeader label="Filing" sortKey="filing_date" activeKey={sortKey} direction={sortDirection} onToggle={handleSortToggle} />
            </tr>
          </thead>
          <tbody>
            {filteredHoldings.map((holding, index) => {
              const changeTone = changeToneClass(holding.change_in_shares);
              const strategy = holding.fund_strategy?.trim() || null;
              return (
                <tr key={`${holding.fund_name}-${holding.reporting_date}-${index}`}>
                  <td>
                    <div className="hedge-fund-name-cell">
                      <span className="insider-name-cell">{holding.fund_name}</span>
                      {strategy ? (
                        <span className="hedge-fund-strategy-chip" tabIndex={0} title={strategy}>
                          Strategy
                          <span className="hedge-fund-strategy-tooltip">{strategy}</span>
                        </span>
                      ) : null}
                    </div>
                  </td>
                  <td className="numeric-cell">{formatInteger(holding.shares_held)}</td>
                  <td className={`numeric-cell hedge-fund-change-cell ${changeTone}`}>{formatSignedInteger(holding.change_in_shares)}</td>
                  <td className={`numeric-cell hedge-fund-change-cell ${changeTone}`}>{formatSignedPercent(holding.percent_change)}</td>
                  <td className="numeric-cell">{formatPercent(holding.portfolio_weight)}</td>
                  <td>
                    <div className="hedge-fund-quarter-cell">
                      <span>{formatQuarter(holding.reporting_date)}</span>
                      <span className="hedge-fund-quarter-date">{formatDate(holding.reporting_date)}</span>
                    </div>
                  </td>
                  <td>
                    <div className="filing-meta-cell">
                      <span className="filing-form-pill">13F</span>
                      <span className="filing-date">{holding.filing_date ? formatDate(holding.filing_date) : "--"}</span>
                      {holding.source ? (
                        <a className="filing-link" href={holding.source} target="_blank" rel="noreferrer">
                          {holding.accession_number ? holding.accession_number : "SEC Filing"}
                        </a>
                      ) : (
                        <span className="filing-link is-muted">{holding.accession_number ? holding.accession_number : "--"}</span>
                      )}
                    </div>
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

function compareHoldings(left: InstitutionalHoldingPayload, right: InstitutionalHoldingPayload, sortKey: SortKey, sortDirection: SortDirection) {
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

function sortValue(holding: InstitutionalHoldingPayload, sortKey: SortKey): number | string | null {
  switch (sortKey) {
    case "fund_name":
      return holding.fund_name.toLowerCase();
    case "shares_held":
      return holding.shares_held;
    case "change_in_shares":
      return holding.change_in_shares;
    case "percent_change":
      return holding.percent_change;
    case "portfolio_weight":
      return holding.portfolio_weight;
    case "quarter":
      return Date.parse(holding.reporting_date);
    case "filing_date":
      return holding.filing_date ? Date.parse(holding.filing_date) : null;
    default:
      return null;
  }
}

function formatInteger(value: number | null) {
  if (value === null || Number.isNaN(value)) {
    return "--";
  }
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}

function formatSignedInteger(value: number | null) {
  if (value === null || Number.isNaN(value)) {
    return "--";
  }
  const formatted = formatInteger(Math.abs(value));
  return value > 0 ? `+${formatted}` : value < 0 ? `-${formatted}` : formatted;
}

function formatSignedPercent(value: number | null) {
  if (value === null || Number.isNaN(value)) {
    return "--";
  }
  const formatted = `${Math.abs(value * 100).toFixed(2)}%`;
  return value > 0 ? `+${formatted}` : value < 0 ? `-${formatted}` : formatted;
}

function changeToneClass(value: number | null) {
  if (value === null || Number.isNaN(value) || value === 0) {
    return "hedge-fund-change-flat";
  }
  return value > 0 ? "hedge-fund-change-positive" : "hedge-fund-change-negative";
}

function formatQuarter(value: string) {
  const dateValue = new Date(value);
  const quarter = Math.floor(dateValue.getUTCMonth() / 3) + 1;
  return `Q${quarter} ${dateValue.getUTCFullYear()}`;
}

const DATE_ONLY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

function buildReportingLagSummary(holdings: InstitutionalHoldingPayload[]): ReportingLagSummary {
  const points: ReportingLagPoint[] = [];
  for (const holding of holdings) {
    if (!holding.filing_date || !holding.reporting_date) {
      continue;
    }
    const filingDate = parseLagDate(holding.filing_date);
    const reportingDate = parseLagDate(holding.reporting_date);
    if (!filingDate || !reportingDate) {
      continue;
    }
    const lagDays = Math.max(0, Math.round((filingDate.getTime() - reportingDate.getTime()) / 86400000));
    const key = holding.accession_number ? holding.accession_number : `${holding.fund_name}-${holding.reporting_date}`;
    points.push({ key, filingDate: holding.filing_date, lagDays });
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
