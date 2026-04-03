"use client";

import { Children, useEffect, useMemo, useState, type ReactNode } from "react";

import { MetricLabel } from "@/components/ui/metric-label";
import { SourceFreshnessSummary } from "@/components/ui/source-freshness-summary";
import { getCompanyChangesSinceLastFiling } from "@/lib/api";
import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import type {
  CompanyChangesSinceLastFilingResponse,
  FilingComparisonAmendedValuePayload,
  FilingComparisonMetricDeltaPayload,
  FilingComparisonRiskIndicatorPayload,
  FilingComparisonSegmentShiftPayload,
} from "@/lib/types";

interface ChangesSinceLastFilingCardProps {
  ticker: string;
  reloadKey?: string | number;
}

export function ChangesSinceLastFilingCard({ ticker, reloadKey }: ChangesSinceLastFilingCardProps) {
  const [payload, setPayload] = useState<CompanyChangesSinceLastFilingResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
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
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [reloadKey, ticker]);

  const topMetricDeltas = useMemo(() => (payload?.metric_deltas ?? []).slice(0, 4), [payload?.metric_deltas]);
  const topRiskIndicators = useMemo(() => (payload?.new_risk_indicators ?? []).slice(0, 4), [payload?.new_risk_indicators]);
  const topSegmentShifts = useMemo(() => (payload?.segment_shifts ?? []).slice(0, 3), [payload?.segment_shifts]);
  const capitalAndShareChanges = useMemo(
    () => [...(payload?.share_count_changes ?? []).slice(0, 2), ...(payload?.capital_structure_changes ?? []).slice(0, 3)],
    [payload?.capital_structure_changes, payload?.share_count_changes]
  );
  const amendedPriorValues = useMemo(() => (payload?.amended_prior_values ?? []).slice(0, 3), [payload?.amended_prior_values]);

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
        <MetricCard label="Metric Deltas" value={String(summary.metric_delta_count)} />
        <MetricCard label="New Risk Indicators" value={String(summary.new_risk_indicator_count)} />
        <MetricCard label="Segment Shifts" value={String(summary.segment_shift_count)} />
        <MetricCard label="Amended Prior Values" value={String(summary.amended_prior_value_count)} />
      </div>

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