"use client";

import { CommercialFallbackNotice } from "@/components/ui/commercial-fallback-notice";
import { formatDate } from "@/lib/format";
import type { ProvenanceEntryPayload, SourceMixPayload } from "@/lib/types";

interface SourceFreshnessSummaryProps {
  provenance?: ProvenanceEntryPayload[] | null;
  asOf?: string | null;
  lastRefreshedAt?: string | null;
  sourceMix?: SourceMixPayload | null;
  confidenceFlags?: string[] | null;
  emptyMessage?: string;
}

export function SourceFreshnessSummary({
  provenance,
  asOf,
  lastRefreshedAt,
  sourceMix,
  confidenceFlags,
  emptyMessage = "Source metadata is not available yet."
}: SourceFreshnessSummaryProps) {
  const entries = provenance ?? [];
  const flags = confidenceFlags ?? [];

  if (!entries.length && !asOf && !lastRefreshedAt && !flags.length) {
    return <div className="text-muted">{emptyMessage}</div>;
  }

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {asOf ? <span className="pill">As of {formatDate(asOf)}</span> : null}
        {lastRefreshedAt ? <span className="pill">Refreshed {formatDate(lastRefreshedAt)}</span> : null}
        <span className="pill">{formatSourceMix(sourceMix, entries)}</span>
        <span className="pill">Sources {entries.length}</span>
      </div>

      <CommercialFallbackNotice provenance={entries} sourceMix={sourceMix} />

      {flags.length ? (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {flags.map((flag) => (
            <span key={flag} className="pill">{humanizeFlag(flag)}</span>
          ))}
        </div>
      ) : null}

      {entries.length ? (
        <div style={{ display: "grid", gap: 10 }}>
          {entries.map((entry) => (
            <div key={entry.source_id} className="filing-link-card" style={{ display: "grid", gap: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <div style={{ display: "grid", gap: 4 }}>
                  <strong>{entry.display_label}</strong>
                  <div className="text-muted" style={{ fontSize: "var(--text-xs)" }}>{entry.source_id}</div>
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <span className="pill">{humanizeFlag(entry.role)}</span>
                  <span className="pill">{humanizeFlag(entry.source_tier)}</span>
                  <span className="pill">TTL {formatTtl(entry.default_freshness_ttl_seconds)}</span>
                </div>
              </div>

              <div className="text-muted" style={{ fontSize: "var(--text-sm)", lineHeight: 1.55 }}>
                {entry.disclosure_note}
              </div>

              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                {entry.as_of ? <span className="text-muted">As of {formatDate(entry.as_of)}</span> : null}
                {entry.last_refreshed_at ? <span className="text-muted">Refreshed {formatDate(entry.last_refreshed_at)}</span> : null}
                <a href={entry.url} target="_blank" rel="noreferrer" className="ticker-button" style={{ width: "fit-content" }}>
                  Open source
                </a>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function formatSourceMix(sourceMix: SourceMixPayload | null | undefined, entries: ProvenanceEntryPayload[]): string {
  if (!entries.length) {
    return "No source mix";
  }
  if (sourceMix?.official_only) {
    return "Official/public only";
  }
  if ((sourceMix?.fallback_source_ids.length ?? 0) > 0) {
    return "Official + labeled fallback";
  }
  return "Mixed public inputs";
}

function formatTtl(ttlSeconds: number): string {
  if (ttlSeconds <= 0) {
    return "manual";
  }
  if (ttlSeconds % 86_400 === 0) {
    return `${ttlSeconds / 86_400}d`;
  }
  if (ttlSeconds % 3_600 === 0) {
    return `${ttlSeconds / 3_600}h`;
  }
  if (ttlSeconds % 60 === 0) {
    return `${ttlSeconds / 60}m`;
  }
  return `${ttlSeconds}s`;
}

function humanizeFlag(value: string): string {
  return value.replaceAll("_", " ");
}
