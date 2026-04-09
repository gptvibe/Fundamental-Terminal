import type { ProvenanceEntryPayload, SourceMixPayload } from "@/lib/types";

interface CommercialFallbackNoticeProps {
  provenance?: ProvenanceEntryPayload[] | null;
  sourceMix?: SourceMixPayload | null;
  subject?: string;
}

export function CommercialFallbackNotice({
  provenance,
  sourceMix,
  subject = "Price or market profile data on this surface"
}: CommercialFallbackNoticeProps) {
  const sourceLabels = resolveCommercialFallbackLabels(provenance, sourceMix);
  if (!sourceLabels.length) {
    return null;
  }

  const joinedSources = sourceLabels.join(", ");

  return (
    <div className="commercial-fallback-notice">
      <div className="commercial-fallback-notice-label">Fallback label</div>
      <div className="commercial-fallback-notice-value">{joinedSources}</div>
      <div className="commercial-fallback-notice-copy">
        {subject} includes a labeled commercial fallback from {joinedSources}. Core fundamentals remain sourced from official filings and public datasets.
      </div>
    </div>
  );
}

export function resolveCommercialFallbackLabels(
  provenance?: ProvenanceEntryPayload[] | null,
  sourceMix?: SourceMixPayload | null
): string[] {
  const entries = provenance ?? [];
  const fallbackIds = new Set(sourceMix?.fallback_source_ids ?? []);
  const labels = entries
    .filter((entry) => entry.source_tier === "commercial_fallback" || fallbackIds.has(entry.source_id))
    .map((entry) => entry.display_label);

  return Array.from(new Set(labels));
}
