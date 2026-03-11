"use client";

import { useEffect, useMemo, useState } from "react";

import { PanelEmptyState } from "@/components/company/panel-empty-state";
import { formatDate } from "@/lib/format";
import type { FilingPayload } from "@/lib/types";

interface FilingDocumentViewerProps {
  ticker: string;
  filing: FilingPayload | null;
}

export function FilingDocumentViewer({ ticker, filing }: FilingDocumentViewerProps) {
  const [frameLoaded, setFrameLoaded] = useState(false);

  const iframeSrc = useMemo(() => {
    if (!filing) {
      return null;
    }
    return `/backend/api/companies/${encodeURIComponent(ticker)}/filings/view?source_url=${encodeURIComponent(filing.source_url)}`;
  }, [filing, ticker]);

  useEffect(() => {
    setFrameLoaded(false);
  }, [iframeSrc]);

  if (!filing || !iframeSrc) {
    return <PanelEmptyState message="Choose a filing from the timeline to open it inside the workspace." />;
  }

  const displayTitle = resolveFilingTitle(filing);
  const displayDate = filing.filing_date ?? filing.report_date;

  return (
    <div className="filing-viewer-shell">
      <div className="filing-viewer-header">
        <div className="filing-viewer-copy">
          <div className="filing-viewer-title-row">
            <span className="filing-viewer-form">{filing.form}</span>
            <span className="filing-viewer-title">{displayTitle}</span>
          </div>
          <div className="filing-viewer-meta">
            {displayDate ? <span>{formatDate(displayDate)}</span> : null}
            {filing.accession_number ? <span>Accn {filing.accession_number}</span> : null}
            {filing.primary_document ? <span>{filing.primary_document}</span> : null}
          </div>
        </div>
        <div className="filing-viewer-actions">
          <a href={filing.source_url} target="_blank" rel="noreferrer" className="ticker-button filing-action-link">
            Open on SEC
          </a>
        </div>
      </div>

      <div className="sparkline-note">Embedded filings open in a sandboxed viewer. External links inside the document open in a new tab.</div>

      <div className="filing-viewer-frame-shell">
        {!frameLoaded ? <div className="filing-viewer-loading">Loading filing document...</div> : null}
        <iframe
          key={iframeSrc}
          src={iframeSrc}
          title={`${filing.form} filing viewer`}
          className="filing-viewer-frame"
          loading="lazy"
          sandbox="allow-forms allow-popups allow-downloads"
          referrerPolicy="no-referrer"
          onLoad={() => setFrameLoaded(true)}
        />
      </div>
    </div>
  );
}

function resolveFilingTitle(filing: FilingPayload): string {
  const description = filing.primary_doc_description?.trim();
  if (description && description.toUpperCase() !== filing.form && description.toUpperCase() !== `FORM ${filing.form}`) {
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
