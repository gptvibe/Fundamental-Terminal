import { titleCase } from "@/lib/format";
import type { SourceTier } from "@/lib/types";

interface SourceBadgeProps {
  sourceTier?: SourceTier | null;
  sourceLabel?: string | null;
  sourceId?: string | null;
  compact?: boolean;
}

const SOURCE_TIER_LABELS: Record<SourceTier, string> = {
  official_regulator: "Official regulator",
  official_statistical: "Official statistical",
  official_treasury_or_fed: "Official treasury/fed",
  derived_from_official: "Derived from official",
  commercial_fallback: "Commercial fallback",
  manual_override: "Manual override",
};

export function SourceBadge({
  sourceTier,
  sourceLabel,
  sourceId,
  compact = false,
}: SourceBadgeProps) {
  if (!sourceTier || !sourceLabel) {
    return (
      <span className="source-badge source-badge-unavailable" data-testid="source-badge-unavailable">
        Source unavailable
      </span>
    );
  }

  return (
    <span className={`source-badge source-badge-${sourceTier}`} data-testid={`source-badge-${sourceTier}`}>
      <span className="source-badge-tier">{SOURCE_TIER_LABELS[sourceTier]}</span>
      <span className="source-badge-label">{sourceLabel}</span>
      {!compact && sourceId ? <span className="source-badge-id">{titleCase(sourceId.replaceAll("_", " "))}</span> : null}
    </span>
  );
}
