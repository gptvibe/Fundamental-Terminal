import { resolveCommercialFallbackLabels } from "@/components/ui/commercial-fallback-notice";
import { SourceBadge } from "@/components/ui/source-badge";
import { formatDate } from "@/lib/format";
import type { DataQualityDiagnosticsPayload, ProvenanceEntryPayload, SourceMixPayload } from "@/lib/types";

interface SourceRibbonProps {
  provenance?: ProvenanceEntryPayload[] | null;
  sourceMix?: SourceMixPayload | null;
  asOf?: string | null;
  lastRefreshedAt?: string | null;
  confidenceFlags?: string[] | null;
  diagnostics?: DataQualityDiagnosticsPayload | null;
  emptyMessage?: string;
}

export function SourceRibbon({
  provenance,
  sourceMix,
  asOf,
  lastRefreshedAt,
  confidenceFlags,
  diagnostics,
  emptyMessage = "Source unavailable",
}: SourceRibbonProps) {
  const entries = provenance ?? [];
  const fallbackLabels = resolveCommercialFallbackLabels(entries, sourceMix);
  const flags = confidenceFlags ?? [];

  if (!entries.length) {
    return (
      <div className="source-ribbon" data-testid="source-ribbon-unavailable">
        <SourceBadge />
        <div className="source-ribbon-unavailable-copy">{emptyMessage}</div>
      </div>
    );
  }

  const uniqueEntries = dedupeBySourceId(entries);

  return (
    <div className="source-ribbon" data-testid="source-ribbon">
      <div className="source-ribbon-badges">
        {uniqueEntries.map((entry) => (
          <SourceBadge
            key={`${entry.source_id}:${entry.role}`}
            sourceTier={entry.source_tier}
            sourceLabel={entry.display_label}
            sourceId={entry.source_id}
            compact
          />
        ))}
      </div>

      <div className="source-ribbon-meta">
        <span className="source-ribbon-chip">Source mix: {formatSourceMix(sourceMix, entries)}</span>
        <span className="source-ribbon-chip">As of: {asOf ? formatDate(asOf) : "Pending"}</span>
        <span className="source-ribbon-chip">Refreshed: {lastRefreshedAt ? formatDate(lastRefreshedAt) : "Pending"}</span>
      </div>

      {fallbackLabels.length ? (
        <div className="source-ribbon-fallback" data-testid="source-ribbon-fallback">
          <span className="source-ribbon-fallback-label">Commercial fallback</span>
          <span>
            Price or market profile context includes labeled fallback input from {fallbackLabels.join(", ")}.
          </span>
        </div>
      ) : null}

      {flags.length ? (
        <div className="source-ribbon-flags">Confidence flags: {flags.map(humanize).join(", ")}</div>
      ) : null}

      {diagnostics ? (
        <div className="source-ribbon-diagnostics">
          {diagnostics.coverage_ratio != null ? <span>Coverage {formatPercent(diagnostics.coverage_ratio)}</span> : null}
          {diagnostics.fallback_ratio != null ? <span>Fallback ratio {formatPercent(diagnostics.fallback_ratio)}</span> : null}
          {diagnostics.stale_flags.length ? <span>Stale flags {diagnostics.stale_flags.length}</span> : null}
          {diagnostics.missing_field_flags.length ? <span>Missing fields {diagnostics.missing_field_flags.length}</span> : null}
        </div>
      ) : null}
    </div>
  );
}

function dedupeBySourceId(entries: ProvenanceEntryPayload[]): ProvenanceEntryPayload[] {
  const seen = new Set<string>();
  const result: ProvenanceEntryPayload[] = [];

  for (const entry of entries) {
    if (seen.has(entry.source_id)) {
      continue;
    }
    seen.add(entry.source_id);
    result.push(entry);
  }

  return result;
}

function formatSourceMix(sourceMix: SourceMixPayload | null | undefined, entries: ProvenanceEntryPayload[]): string {
  if (!entries.length) {
    return "Source unavailable";
  }
  if (sourceMix?.official_only) {
    return "Official/public only";
  }
  if ((sourceMix?.fallback_source_ids.length ?? 0) > 0) {
    return "Official + labeled fallback";
  }
  return "Mixed public inputs";
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(0)}%`;
}

function humanize(value: string): string {
  return value.replaceAll("_", " ");
}
