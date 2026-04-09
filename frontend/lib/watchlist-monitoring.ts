export type WatchlistTriageState = "inbox" | "reviewing" | "monitoring" | "ready";

export type WatchlistMonitoringProfileKey = "deep-dive" | "quality-compounder" | "event-watch" | "special-situation";

export type WatchlistPrimaryFilter =
  | "all"
  | "review-due"
  | "attention"
  | "stale"
  | "material-change"
  | "no-note"
  | "no-rationale"
  | "undervalued"
  | "quality"
  | "capital-return"
  | "balance-risk"
  | "snoozed"
  | "hold";

export type WatchlistSort = "review" | "attention" | "undervaluation" | "quality" | "capital-return" | "balance-risk";

export interface WatchlistMonitoringProfileDefinition {
  key: WatchlistMonitoringProfileKey;
  label: string;
  description: string;
  triageState: WatchlistTriageState;
  cadenceDays: number;
}

export interface LocalWatchlistMonitoringEntry {
  ticker: string;
  triageState: WatchlistTriageState;
  profileKey: WatchlistMonitoringProfileKey | null;
  rationale: string;
  lastReviewedAt: string | null;
  nextReviewAt: string | null;
  snoozedUntil: string | null;
  holdUntil: string | null;
  updatedAt: string;
}

export interface WatchlistSavedViewCriteria {
  primaryFilter: WatchlistPrimaryFilter;
  triageStates: WatchlistTriageState[];
  sortBy: WatchlistSort;
  searchText: string;
  profileKey: WatchlistMonitoringProfileKey | null;
}

export interface LocalWatchlistSavedView {
  id: string;
  name: string;
  criteria: WatchlistSavedViewCriteria;
  createdAt: string;
  updatedAt: string;
}

export interface WatchlistDeskPreset {
  key: string;
  label: string;
  description: string;
  criteria: Partial<WatchlistSavedViewCriteria>;
}

export const WATCHLIST_TRIAGE_STATES: WatchlistTriageState[] = ["inbox", "reviewing", "monitoring", "ready"];

export const WATCHLIST_MONITORING_PROFILES: WatchlistMonitoringProfileDefinition[] = [
  {
    key: "deep-dive",
    label: "Deep Dive",
    description: "Front-footed underwriting queue with short review loops.",
    triageState: "reviewing",
    cadenceDays: 7,
  },
  {
    key: "quality-compounder",
    label: "Quality Compounder",
    description: "Monthly quality and capital return check-ins.",
    triageState: "monitoring",
    cadenceDays: 30,
  },
  {
    key: "event-watch",
    label: "Event Watch",
    description: "Catalyst-driven names that need near-term review.",
    triageState: "ready",
    cadenceDays: 5,
  },
  {
    key: "special-situation",
    label: "Special Situation",
    description: "Capital structure or filing-driven work that needs tighter follow-up.",
    triageState: "reviewing",
    cadenceDays: 14,
  },
];

export const DEFAULT_WATCHLIST_VIEW_CRITERIA: WatchlistSavedViewCriteria = {
  primaryFilter: "all",
  triageStates: [],
  sortBy: "review",
  searchText: "",
  profileKey: null,
};

export const WATCHLIST_DESK_PRESETS: WatchlistDeskPreset[] = [
  {
    key: "daily-triage",
    label: "Daily Triage",
    description: "Review what is due, new, or already throwing alerts.",
    criteria: {
      primaryFilter: "review-due",
      sortBy: "review",
      triageStates: ["inbox", "reviewing", "ready"],
    },
  },
  {
    key: "change-sweep",
    label: "Change Sweep",
    description: "Focus on filings with fresh high-signal changes from the brief model.",
    criteria: {
      primaryFilter: "material-change",
      sortBy: "attention",
    },
  },
  {
    key: "thesis-hygiene",
    label: "Thesis Hygiene",
    description: "Clean up names missing a rationale or local note before they drift.",
    criteria: {
      primaryFilter: "no-rationale",
      sortBy: "review",
    },
  },
  {
    key: "parked-names",
    label: "Parked Names",
    description: "Surface the snoozed or held list when you want to reopen it.",
    criteria: {
      primaryFilter: "hold",
      sortBy: "review",
    },
  },
];

export function isWatchlistTriageState(value: unknown): value is WatchlistTriageState {
  return typeof value === "string" && WATCHLIST_TRIAGE_STATES.includes(value as WatchlistTriageState);
}

export function isWatchlistMonitoringProfileKey(value: unknown): value is WatchlistMonitoringProfileKey {
  return typeof value === "string" && WATCHLIST_MONITORING_PROFILES.some((profile) => profile.key === value);
}

export function isWatchlistPrimaryFilter(value: unknown): value is WatchlistPrimaryFilter {
  return typeof value === "string" && [
    "all",
    "review-due",
    "attention",
    "stale",
    "material-change",
    "no-note",
    "no-rationale",
    "undervalued",
    "quality",
    "capital-return",
    "balance-risk",
    "snoozed",
    "hold",
  ].includes(value);
}

export function isWatchlistSort(value: unknown): value is WatchlistSort {
  return typeof value === "string" && ["review", "attention", "undervaluation", "quality", "capital-return", "balance-risk"].includes(value);
}

export function getWatchlistMonitoringProfile(key: WatchlistMonitoringProfileKey | null | undefined): WatchlistMonitoringProfileDefinition | null {
  if (!key) {
    return null;
  }
  return WATCHLIST_MONITORING_PROFILES.find((profile) => profile.key === key) ?? null;
}

export function buildDefaultMonitoringEntry(ticker: string): LocalWatchlistMonitoringEntry {
  return {
    ticker,
    triageState: "inbox",
    profileKey: null,
    rationale: "",
    lastReviewedAt: null,
    nextReviewAt: null,
    snoozedUntil: null,
    holdUntil: null,
    updatedAt: new Date(0).toISOString(),
  };
}