import type { SourceQualityPayload } from "@/lib/types";

type BadgeTone = "green" | "cyan" | "gold" | "red";

type BadgeDescriptor = {
  key: string;
  label: string;
  tooltip: string;
  tone: BadgeTone;
};

const BADGE_TOOLTIPS: Record<string, string> = {
  official_sec: "Official SEC filing or SEC XBRL data.",
  derived_from_sec: "Computed from SEC disclosures with deterministic formulas.",
  cached: "Served from persisted cache with freshness metadata.",
  stale: "Data is older than expected freshness thresholds.",
  fallback_market: "Fallback market/profile source. Not official SEC fundamentals.",
  experimental: "Confidence is experimental. Treat this output as directional.",
};

export function buildSourceQualityBadges(sourceQuality: SourceQualityPayload | null | undefined): BadgeDescriptor[] {
  if (!sourceQuality) {
    return [];
  }

  const badges: BadgeDescriptor[] = [];

  if (sourceQuality.source_type === "official_sec") {
    badges.push({ key: "official_sec", label: "Official SEC", tooltip: BADGE_TOOLTIPS.official_sec, tone: "green" });
  }
  if (sourceQuality.source_type === "derived_from_sec") {
    badges.push({ key: "derived_from_sec", label: "Derived", tooltip: BADGE_TOOLTIPS.derived_from_sec, tone: "cyan" });
  }
  if (sourceQuality.freshness_time) {
    badges.push({ key: "cached", label: "Cached", tooltip: BADGE_TOOLTIPS.cached, tone: "cyan" });
  }
  if (sourceQuality.stale) {
    badges.push({ key: "stale", label: "Stale", tooltip: BADGE_TOOLTIPS.stale, tone: "red" });
  }
  if (sourceQuality.source_type === "fallback_market") {
    badges.push({ key: "fallback_market", label: "Fallback", tooltip: BADGE_TOOLTIPS.fallback_market, tone: "gold" });
  }
  if (sourceQuality.confidence_level === "experimental") {
    badges.push({ key: "experimental", label: "Experimental", tooltip: BADGE_TOOLTIPS.experimental, tone: "gold" });
  }

  return badges;
}

export function SourceQualityBadges({
  sourceQuality,
  className,
}: {
  sourceQuality: SourceQualityPayload | null | undefined;
  className?: string;
}) {
  const badges = buildSourceQualityBadges(sourceQuality);
  if (!badges.length) {
    return null;
  }

  return (
    <div className={className} style={{ display: "flex", gap: 8, flexWrap: "wrap" }} aria-label="Source quality badges">
      {badges.map((badge) => (
        <span key={badge.key} className={`company-source-chip tone-${badge.tone}`} title={badge.tooltip}>
          <span className="company-source-chip-label">Data trust</span>
          <span className="company-source-chip-value">{badge.label}</span>
        </span>
      ))}
    </div>
  );
}
