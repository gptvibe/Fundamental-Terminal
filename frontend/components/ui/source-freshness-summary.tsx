"use client";

import { useId, useState } from "react";

import { EvidenceMetaBlock } from "@/components/ui/evidence-meta-block";
import { SourceRibbon } from "@/components/ui/source-ribbon";
import { formatDate } from "@/lib/format";
import type { DataQualityDiagnosticsPayload, ProvenanceEntryPayload, SourceMixPayload } from "@/lib/types";

interface SourceFreshnessSummaryProps {
  provenance?: ProvenanceEntryPayload[] | null;
  asOf?: string | null;
  lastRefreshedAt?: string | null;
  sourceMix?: SourceMixPayload | null;
  confidenceFlags?: string[] | null;
  diagnostics?: DataQualityDiagnosticsPayload | null;
  emptyMessage?: string;
}

export function SourceFreshnessSummary({
  provenance,
  asOf,
  lastRefreshedAt,
  sourceMix,
  confidenceFlags,
  diagnostics,
  emptyMessage = "Source metadata is not available yet."
}: SourceFreshnessSummaryProps) {
  const entries = provenance ?? [];
  const drawerId = useId();
  const [drawerOpen, setDrawerOpen] = useState(true);

  if (!entries.length && !asOf && !lastRefreshedAt && !(confidenceFlags ?? []).length) {
    return <div className="text-muted">{emptyMessage}</div>;
  }

  return (
    <div className="source-freshness-summary">
      <SourceRibbon
        provenance={entries}
        sourceMix={sourceMix}
        asOf={asOf}
        lastRefreshedAt={lastRefreshedAt}
        confidenceFlags={confidenceFlags}
        diagnostics={diagnostics}
      />

      {entries.length ? (
        <div className="source-freshness-stack">
          <div className="source-freshness-topline">
            <div className="source-freshness-note">
              Registry-backed provenance details for this surface.
            </div>
            <button
              type="button"
              className="ticker-button"
              aria-expanded={drawerOpen}
              aria-controls={drawerId}
              onClick={() => setDrawerOpen((current) => !current)}
            >
              {drawerOpen ? "Hide provenance drawer" : "Open provenance drawer"}
            </button>
          </div>

          {drawerOpen ? (
            <div id={drawerId} aria-label="Provenance drawer" className="source-freshness-entry-list">
              {entries.map((entry) => (
                <div key={entry.source_id} className="source-freshness-entry">
                  <div className="source-freshness-entry-head">
                    <div className="source-freshness-entry-heading">
                      <strong className="source-freshness-entry-title">{entry.display_label}</strong>
                      <div className="source-freshness-entry-subtitle">
                        {entry.source_id} · {humanizeFlag(entry.role)} · {humanizeFlag(entry.source_tier)}
                      </div>
                    </div>
                  </div>

                  <EvidenceMetaBlock
                    items={[
                      { label: "Source", value: entry.display_label, emphasized: true },
                      { label: "As of", value: entry.as_of ? formatDate(entry.as_of) : "Pending" },
                      {
                        label: "Freshness",
                        value: formatFreshness(entry.last_refreshed_at, entry.default_freshness_ttl_seconds),
                      },
                      {
                        label: "Fallback label",
                        value: entry.source_tier === "commercial_fallback" || entry.role === "fallback" ? entry.display_label : "Official only",
                      },
                    ]}
                  />

                  <div className="source-freshness-entry-copy">{entry.disclosure_note}</div>

                  <div className="source-freshness-entry-actions">
                    <a href={entry.url} target="_blank" rel="noreferrer" className="ticker-button" style={{ width: "fit-content" }}>
                      Open source
                    </a>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
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

function formatFreshness(lastRefreshedAt: string | null | undefined, ttlSeconds: number | null | undefined): string {
  if (lastRefreshedAt && typeof ttlSeconds === "number") {
    return `Refreshed ${formatDate(lastRefreshedAt)} · TTL ${formatTtl(ttlSeconds)}`;
  }
  if (lastRefreshedAt) {
    return `Refreshed ${formatDate(lastRefreshedAt)}`;
  }
  if (typeof ttlSeconds === "number") {
    return `TTL ${formatTtl(ttlSeconds)}`;
  }
  return "Pending";
}

function humanizeFlag(value: string): string {
  return value.replaceAll("_", " ");
}
