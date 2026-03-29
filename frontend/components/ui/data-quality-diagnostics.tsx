import { formatCompactNumber, formatDate, formatPercent, titleCase } from "@/lib/format";
import type { DataQualityDiagnosticsPayload, FinancialFactReferencePayload, FinancialReconciliationPayload } from "@/lib/types";

interface DataQualityDiagnosticsProps {
  diagnostics: DataQualityDiagnosticsPayload | null | undefined;
  reconciliation?: FinancialReconciliationPayload | null;
  emptyMessage?: string;
}

export function DataQualityDiagnostics({
  diagnostics,
  reconciliation = null,
  emptyMessage = "Diagnostics will appear after the cached dataset has enough parsed history to score coverage and freshness."
}: DataQualityDiagnosticsProps) {
  if (!diagnostics) {
    return <div className="text-muted">{emptyMessage}</div>;
  }

  const hasSignal =
    diagnostics.coverage_ratio != null ||
    diagnostics.fallback_ratio != null ||
    diagnostics.parser_confidence != null ||
    diagnostics.reconciliation_penalty != null ||
    diagnostics.reconciliation_disagreement_count > 0 ||
    diagnostics.stale_flags.length > 0 ||
    diagnostics.missing_field_flags.length > 0 ||
    hasReconciliationSignal(reconciliation);

  if (!hasSignal) {
    return <div className="text-muted">{emptyMessage}</div>;
  }

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))" }}>
        <MetricCard label="Coverage" value={formatRatio(diagnostics.coverage_ratio)} />
        <MetricCard label="Fallback" value={formatRatio(diagnostics.fallback_ratio)} />
        <MetricCard label="Parser Confidence" value={formatRatio(diagnostics.parser_confidence)} />
        <MetricCard label="Reconciliation Penalty" value={formatRatio(diagnostics.reconciliation_penalty)} />
        <MetricCard label="Disagreements" value={diagnostics.reconciliation_disagreement_count.toLocaleString()} />
        <MetricCard label="Stale Flags" value={diagnostics.stale_flags.length.toLocaleString()} />
      </div>
      <FlagRow label="Stale / Freshness" flags={diagnostics.stale_flags} emptyLabel="Fresh cache path" />
      <FlagRow label="Missing Fields" flags={diagnostics.missing_field_flags} emptyLabel="No missing-field flags" />
      {reconciliation ? <ReconciliationSection reconciliation={reconciliation} /> : null}
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ border: "1px solid var(--panel-border)", borderRadius: 8, padding: 12, background: "var(--panel)" }}>
      <div className="text-muted" style={{ fontSize: 12, marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color: "var(--surface-strong-text)" }}>{value}</div>
    </div>
  );
}

function FlagRow({ label, flags, emptyLabel }: { label: string; flags: string[]; emptyLabel: string }) {
  return (
    <div style={{ display: "grid", gap: 8 }}>
      <div className="text-muted" style={{ fontSize: 12 }}>{label}</div>
      {flags.length ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {flags.map((flag) => (
            <span
              key={`${label}-${flag}`}
              style={{
                border: "1px solid color-mix(in srgb, var(--warning) 35%, var(--panel-border))",
                borderRadius: 999,
                padding: "4px 10px",
                fontSize: 12,
                color: "var(--surface-strong-text)",
                background: "color-mix(in srgb, var(--warning) 14%, var(--panel))"
              }}
            >
              {flag}
            </span>
          ))}
        </div>
      ) : (
        <div className="text-muted">{emptyLabel}</div>
      )}
    </div>
  );
}

function ReconciliationSection({ reconciliation }: { reconciliation: FinancialReconciliationPayload }) {
  return (
    <div style={{ display: "grid", gap: 12, paddingTop: 4 }}>
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
        <div style={{ display: "grid", gap: 4 }}>
          <div className="text-muted" style={{ fontSize: 12 }}>Statement Reconciliation</div>
          <div style={{ fontSize: 18, fontWeight: 700 }}>{titleCase(reconciliation.status)}</div>
        </div>
        <StatusChip status={reconciliation.status} />
      </div>

      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
        <MetaCard label="As Of" value={formatDate(reconciliation.as_of)} />
        <MetaCard label="Last Refreshed" value={formatDate(reconciliation.last_refreshed_at)} />
        <MetaCard label="Confidence" value={formatRatio(reconciliation.confidence_score)} />
        <MetaCard label="Sources" value={reconciliation.provenance_sources.join(", ") || "n/a"} />
      </div>

      <FlagRow label="Confidence Flags" flags={reconciliation.confidence_flags} emptyLabel="No confidence penalties" />
      <FlagRow label="Reconciliation Missing Fields" flags={reconciliation.missing_field_flags} emptyLabel="No reconciliation missing fields" />

      {reconciliation.comparisons.length ? (
        <div style={{ display: "grid", gap: 10 }}>
          <div className="text-muted" style={{ fontSize: 12 }}>Exact SEC tags and periods used for the latest comparison</div>
          <div style={{ display: "grid", gap: 10 }}>
            {reconciliation.comparisons.map((comparison) => (
              <ComparisonCard key={comparison.metric_key} comparison={comparison} />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ComparisonCard({ comparison }: { comparison: FinancialReconciliationPayload["comparisons"][number] }) {
  return (
    <div style={{ border: "1px solid var(--panel-border)", borderRadius: 8, padding: 12, background: "var(--panel)", display: "grid", gap: 10 }}>
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
        <div style={{ display: "grid", gap: 4 }}>
          <div className="text-muted" style={{ fontSize: 12 }}>{titleCase(comparison.metric_key)}</div>
          <div style={{ fontSize: 16, fontWeight: 700 }}>{titleCase(comparison.status)}</div>
        </div>
        <div style={{ display: "grid", gap: 4, textAlign: "right" }}>
          <div style={{ fontWeight: 700 }}>{formatCompactNumber(comparison.companyfacts_value)}</div>
          <div className="text-muted" style={{ fontSize: 12 }}>companyfacts</div>
        </div>
      </div>

      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
        <LineageCard label="Companyfacts" fact={comparison.companyfacts_fact} />
        <LineageCard label="Filing Parser" fact={comparison.filing_parser_fact} />
      </div>

      <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))" }}>
        <MetaCard label="Parser Value" value={formatCompactNumber(comparison.filing_parser_value)} />
        <MetaCard label="Delta" value={formatCompactNumber(comparison.delta)} />
        <MetaCard label="Relative Delta" value={formatRatio(comparison.relative_delta)} />
        <MetaCard label="Penalty" value={formatRatio(comparison.confidence_penalty)} />
      </div>
    </div>
  );
}

function LineageCard({ label, fact }: { label: string; fact: FinancialFactReferencePayload | null }) {
  return (
    <div style={{ border: "1px solid var(--panel-border)", borderRadius: 8, padding: 10, background: "var(--panel)", display: "grid", gap: 6 }}>
      <div className="text-muted" style={{ fontSize: 12 }}>{label}</div>
      {fact ? (
        <>
          <div style={{ fontWeight: 700, color: "var(--surface-strong-text)" }}>{formatFactLabel(fact)}</div>
          <div className="text-muted" style={{ fontSize: 12 }}>{formatPeriodRange(fact.period_start, fact.period_end)}</div>
          <div className="text-muted" style={{ fontSize: 12 }}>{fact.accession_number || fact.source || "No accession metadata"}</div>
        </>
      ) : (
        <div className="text-muted">No lineage available</div>
      )}
    </div>
  );
}

function MetaCard({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ border: "1px solid var(--panel-border)", borderRadius: 8, padding: 10, background: "var(--panel)", display: "grid", gap: 4 }}>
      <div className="text-muted" style={{ fontSize: 12 }}>{label}</div>
      <div style={{ fontWeight: 700, wordBreak: "break-word", color: "var(--surface-strong-text)" }}>{value}</div>
    </div>
  );
}

function StatusChip({ status }: { status: FinancialReconciliationPayload["status"] }) {
  const palette = {
    matched: { border: "color-mix(in srgb, var(--positive) 35%, var(--panel-border))", text: "var(--positive)", background: "color-mix(in srgb, var(--positive) 12%, var(--panel))" },
    disagreement: { border: "color-mix(in srgb, var(--warning) 35%, var(--panel-border))", text: "var(--warning)", background: "color-mix(in srgb, var(--warning) 12%, var(--panel))" },
    parser_missing: { border: "color-mix(in srgb, var(--warning) 35%, var(--panel-border))", text: "var(--surface-strong-text)", background: "color-mix(in srgb, var(--warning) 14%, var(--panel))" },
    unsupported_form: { border: "var(--panel-border)", text: "var(--text-muted)", background: "var(--panel)" }
  }[status];

  return (
    <span style={{ border: `1px solid ${palette.border}`, color: palette.text, background: palette.background, borderRadius: 999, padding: "6px 12px", fontSize: 12, fontWeight: 700 }}>
      {titleCase(status)}
    </span>
  );
}

function hasReconciliationSignal(reconciliation: FinancialReconciliationPayload | null): boolean {
  return Boolean(
    reconciliation && (
      reconciliation.comparisons.length > 0 ||
      reconciliation.confidence_flags.length > 0 ||
      reconciliation.missing_field_flags.length > 0 ||
      reconciliation.confidence_score != null ||
      reconciliation.matched_source
    )
  );
}

function formatFactLabel(fact: FinancialFactReferencePayload): string {
  if (fact.taxonomy && fact.tag) {
    return `${fact.taxonomy}:${fact.tag}`;
  }
  if (fact.form) {
    return fact.form;
  }
  return fact.source || "Unavailable";
}

function formatPeriodRange(start: string | null, end: string | null): string {
  if (!start && !end) {
    return "No SEC period metadata";
  }
  if (start && end) {
    return `${formatDate(start)} to ${formatDate(end)}`;
  }
  return formatDate(start || end);
}

function formatRatio(value: number | null): string {
  if (value == null) {
    return "n/a";
  }
  return formatPercent(value);
}