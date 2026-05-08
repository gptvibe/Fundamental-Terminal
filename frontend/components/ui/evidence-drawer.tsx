"use client";

import { useMemo, useState } from "react";

import { resolveCommercialFallbackLabels } from "@/components/ui/commercial-fallback-notice";
import { Dialog } from "@/components/ui/dialog";
import { EvidenceMetaBlock } from "@/components/ui/evidence-meta-block";
import { formatDate } from "@/lib/format";
import type {
  DataQualityDiagnosticsPayload,
  ProvenanceEntryPayload,
  SourceMixPayload,
  SourceRole,
  SourceTier,
} from "@/lib/types";

export interface EvidenceMetricReference {
  label: string;
  source_id?: string | null;
  source_tier?: SourceTier | null;
  display_label?: string | null;
  canonical_url?: string | null;
  role?: SourceRole | null;
  as_of?: string | null;
  last_refreshed_at?: string | null;
  confidence_flags?: string[];
  diagnostics?: string | null;
  accession_number?: string | null;
  taxonomy?: string | null;
  tag?: string | null;
  formula_note?: string | null;
}

interface EvidenceDrawerProps {
  title: string;
  triggerLabel?: string;
  description?: string;
  provenance?: ProvenanceEntryPayload[] | null;
  sourceMix?: SourceMixPayload | null;
  asOf?: string | null;
  lastRefreshedAt?: string | null;
  confidenceFlags?: string[] | null;
  diagnostics?: DataQualityDiagnosticsPayload | null;
  metrics?: EvidenceMetricReference[] | null;
  strictOfficialMode?: boolean;
}

export function EvidenceDrawer({
  title,
  triggerLabel = "View evidence",
  description,
  provenance,
  sourceMix,
  asOf,
  lastRefreshedAt,
  confidenceFlags,
  diagnostics,
  metrics,
  strictOfficialMode = false,
}: EvidenceDrawerProps) {
  const [open, setOpen] = useState(false);
  const drawerId = useMemo(() => `evidence-drawer-${slugify(title)}`, [title]);
  const entries = provenance ?? [];
  const metricRows = metrics ?? [];
  const sourceById = useMemo(() => new Map(entries.map((entry) => [entry.source_id, entry])), [entries]);
  const fallbackLabels = resolveCommercialFallbackLabels(entries, sourceMix);
  const hasEvidence = Boolean(entries.length || metricRows.length || confidenceFlags?.length || diagnostics);

  return (
    <>
      <button
        type="button"
        className="research-brief-evidence-trigger"
        aria-haspopup="dialog"
        aria-expanded={open ? "true" : "false"}
        aria-controls={open ? drawerId : undefined}
        onClick={() => setOpen(true)}
      >
        {triggerLabel}
      </button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        labelledBy={`${drawerId}-title`}
        describedBy={`${drawerId}-description`}
        contentClassName="research-brief-evidence-drawer"
      >
        <div id={drawerId} className="research-brief-evidence-drawer-stack">
          <div className="research-brief-evidence-drawer-head">
            <div>
              <h3 id={`${drawerId}-title`} className="research-brief-evidence-drawer-title">
                {title}
              </h3>
              <p id={`${drawerId}-description`} className="research-brief-evidence-drawer-copy">
                {description ?? "Section-level and metric-level provenance from persisted payload evidence."}
              </p>
            </div>
            <button type="button" className="research-brief-evidence-drawer-close" onClick={() => setOpen(false)}>
              Close
            </button>
          </div>

          {strictOfficialMode ? (
            <div className={`research-brief-evidence-callout ${fallbackLabels.length ? "tone-red" : "tone-green"}`}>
              {fallbackLabels.length
                ? `Strict official mode is enabled, but fallback evidence is still present: ${fallbackLabels.join(", ")}.`
                : "Strict official mode is enabled. Commercial fallback evidence is suppressed for this surface."}
            </div>
          ) : null}

          {fallbackLabels.length ? (
            <div className="research-brief-evidence-callout tone-gold">
              Commercial fallback in use: {fallbackLabels.join(", ")}
            </div>
          ) : null}

          {hasEvidence ? (
            <div className="research-brief-evidence-section">
              <h4 className="research-brief-evidence-section-title">Section evidence</h4>
              <EvidenceMetaBlock
                items={[
                  {
                    label: "Source mix",
                    value: sourceMix?.official_only
                      ? "Official/public only"
                      : fallbackLabels.length
                        ? "Official + labeled fallback"
                        : entries.length
                          ? "Cached source mix"
                          : "Pending",
                    emphasized: true,
                  },
                  { label: "As of", value: asOf ? formatDate(asOf) : "Pending" },
                  {
                    label: "Last refreshed",
                    value: lastRefreshedAt ? formatDate(lastRefreshedAt) : "Pending",
                  },
                  {
                    label: "Confidence flags",
                    value: confidenceFlags?.length ? confidenceFlags.join(", ") : "None",
                  },
                ]}
              />
              {diagnostics ? <DiagnosticsBlock diagnostics={diagnostics} /> : null}
            </div>
          ) : null}

          {entries.length ? (
            <div className="research-brief-evidence-section">
              <h4 className="research-brief-evidence-section-title">Provenance sources</h4>
              <div className="research-brief-evidence-provenance-list">
                {entries.map((entry) => (
                  <article key={`${entry.source_id}-${entry.role}`} className="research-brief-evidence-provenance-card">
                    <div className="research-brief-evidence-provenance-title">{entry.display_label}</div>
                    <EvidenceMetaBlock
                      items={[
                        { label: "Source ID", value: entry.source_id },
                        { label: "Source tier", value: entry.source_tier },
                        { label: "Role", value: entry.role },
                        {
                          label: "Canonical URL",
                          value: (
                            <a href={entry.url} target="_blank" rel="noreferrer" className="research-brief-evidence-link">
                              {entry.url}
                            </a>
                          ),
                        },
                        { label: "As of", value: entry.as_of ? formatDate(entry.as_of) : "Pending" },
                        {
                          label: "Last refreshed",
                          value: entry.last_refreshed_at ? formatDate(entry.last_refreshed_at) : "Pending",
                        },
                      ]}
                    />
                    <p className="research-brief-evidence-note">{entry.disclosure_note}</p>
                  </article>
                ))}
              </div>
            </div>
          ) : null}

          {metricRows.length ? (
            <div className="research-brief-evidence-section">
              <h4 className="research-brief-evidence-section-title">Metric evidence</h4>
              <div className="research-brief-evidence-provenance-list">
                {metricRows.map((metric) => {
                  const source = metric.source_id ? sourceById.get(metric.source_id) : undefined;
                  const label = metric.display_label ?? source?.display_label ?? "Unavailable";
                  const sourceTier = metric.source_tier ?? source?.source_tier ?? "Unavailable";
                  const canonicalUrl = metric.canonical_url ?? source?.url ?? null;

                  return (
                    <article key={`${metric.label}-${metric.accession_number ?? "none"}`} className="research-brief-evidence-provenance-card">
                      <div className="research-brief-evidence-provenance-title">{metric.label}</div>
                      <EvidenceMetaBlock
                        items={[
                          { label: "Source ID", value: metric.source_id ?? source?.source_id ?? "Unavailable" },
                          { label: "Source tier", value: sourceTier },
                          { label: "Display label", value: label },
                          {
                            label: "Canonical URL",
                            value: canonicalUrl ? (
                              <a href={canonicalUrl} target="_blank" rel="noreferrer" className="research-brief-evidence-link">
                                {canonicalUrl}
                              </a>
                            ) : (
                              "Unavailable"
                            ),
                          },
                          { label: "Role", value: metric.role ?? source?.role ?? "Unavailable" },
                          { label: "As of", value: metric.as_of ? formatDate(metric.as_of) : source?.as_of ? formatDate(source.as_of) : "Pending" },
                          {
                            label: "Last refreshed",
                            value: metric.last_refreshed_at
                              ? formatDate(metric.last_refreshed_at)
                              : source?.last_refreshed_at
                                ? formatDate(source.last_refreshed_at)
                                : "Pending",
                          },
                          {
                            label: "Confidence flags",
                            value:
                              metric.confidence_flags?.length
                                ? metric.confidence_flags.join(", ")
                                : confidenceFlags?.length
                                  ? confidenceFlags.join(", ")
                                  : "None",
                          },
                          { label: "Diagnostics", value: metric.diagnostics ?? "None" },
                          { label: "Filing accession", value: metric.accession_number ?? "Unavailable" },
                          { label: "Taxonomy", value: metric.taxonomy ?? "Unavailable" },
                          { label: "Tag", value: metric.tag ?? "Unavailable" },
                          { label: "Formula/computation note", value: metric.formula_note ?? "Unavailable" },
                        ]}
                      />
                    </article>
                  );
                })}
              </div>
            </div>
          ) : null}

          {!hasEvidence ? <p className="research-brief-evidence-unavailable">Evidence unavailable for this field.</p> : null}
        </div>
      </Dialog>
    </>
  );
}

function DiagnosticsBlock({ diagnostics }: { diagnostics: DataQualityDiagnosticsPayload }) {
  const pairs: Array<{ label: string; value: string }> = [
    {
      label: "Coverage ratio",
      value: diagnostics.coverage_ratio == null ? "Unavailable" : diagnostics.coverage_ratio.toFixed(2),
    },
    {
      label: "Fallback ratio",
      value: diagnostics.fallback_ratio == null ? "Unavailable" : diagnostics.fallback_ratio.toFixed(2),
    },
    {
      label: "Stale flags",
      value: diagnostics.stale_flags.length ? diagnostics.stale_flags.join(", ") : "None",
    },
    {
      label: "Missing fields",
      value: diagnostics.missing_field_flags.length ? diagnostics.missing_field_flags.join(", ") : "None",
    },
    {
      label: "Parser confidence",
      value: diagnostics.parser_confidence == null ? "Unavailable" : diagnostics.parser_confidence.toFixed(2),
    },
    {
      label: "Reconciliation penalty",
      value:
        diagnostics.reconciliation_penalty == null ? "Unavailable" : diagnostics.reconciliation_penalty.toFixed(2),
    },
  ];

  return (
    <div className="research-brief-evidence-diagnostics">
      <h5 className="research-brief-evidence-subtitle">Diagnostics</h5>
      <EvidenceMetaBlock items={pairs.map((pair) => ({ label: pair.label, value: pair.value }))} />
    </div>
  );
}

function slugify(value: string): string {
  return value.trim().toLowerCase().replaceAll(/[^a-z0-9]+/g, "-").replaceAll(/^-+|-+$/g, "") || "field";
}