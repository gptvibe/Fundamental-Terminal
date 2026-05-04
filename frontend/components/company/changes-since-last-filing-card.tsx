"use client";

import { Children, useEffect, useMemo, useState, type ReactNode } from "react";

import { MetricLabel } from "@/components/ui/metric-label";
import { SourceFreshnessSummary } from "@/components/ui/source-freshness-summary";
import { getCompanyChangesSinceLastFiling } from "@/lib/api";
import { formatCompactNumber, formatDate, formatPercent, titleCase } from "@/lib/format";
import type {
  CompanyChangesSinceLastFilingResponse,
  FilingComparisonAmendedValuePayload,
  FilingComparisonMetricDeltaPayload,
  FilingComparisonRiskIndicatorPayload,
  FilingComparisonSegmentShiftPayload,
  FilingCommentLetterItemPayload,
  FilingHighSignalChangePayload,
} from "@/lib/types";

interface ChangesSinceLastFilingCardProps {
  ticker: string;
  reloadKey?: string | number;
  initialPayload?: CompanyChangesSinceLastFilingResponse | null;
  detailMode?: "brief" | "full";
  deferFetch?: boolean;
}

export function ChangesSinceLastFilingCard({
  ticker,
  reloadKey,
  initialPayload = null,
  detailMode = "brief",
  deferFetch = false,
}: ChangesSinceLastFilingCardProps) {
  const [payload, setPayload] = useState<CompanyChangesSinceLastFilingResponse | null>(initialPayload);
  const [loading, setLoading] = useState(initialPayload === null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!initialPayload) {
      return;
    }
    setPayload(initialPayload);
    setLoading(false);
    setError(null);
  }, [initialPayload]);

  useEffect(() => {
    if (initialPayload !== null || deferFetch) {
      return;
    }

    let cancelled = false;

    async function load() {
      try {
        if (initialPayload === null) {
          setLoading(true);
        }
        setError(null);
        const next = await getCompanyChangesSinceLastFiling(ticker);
        if (!cancelled) {
          setPayload(next);
        }
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError instanceof Error ? nextError.message : "Unable to load filing changes");
        }
      } finally {
        if (!cancelled && initialPayload === null) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [deferFetch, initialPayload, reloadKey, ticker]);

  const topMetricDeltas = useMemo(() => (payload?.metric_deltas ?? []).slice(0, 4), [payload?.metric_deltas]);
  const topRiskIndicators = useMemo(() => (payload?.new_risk_indicators ?? []).slice(0, 4), [payload?.new_risk_indicators]);
  const topSegmentShifts = useMemo(() => (payload?.segment_shifts ?? []).slice(0, 3), [payload?.segment_shifts]);
  const capitalAndShareChanges = useMemo(
    () => [...(payload?.share_count_changes ?? []).slice(0, 2), ...(payload?.capital_structure_changes ?? []).slice(0, 3)],
    [payload?.capital_structure_changes, payload?.share_count_changes]
  );
  const amendedPriorValues = useMemo(() => (payload?.amended_prior_values ?? []).slice(0, 3), [payload?.amended_prior_values]);
  const highSignalChanges = useMemo(
    () => (payload?.high_signal_changes ?? []).slice(0, detailMode === "brief" ? 4 : 8),
    [detailMode, payload?.high_signal_changes]
  );
  const recentCommentLetters = useMemo(
    () => (payload?.comment_letter_history.recent_letters ?? []).slice(0, detailMode === "brief" ? 2 : 5),
    [detailMode, payload?.comment_letter_history.recent_letters]
  );

  if (loading) {
    return <div className="text-muted">Loading latest-versus-prior filing comparison...</div>;
  }
  if (error) {
    return <div className="text-muted">{error}</div>;
  }
  if (!payload || !payload.current_filing) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 220 }}>
        <div className="grid-empty-kicker">Filing comparison</div>
        <div className="grid-empty-title">No comparable filing snapshot yet</div>
        <div className="grid-empty-copy">This card appears after the latest canonical SEC filing and a prior comparable filing are both cached.</div>
      </div>
    );
  }

  const summary = payload.summary;

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <span className="pill">{payload.current_filing.filing_type}</span>
        <span className="pill">Latest {formatDate(payload.current_filing.period_end)}</span>
        {payload.previous_filing ? <span className="pill">Prior {formatDate(payload.previous_filing.period_end)}</span> : null}
        {payload.current_filing.accession_number ? <span className="pill">Accession {payload.current_filing.accession_number}</span> : null}
      </div>

      <SourceFreshnessSummary
        provenance={payload.provenance}
        asOf={payload.as_of}
        lastRefreshedAt={payload.last_refreshed_at}
        sourceMix={payload.source_mix}
        confidenceFlags={payload.confidence_flags}
      />

      <div className="metric-grid">
        <MetricCard label="High-Signal Changes" value={String(summary.high_signal_change_count)} />
        <MetricCard label="Comment Letters" value={String(summary.comment_letter_count)} />
        <MetricCard label="Metric Deltas" value={String(summary.metric_delta_count)} />
        <MetricCard label="New Risk Indicators" value={String(summary.new_risk_indicator_count)} />
      </div>

      <Section title="High-Signal Filing Intelligence" emptyMessage="No high-signal filing changes were detected between the latest and prior comparable filings.">
        {highSignalChanges.map((item) => (
          <HighSignalChangeRow key={item.change_key} item={item} />
        ))}
      </Section>

      <Section title="Comment-Letter History" emptyMessage="No SEC comment-letter history is cached for this company yet.">
        {recentCommentLetters.map((item) => (
          <CommentLetterRow key={`${item.accession_number ?? item.sec_url}-${item.filing_date ?? "pending"}`} item={item} />
        ))}
      </Section>

      {detailMode === "full" ? (
        <>
      <Section title="Headline Deltas" emptyMessage="No primary metric deltas detected between the latest and prior comparable filing.">
        {topMetricDeltas.map((item) => (
          <MetricDeltaRow key={item.metric_key} item={item} />
        ))}
      </Section>

      <Section title="New Risk Indicators" emptyMessage="No newly added filing-derived risk indicators were triggered.">
        {topRiskIndicators.map((item) => (
          <RiskIndicatorRow key={item.indicator_key} item={item} />
        ))}
      </Section>

      <Section title="Segment Shifts" emptyMessage="No material segment mix changes were detected.">
        {topSegmentShifts.map((item) => (
          <SegmentShiftRow key={item.segment_id} item={item} />
        ))}
      </Section>

      <Section title="Capital And Share Count" emptyMessage="No capital-structure or share-count changes were detected.">
        {capitalAndShareChanges.map((item) => (
          <MetricDeltaRow key={`${item.metric_key}-${item.label}`} item={item} />
        ))}
      </Section>

      <Section title="Amended Prior Values" emptyMessage="No amended values were detected for the prior comparable filing.">
        {amendedPriorValues.map((item) => (
          <AmendedValueRow key={`${item.metric_key}-${item.accession_number ?? item.source}`} item={item} />
        ))}
      </Section>
        </>
      ) : null}
    </div>
  );
}

function Section({ title, emptyMessage, children }: { title: string; emptyMessage: string; children: ReactNode }) {
  const rows = Children.toArray(children);
  return (
    <div style={{ display: "grid", gap: 10 }}>
      <div style={{ fontWeight: 600, color: "var(--text)" }}>{title}</div>
      {rows.length ? rows : <div className="text-muted">{emptyMessage}</div>}
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-card">
      <div className="metric-label">
        <MetricLabel label={label} />
      </div>
      <div className="metric-value">{value}</div>
    </div>
  );
}

function MetricDeltaRow({ item }: { item: FilingComparisonMetricDeltaPayload }) {
  return (
    <div className="filing-link-card" style={{ display: "grid", gap: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <strong>{item.label}</strong>
        <span className="pill">{item.direction.replaceAll("_", " ")}</span>
      </div>
      <div className="text-muted" style={{ fontSize: 13 }}>
        Current {formatDeltaValue(item.current_value, item.unit)} · Prior {formatDeltaValue(item.previous_value, item.unit)}
      </div>
      <div style={{ fontSize: 14, color: "var(--text)" }}>
        Change {formatDeltaValue(item.delta, item.unit)}
        {item.relative_change != null ? ` (${formatPercent(item.relative_change)})` : ""}
      </div>
    </div>
  );
}

function RiskIndicatorRow({ item }: { item: FilingComparisonRiskIndicatorPayload }) {
  return (
    <div className="filing-link-card" style={{ display: "grid", gap: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <strong>{item.label}</strong>
        <span className="pill">{item.severity}</span>
      </div>
      <div className="text-muted" style={{ fontSize: 13 }}>{item.description}</div>
      <div style={{ fontSize: 13, color: "var(--text)" }}>
        Current {formatRiskValue(item.current_value)}
        {item.previous_value != null ? ` · Prior ${formatRiskValue(item.previous_value)}` : ""}
      </div>
    </div>
  );
}

function SegmentShiftRow({ item }: { item: FilingComparisonSegmentShiftPayload }) {
  return (
    <div className="filing-link-card" style={{ display: "grid", gap: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <strong>{item.segment_name}</strong>
        <span className="pill">{item.kind}</span>
      </div>
      <div className="text-muted" style={{ fontSize: 13 }}>
        Revenue {formatCompactNumber(item.previous_revenue)} to {formatCompactNumber(item.current_revenue)}
      </div>
      <div style={{ fontSize: 13, color: "var(--text)" }}>
        Mix shift {item.share_delta == null ? "?" : formatPercent(item.share_delta)}
        {item.current_share_of_revenue != null ? ` · Now ${formatPercent(item.current_share_of_revenue)}` : ""}
      </div>
    </div>
  );
}

function AmendedValueRow({ item }: { item: FilingComparisonAmendedValuePayload }) {
  return (
    <a href={item.source} target="_blank" rel="noreferrer" className="filing-link-card" style={{ display: "grid", gap: 8, textDecoration: "none" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <strong>{item.label}</strong>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <span className="pill">{item.form ?? item.detection_kind}</span>
          <span className="pill">{item.confidence_severity}</span>
        </div>
      </div>
      <div className="text-muted" style={{ fontSize: 13 }}>
        Prior {formatCompactNumber(item.previous_value)} · Amended {formatCompactNumber(item.amended_value)}
      </div>
      <div style={{ fontSize: 13, color: "var(--text)" }}>
        {item.amended_at ? `Amended ${formatDate(item.amended_at)} · ` : ""}
        Change {formatCompactNumber(item.delta)}
        {item.relative_change != null ? ` (${formatPercent(item.relative_change)})` : ""}
      </div>
    </a>
  );
}

function HighSignalChangeRow({ item }: { item: FilingHighSignalChangePayload }) {
  return (
    <div className="filing-link-card" style={{ display: "grid", gap: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <strong>{item.title}</strong>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <span className="pill">{item.category.replaceAll("_", " ")}</span>
          <span className="pill">{item.importance}</span>
        </div>
      </div>
      <div style={{ fontSize: 14, color: "var(--text)" }}>{item.summary}</div>
      <div className="text-muted" style={{ fontSize: 13 }}>{item.why_it_matters}</div>
      {item.signal_tags.length ? (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {item.signal_tags.map((tag) => (
            <span key={`${item.change_key}-${tag}`} className="pill">{tag}</span>
          ))}
        </div>
      ) : null}
      {item.evidence.length ? (
        <div style={{ display: "grid", gap: 8 }}>
          {item.evidence.slice(0, 2).map((evidence) => (
            <a
              key={`${item.change_key}-${evidence.label}-${evidence.source}`}
              href={evidence.source}
              target="_blank"
              rel="noreferrer"
              className="text-muted"
              style={{ fontSize: 13, lineHeight: 1.6, textDecoration: "none" }}
            >
              <strong style={{ color: "var(--text)" }}>{evidence.label}:</strong> {evidence.excerpt}
            </a>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function CommentLetterRow({ item }: { item: FilingCommentLetterItemPayload }) {
  return (
    <a href={item.document_url ?? item.sec_url} target="_blank" rel="noreferrer" className="filing-link-card" style={{ display: "grid", gap: 8, textDecoration: "none" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <strong>{item.description}</strong>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {item.is_new_since_current_filing ? <span className="pill">new</span> : null}
          {item.correspondent_role ? <span className="pill">{formatCorrespondentRole(item.correspondent_role)}</span> : null}
          {item.document_kind ? <span className="pill">{titleCase(item.document_kind)}</span> : null}
          {item.document_format ? <span className="pill">{item.document_format.toUpperCase()}</span> : null}
          <span className="pill">{item.filing_date ? formatDate(item.filing_date) : "Pending"}</span>
        </div>
      </div>
      <div className="text-muted" style={{ fontSize: 13 }}>
        {item.accession_number ?? "CORRESP"}
        {item.thread_key ? ` · ${formatThreadKey(item.thread_key)}` : ""}
      </div>
      {item.topics?.length ? (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {item.topics.slice(0, 4).map((topic) => (
            <span key={`${item.accession_number ?? item.sec_url}-${topic}`} className="pill">{titleCase(topic)}</span>
          ))}
        </div>
      ) : null}
      {item.document_text_excerpt ? <div className="text-muted" style={{ fontSize: 13 }}>{item.document_text_excerpt}</div> : null}
    </a>
  );
}

function formatCorrespondentRole(value: string): string {
  switch (value) {
    case "sec_staff":
      return "SEC Staff";
    case "issuer":
      return "Issuer";
    default:
      return titleCase(value);
  }
}

function formatThreadKey(value: string): string {
  if (value.startsWith("review-date:")) {
    return `Thread ${formatDate(value.slice("review-date:".length))}`;
  }
  if (value.startsWith("review-sequence:")) {
    return `Review ${value.slice("review-sequence:".length)}`;
  }
  if (value.startsWith("accession-date:")) {
    const [, dateValue] = value.split(":", 3);
    return `Thread ${formatDate(dateValue)}`;
  }
  return value;
}

function formatDeltaValue(value: number | null, unit: FilingComparisonMetricDeltaPayload["unit"]): string {
  if (value == null) {
    return "?";
  }
  if (unit === "ratio" || unit === "usd_per_share") {
    return value.toFixed(2);
  }
  return formatCompactNumber(value);
}

function formatRiskValue(value: number | null): string {
  if (value == null) {
    return "?";
  }
  if (Math.abs(value) <= 2) {
    return value.toFixed(2);
  }
  return formatCompactNumber(value);
}
