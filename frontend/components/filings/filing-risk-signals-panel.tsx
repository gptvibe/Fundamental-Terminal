"use client";

import { useMemo } from "react";

import { formatDate } from "@/lib/format";
import type { CompanyFilingRiskSignalsResponse, FilingRiskSignalPayload, RefreshState } from "@/lib/types";

interface FilingRiskSignalsPanelProps {
  payload?: CompanyFilingRiskSignalsResponse | null;
  loading?: boolean;
  error?: string | null;
  maxItems?: number;
}

const SEVERITY_ORDER: Record<string, number> = {
  high: 0,
  medium: 1,
  low: 2,
};

export function FilingRiskSignalsPanel({ payload, loading = false, error = null, maxItems = 6 }: FilingRiskSignalsPanelProps) {
  const signals = useMemo(() => payload?.signals ?? [], [payload?.signals]);
  const refresh = payload?.refresh ?? null;
  const orderedSignals = useMemo(
    () => [...signals].sort((left, right) => compareSignals(left, right)).slice(0, maxItems),
    [maxItems, signals]
  );
  const remainingCount = Math.max(0, signals.length - orderedSignals.length);

  if (error && !signals.length) {
    return <div className="text-muted">{error}</div>;
  }

  if (loading && !signals.length) {
    return <div className="text-muted">Reading cached filing signals...</div>;
  }

  if (!signals.length) {
    return (
      <div className="risk-panel-shell">
        <div className="risk-feed-headline">
          <div className="risk-feed-title risk-feed-title-safe">No recent filing text alerts</div>
          <div className="risk-feed-subcopy">This panel fills from cached 10-K, 10-Q, and 8-K text after the next background refresh.</div>
        </div>
        {refresh?.job_id ? <div className="sparkline-note">Refresh job {refresh.job_id} is populating filing text signals.</div> : null}
      </div>
    );
  }

  return (
    <div className="risk-panel-shell">
      <div className="risk-panel-meta">
        <span className="pill">
          High severity: <span className={(payload?.summary.high_severity_count ?? 0) > 0 ? "risk-pill-danger" : "risk-pill-safe"}>{payload?.summary.high_severity_count ?? 0}</span>
        </span>
        <span className="pill">Recent filing signals: {payload?.summary.total_signals ?? signals.length}</span>
      </div>

      <div className="risk-feed-headline">
        <div className={`risk-feed-title ${(payload?.summary.high_severity_count ?? 0) > 0 ? "risk-feed-title-danger" : "risk-feed-title-safe"}`}>
          {(payload?.summary.high_severity_count ?? 0) > 0 ? "Recent high-signal filing alerts" : "Recent filing language worth watching"}
        </div>
        <div className="risk-feed-subcopy">
          Signals come from already-cached SEC filing text. Stronger signals stay pinned first so the latest investor-relevant language is visible.
        </div>
      </div>

      <div className="risk-card-stack">
        {orderedSignals.map((signal) => (
          <article key={`${signal.accession_number}-${signal.signal_category}`} className={`risk-card risk-card-${signal.severity === "high" ? "high" : "medium"}`}>
            <div className="risk-card-topline">
              <span className={`risk-card-badge risk-card-badge-${signal.severity === "high" ? "high" : "medium"}`}>{signal.severity === "high" ? "High Priority" : "Watch"}</span>
              <div className="risk-card-metric">
                {signal.form_type}
                {signal.filed_date ? ` · ${formatDate(signal.filed_date)}` : ""}
              </div>
            </div>
            <div className="risk-card-header">
              <div>
                <div className="risk-card-title">{labelForSignal(signal.signal_category)}</div>
                <div className="risk-card-explanation">Matched phrase: {signal.matched_phrase}</div>
              </div>
            </div>
            <div className="sparkline-note">{signal.context_snippet}</div>
          </article>
        ))}
      </div>

      <div className="sparkline-note">
        Latest filing with signal: {payload?.summary.latest_filed_date ? formatDate(payload.summary.latest_filed_date) : "Unavailable"}
        {remainingCount > 0 ? ` · ${remainingCount} more signal${remainingCount === 1 ? "" : "s"} on the filings page` : ""}
      </div>
      {renderRefreshNote(refresh)}
    </div>
  );
}

function compareSignals(left: FilingRiskSignalPayload, right: FilingRiskSignalPayload): number {
  const severityDelta = (SEVERITY_ORDER[left.severity] ?? 9) - (SEVERITY_ORDER[right.severity] ?? 9);
  if (severityDelta !== 0) {
    return severityDelta;
  }
  const leftDate = left.filed_date ?? "";
  const rightDate = right.filed_date ?? "";
  if (leftDate !== rightDate) {
    return leftDate < rightDate ? 1 : -1;
  }
  return left.signal_category.localeCompare(right.signal_category);
}

function labelForSignal(category: string): string {
  switch (category) {
    case "material_weakness":
      return "Material weakness";
    case "going_concern":
      return "Going concern";
    case "customer_concentration":
      return "Customer concentration";
    case "supplier_concentration":
      return "Supplier concentration";
    case "covenant_risk":
      return "Debt covenant pressure";
    case "impairment":
      return "Impairment";
    case "restructuring":
      return "Restructuring";
    case "cybersecurity_incident":
      return "Cybersecurity incident";
    case "restatement":
      return "Restatement";
    case "late_filing":
      return "Late filing";
    default:
      return category.replace(/_/g, " ");
  }
}

function renderRefreshNote(refresh: RefreshState | null) {
  if (!refresh?.job_id) {
    return null;
  }
  return <div className="sparkline-note">Background refresh {refresh.job_id} is checking for newer filing text.</div>;
}