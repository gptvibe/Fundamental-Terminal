import type { ActivityFeedEntryPayload, AlertPayload } from "@/lib/types";

export type SemanticTone = "red" | "gold" | "green" | "cyan";

const POSITIVE_BADGES = new Set(["BUY", "ADDED", "ADD", "INCREASE", "INCREASED", "NEW"]);
const NEGATIVE_BADGES = new Set(["SELL", "SOLD", "REMOVE", "REMOVED", "DECREASE", "DECREASED", "EXIT", "EXITED", "144"]);
const GOVERNANCE_FORM_PREFIXES = ["DEF 14", "DEFA14", "PRE 14", "PRER14", "DEFR14"];
const OWNERSHIP_FORM_MARKERS = ["13D", "13G"];

export function toneForAlertLevel(level: AlertPayload["level"]): SemanticTone {
  switch (level) {
    case "high":
      return "red";
    case "medium":
      return "gold";
    case "low":
      return "green";
    default:
      return "cyan";
  }
}

export function toneForAlertSource(source: string): SemanticTone {
  switch (source) {
    case "beneficial-ownership":
      return "green";
    case "capital-markets":
      return "gold";
    case "insider-trades":
      return "red";
    case "institutional-holdings":
      return "cyan";
    default:
      return "cyan";
  }
}

export function toneForEntryType(type: string): SemanticTone {
  switch (type) {
    case "form144":
      return "red";
    case "event":
    case "earnings":
    case "governance":
      return "gold";
    case "ownership-change":
      return "green";
    default:
      return "cyan";
  }
}

export function toneForEntryBadge(type: string, badge: string): SemanticTone {
  const normalizedBadge = badge.trim().toUpperCase();

  if (!normalizedBadge) {
    return toneForEntryType(type);
  }

  if (type === "form144" || normalizedBadge === "144") {
    return "red";
  }

  if (POSITIVE_BADGES.has(normalizedBadge)) {
    return "green";
  }

  if (NEGATIVE_BADGES.has(normalizedBadge)) {
    return "red";
  }

  if (OWNERSHIP_FORM_MARKERS.some((marker) => normalizedBadge.includes(marker))) {
    return "green";
  }

  if (GOVERNANCE_FORM_PREFIXES.some((prefix) => normalizedBadge.startsWith(prefix))) {
    return "gold";
  }

  if (normalizedBadge === "8-K" || normalizedBadge === "EARNINGS" || normalizedBadge === "UPDATE") {
    return "gold";
  }

  return toneForEntryType(type);
}

export function toneForEntryCard(entry: Pick<ActivityFeedEntryPayload, "type" | "badge">): SemanticTone {
  if (entry.type === "form144" || entry.type === "insider" || entry.type === "ownership-change") {
    return toneForEntryBadge(entry.type, entry.badge);
  }

  return toneForEntryType(entry.type);
}

export function toneForInsiderSentiment(sentiment: string | null | undefined): SemanticTone {
  const normalized = (sentiment ?? "").toLowerCase();

  if (normalized === "bullish") {
    return "green";
  }

  if (normalized === "bearish") {
    return "red";
  }

  return "gold";
}