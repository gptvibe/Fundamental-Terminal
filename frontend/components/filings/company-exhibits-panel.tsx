"use client";

import { useMemo, useState } from "react";
import { clsx } from "clsx";

import { formatDate } from "@/lib/format";
import type { CompanyExhibitsResponse, ExhibitPayload } from "@/lib/types";

const KNOWN_EXHIBIT_TYPES = [
  { value: "", label: "All types" },
  { value: "EX-99.1", label: "EX-99.1 — Earnings release" },
  { value: "EX-99", label: "EX-99 — Press release" },
  { value: "EX-10", label: "EX-10 — Material contract" },
  { value: "EX-21", label: "EX-21 — Subsidiaries" },
  { value: "EX-31", label: "EX-31 — SOX 302 Certification" },
  { value: "EX-32", label: "EX-32 — SOX 906 Certification" },
  { value: "EX-23", label: "EX-23 — Auditor consent" },
];

const KNOWN_FILING_TYPES = [
  { value: "", label: "All forms" },
  { value: "10-K", label: "10-K — Annual report" },
  { value: "10-Q", label: "10-Q — Quarterly report" },
  { value: "8-K", label: "8-K — Current report" },
  { value: "DEF 14A", label: "DEF 14A — Proxy statement" },
  { value: "S-1", label: "S-1 — Registration statement" },
];

interface CompanyExhibitsPanelProps {
  payload?: CompanyExhibitsResponse | null;
  loading?: boolean;
  error?: string | null;
  onFilterChange?: (filters: { exhibitType: string; filingType: string }) => void;
  exhibitTypeFilter?: string;
  filingTypeFilter?: string;
}

export function CompanyExhibitsPanel({
  payload,
  loading = false,
  error = null,
  onFilterChange,
  exhibitTypeFilter = "",
  filingTypeFilter = "",
}: CompanyExhibitsPanelProps) {
  const exhibits = useMemo(() => payload?.exhibits ?? [], [payload]);

  if (error && !exhibits.length) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 240 }}>
        <div className="grid-empty-kicker">SEC Exhibits</div>
        <div className="grid-empty-title">Unable to load exhibits</div>
        <div className="grid-empty-copy">{error}</div>
      </div>
    );
  }

  if (loading && !exhibits.length) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 240 }}>
        <div className="grid-empty-kicker">SEC Exhibits</div>
        <div className="grid-empty-title">Loading exhibit index</div>
        <div className="grid-empty-copy">Fetching exhibit lists from SEC EDGAR filing indexes.</div>
      </div>
    );
  }

  if (!loading && !exhibits.length) {
    return (
      <div>
        <ExhibitFilters
          exhibitTypeFilter={exhibitTypeFilter}
          filingTypeFilter={filingTypeFilter}
          onFilterChange={onFilterChange}
        />
        <div className="grid-empty-state" style={{ minHeight: 200 }}>
          <div className="grid-empty-kicker">SEC Exhibits</div>
          <div className="grid-empty-title">No exhibits found</div>
          <div className="grid-empty-copy">
            Try a different exhibit type or filing form filter, or clear the filters to see all exhibits.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="exhibits-panel-shell">
      <div className="exhibits-provenance-note">
        Source: SEC EDGAR — official filing documents only.{" "}
        {payload?.provenance?.length ? payload.provenance[0] : null}
      </div>

      <ExhibitFilters
        exhibitTypeFilter={exhibitTypeFilter}
        filingTypeFilter={filingTypeFilter}
        onFilterChange={onFilterChange}
      />

      <div className="exhibits-count-note">
        Showing {exhibits.length} exhibit{exhibits.length !== 1 ? "s" : ""}
        {payload?.total != null && payload.total > exhibits.length
          ? ` (${payload.total} total)`
          : null}
      </div>

      <div className="exhibits-list">
        {exhibits.map((exhibit, index) => (
          <ExhibitRow key={`${exhibit.accession_number}-${exhibit.exhibit_number}-${index}`} exhibit={exhibit} />
        ))}
      </div>
    </div>
  );
}

function ExhibitFilters({
  exhibitTypeFilter,
  filingTypeFilter,
  onFilterChange,
}: {
  exhibitTypeFilter: string;
  filingTypeFilter: string;
  onFilterChange?: (filters: { exhibitType: string; filingType: string }) => void;
}) {
  return (
    <div className="exhibits-filter-row">
      <label className="exhibits-filter-label">
        Exhibit type
        <select
          className="exhibits-filter-select"
          value={exhibitTypeFilter}
          onChange={(e) => onFilterChange?.({ exhibitType: e.target.value, filingType: filingTypeFilter })}
          aria-label="Filter by exhibit type"
        >
          {KNOWN_EXHIBIT_TYPES.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>

      <label className="exhibits-filter-label">
        Filing form
        <select
          className="exhibits-filter-select"
          value={filingTypeFilter}
          onChange={(e) => onFilterChange?.({ exhibitType: exhibitTypeFilter, filingType: e.target.value })}
          aria-label="Filter by filing form"
        >
          {KNOWN_FILING_TYPES.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>

      {(exhibitTypeFilter || filingTypeFilter) && (
        <button
          type="button"
          className="ticker-button"
          onClick={() => onFilterChange?.({ exhibitType: "", filingType: "" })}
        >
          Clear filters
        </button>
      )}
    </div>
  );
}

function ExhibitRow({ exhibit }: { exhibit: ExhibitPayload }) {
  const filingDate = exhibit.filing_date ? formatDate(exhibit.filing_date) : null;

  return (
    <div className="exhibit-row">
      <div className="exhibit-row-topline">
        <span className="exhibit-type-badge">{exhibit.exhibit_number}</span>
        {exhibit.tag_label ? (
          <span className="exhibit-tag-label">{exhibit.tag_label}</span>
        ) : null}
        <span className="exhibit-filing-type">{exhibit.filing_type}</span>
        {filingDate ? <span className="exhibit-date">{filingDate}</span> : null}
      </div>

      {exhibit.description ? (
        <div className="exhibit-description">{exhibit.description}</div>
      ) : null}

      <div className="exhibit-meta">
        <span className="exhibit-document">{exhibit.document}</span>
        <span className="exhibit-accession">Accn {exhibit.accession_number}</span>
      </div>

      <div className="exhibit-actions">
        <a
          href={exhibit.source_url}
          target="_blank"
          rel="noreferrer"
          className="ticker-button filing-action-link"
          aria-label={`Open ${exhibit.exhibit_number} on SEC EDGAR`}
        >
          Open on SEC ↗
        </a>
        <a
          href={exhibit.filing_index_url}
          target="_blank"
          rel="noreferrer"
          className="ticker-button filing-action-link"
          aria-label="View filing index on SEC EDGAR"
        >
          Filing index ↗
        </a>
      </div>
    </div>
  );
}
