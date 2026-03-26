import { formatPercent } from "@/lib/format";
import type { DataQualityDiagnosticsPayload } from "@/lib/types";

interface DataQualityDiagnosticsProps {
  diagnostics: DataQualityDiagnosticsPayload | null | undefined;
  emptyMessage?: string;
}

export function DataQualityDiagnostics({
  diagnostics,
  emptyMessage = "Diagnostics will appear after the cached dataset has enough parsed history to score coverage and freshness."
}: DataQualityDiagnosticsProps) {
  if (!diagnostics) {
    return <div className="text-muted">{emptyMessage}</div>;
  }

  const hasSignal =
    diagnostics.coverage_ratio != null ||
    diagnostics.fallback_ratio != null ||
    diagnostics.parser_confidence != null ||
    diagnostics.stale_flags.length > 0 ||
    diagnostics.missing_field_flags.length > 0;

  if (!hasSignal) {
    return <div className="text-muted">{emptyMessage}</div>;
  }

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))" }}>
        <MetricCard label="Coverage" value={formatRatio(diagnostics.coverage_ratio)} />
        <MetricCard label="Fallback" value={formatRatio(diagnostics.fallback_ratio)} />
        <MetricCard label="Parser Confidence" value={formatRatio(diagnostics.parser_confidence)} />
        <MetricCard label="Stale Flags" value={diagnostics.stale_flags.length.toLocaleString()} />
      </div>
      <FlagRow label="Stale / Freshness" flags={diagnostics.stale_flags} emptyLabel="Fresh cache path" />
      <FlagRow label="Missing Fields" flags={diagnostics.missing_field_flags} emptyLabel="No missing-field flags" />
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, padding: 12, background: "rgba(255,255,255,0.02)" }}>
      <div className="text-muted" style={{ fontSize: 12, marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700 }}>{value}</div>
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
                border: "1px solid rgba(255,215,0,0.25)",
                borderRadius: 999,
                padding: "4px 10px",
                fontSize: 12,
                color: "#FFD700",
                background: "rgba(255,215,0,0.08)"
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

function formatRatio(value: number | null): string {
  if (value == null) {
    return "n/a";
  }
  return formatPercent(value);
}