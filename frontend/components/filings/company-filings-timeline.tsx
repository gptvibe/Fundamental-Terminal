"use client";

import { useEffect, useMemo, useState } from "react";
import { clsx } from "clsx";

import { formatDate } from "@/lib/format";
import type { FilingPayload } from "@/lib/types";

type YearFilter = "current" | "earlier";

interface CompanyFilingsTimelineProps {
  filings: FilingPayload[];
  loading?: boolean;
  error?: string | null;
  timelineSource?: "sec_submissions" | "cached_financials" | null;
  selectedSourceUrl?: string | null;
  onSelectFiling: (filing: FilingPayload) => void;
}

export function CompanyFilingsTimeline({
  filings,
  loading = false,
  error = null,
  timelineSource = null,
  selectedSourceUrl = null,
  onSelectFiling
}: CompanyFilingsTimelineProps) {
  const currentYear = useMemo(() => new Date().getFullYear(), []);
  const [yearFilter, setYearFilter] = useState<YearFilter>("current");

  const filingsByYear = useMemo(() => {
    const current: FilingPayload[] = [];
    const earlier: FilingPayload[] = [];

    filings.forEach((filing) => {
      const year = resolveFilingYear(filing);
      if (year !== null && year < currentYear) {
        earlier.push(filing);
      } else {
        current.push(filing);
      }
    });

    return { current, earlier };
  }, [currentYear, filings]);

  const filteredFilings = useMemo(
    () => (yearFilter === "current" ? filingsByYear.current : filingsByYear.earlier),
    [filingsByYear, yearFilter]
  );

  useEffect(() => {
    if (!filteredFilings.length) {
      return;
    }

    if (selectedSourceUrl && filteredFilings.some((filing) => filing.source_url === selectedSourceUrl)) {
      return;
    }

    onSelectFiling(filteredFilings[0]);
  }, [filteredFilings, onSelectFiling, selectedSourceUrl]);

  if (error) {
    return <div className="text-muted">{error}</div>;
  }

  if (loading && !filings.length) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 240 }}>
        <div className="grid-empty-kicker">SEC timeline</div>
        <div className="grid-empty-title">Loading filing timeline</div>
        <div className="grid-empty-copy">Pulling the latest SEC submissions for this company.</div>
      </div>
    );
  }

  if (!filings.length) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 240 }}>
        <div className="grid-empty-kicker">SEC timeline</div>
        <div className="grid-empty-title">No filings to show yet</div>
        <div className="grid-empty-copy">Recent SEC submissions will appear here once they are available.</div>
      </div>
    );
  }

  const bannerCopy = resolveTimelineBanner(timelineSource);

  return (
    <div className="filing-timeline-shell">
      {bannerCopy ? (
        <div className={clsx("filing-timeline-banner", bannerCopy.tone === "warning" && "is-warning")}>{bannerCopy.text}</div>
      ) : null}

      <div className="filing-filter-row" role="tablist" aria-label="Filing year filter">
        <button
          type="button"
          className={clsx("ticker-button", "filing-filter-button", yearFilter === "current" && "is-active")}
          onClick={() => setYearFilter("current")}
          aria-pressed={yearFilter === "current"}
        >
          Current Year
        </button>
        <button
          type="button"
          className={clsx("ticker-button", "filing-filter-button", yearFilter === "earlier" && "is-active")}
          onClick={() => setYearFilter("earlier")}
          aria-pressed={yearFilter === "earlier"}
        >
          Earlier
        </button>
      </div>

      {filteredFilings.length === 0 ? (
        <div className="grid-empty-state" style={{ minHeight: 220 }}>
          <div className="grid-empty-kicker">Filing timeline</div>
          <div className="grid-empty-title">
            {yearFilter === "current" ? `No filings yet in ${currentYear}` : "No earlier filings"}
          </div>
          <div className="grid-empty-copy">
            {yearFilter === "current"
              ? "Switch to Earlier to view prior-year filings while new reports are pending."
              : "Only current-year filings are available right now."}
          </div>
        </div>
      ) : (
        <div className="filing-timeline-list">
          {filteredFilings.map((filing) => {
            const filingDate = resolveFilingDate(filing);
            const isSelected = selectedSourceUrl === filing.source_url;
            const title = resolveFilingTitle(filing);
            const summary = resolveFilingSummary(filing, title);

            return (
              <div key={filing.source_url} className="filing-timeline-item">
                <div className="filing-timeline-rail" />
                <div className={clsx("filing-timeline-card", isSelected && "is-selected")}>
                  <div className="filing-timeline-topline">
                    <span className="filing-timeline-date">{filingDate ? formatDate(filingDate) : "Pending"}</span>
                    <span className={clsx("filing-form-badge", formBadgeClass(filing.form))}>{filing.form}</span>
                  </div>

                  <div className="filing-timeline-title">{title}</div>

                  <div className="filing-timeline-meta">
                    {filing.report_date ? <span>Report {formatDate(filing.report_date)}</span> : null}
                    {filing.accession_number ? <span>Accn {filing.accession_number}</span> : null}
                    {filing.primary_document ? <span>{filing.primary_document}</span> : null}
                  </div>

                  <div className="filing-timeline-summary">{summary}</div>

                  <div className="filing-timeline-actions">
                    <button
                      type="button"
                      className={clsx("ticker-button", "filing-action-link", isSelected && "is-active")}
                      onClick={() => onSelectFiling(filing)}
                    >
                      {isSelected ? "Viewing in workspace" : "Open in viewer"}
                    </button>
                    <a href={filing.source_url} target="_blank" rel="noreferrer" className="ticker-button filing-action-link">
                      Open on SEC
                    </a>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function resolveTimelineBanner(source: CompanyFilingsTimelineProps["timelineSource"]) {
  if (source === "cached_financials") {
    return {
      tone: "warning" as const,
      text: "Showing cached annual and quarterly filings while SEC submissions refresh."
    };
  }
  if (source === "sec_submissions") {
    return {
      tone: "info" as const,
      text: "Timeline reflects SEC submissions pulled directly from EDGAR."
    };
  }
  return null;
}

function resolveFilingDate(filing: FilingPayload) {
  return filing.filing_date ?? filing.report_date ?? null;
}

function resolveFilingYear(filing: FilingPayload) {
  const date = resolveFilingDate(filing);
  if (!date) {
    return null;
  }
  const parsed = Date.parse(date);
  if (Number.isNaN(parsed)) {
    return null;
  }
  return new Date(parsed).getFullYear();
}

function resolveFilingTitle(filing: FilingPayload): string {
  const description = filing.primary_doc_description?.trim();
  if (description && !isRedundantDescription(description, filing.form)) {
    return description;
  }

  switch (filing.form) {
    case "10-K":
    case "20-F":
    case "40-F":
      return "Annual report";
    case "10-Q":
      return "Quarterly report";
    case "8-K":
      return "Current report";
    case "6-K":
      return "Foreign issuer report";
    default:
      return filing.form;
  }
}

function resolveFilingSummary(filing: FilingPayload, title: string) {
  const items = filing.items?.trim();
  if (items) {
    return `Items: ${items}`;
  }

  const description = filing.primary_doc_description?.trim();
  if (description && description !== title && !isRedundantDescription(description, filing.form)) {
    return description;
  }

  return "No itemized disclosures reported for this filing.";
}

function isRedundantDescription(description: string, form: string) {
  const normalized = description.trim().toUpperCase();
  const normalizedForm = form.trim().toUpperCase();
  return normalized === normalizedForm || normalized === `FORM ${normalizedForm}`;
}

function formBadgeClass(form: string) {
  const normalized = form.trim().toLowerCase();
  const withoutAmendment = normalized.endsWith("/a") ? normalized.slice(0, -2) : normalized;
  const slug = withoutAmendment.replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
  return slug ? `filing-form-${slug}` : undefined;
}
