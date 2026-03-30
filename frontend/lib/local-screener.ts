import type {
  OfficialScreenerSearchRequest,
  ScreenerPeriodType,
  ScreenerSortDirection,
  ScreenerSortField,
} from "@/lib/types";

export interface LocalScreenerFilters {
  revenue_growth_min: string;
  operating_margin_min: string;
  fcf_margin_min: string;
  leverage_ratio_max: string;
  dilution_max: string;
  sbc_burden_max: string;
  shareholder_yield_min: string;
  max_filing_lag_days: string;
  exclude_restatements: boolean;
  exclude_stale_periods: boolean;
  excluded_quality_flags: string[];
}

export interface LocalScreenerDraft {
  periodType: ScreenerPeriodType;
  tickerUniverseText: string;
  sortField: ScreenerSortField;
  sortDirection: ScreenerSortDirection;
  limit: number;
  offset: number;
  filters: LocalScreenerFilters;
}

export interface LocalScreenerPreset {
  id: string;
  name: string;
  updatedAt: string;
  draft: LocalScreenerDraft;
}

export interface LocalScreenerState {
  draft: LocalScreenerDraft;
  presets: LocalScreenerPreset[];
}

const NUMERIC_FILTER_FIELDS = [
  "revenue_growth_min",
  "operating_margin_min",
  "fcf_margin_min",
  "leverage_ratio_max",
  "dilution_max",
  "sbc_burden_max",
  "shareholder_yield_min",
  "max_filing_lag_days",
] as const;

const SORT_FIELDS: ReadonlyArray<ScreenerSortField> = [
  "ticker",
  "period_end",
  "revenue_growth",
  "operating_margin",
  "fcf_margin",
  "leverage_ratio",
  "dilution",
  "sbc_burden",
  "shareholder_yield",
  "filing_lag_days",
  "restatement_count",
  "quality_score",
  "value_score",
  "capital_allocation_score",
  "dilution_risk_score",
  "filing_risk_score",
];

const PERIOD_TYPES: ReadonlyArray<ScreenerPeriodType> = ["quarterly", "annual", "ttm"];
const SORT_DIRECTIONS: ReadonlyArray<ScreenerSortDirection> = ["asc", "desc"];

export const LOCAL_SCREENER_STORAGE_KEY = "ft-local-screener";
export const LOCAL_SCREENER_EVENT = "ft:local-screener";

export const DEFAULT_LOCAL_SCREENER_DRAFT: LocalScreenerDraft = {
  periodType: "ttm",
  tickerUniverseText: "",
  sortField: "revenue_growth",
  sortDirection: "desc",
  limit: 50,
  offset: 0,
  filters: {
    revenue_growth_min: "",
    operating_margin_min: "",
    fcf_margin_min: "",
    leverage_ratio_max: "",
    dilution_max: "",
    sbc_burden_max: "",
    shareholder_yield_min: "",
    max_filing_lag_days: "",
    exclude_restatements: false,
    exclude_stale_periods: false,
    excluded_quality_flags: [],
  },
};

const EMPTY_STATE: LocalScreenerState = {
  draft: DEFAULT_LOCAL_SCREENER_DRAFT,
  presets: [],
};

function canUseStorage(): boolean {
  return typeof window !== "undefined";
}

function writeLocalScreenerState(state: LocalScreenerState): void {
  if (!canUseStorage()) {
    return;
  }

  window.localStorage.setItem(LOCAL_SCREENER_STORAGE_KEY, JSON.stringify(state));
  window.dispatchEvent(new CustomEvent(LOCAL_SCREENER_EVENT, { detail: state }));
}

function normalizeText(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function normalizeBoolean(value: unknown): boolean {
  return value === true;
}

function normalizeNumberInput(value: unknown): string {
  const text = normalizeText(value);
  if (!text) {
    return "";
  }

  return Number.isFinite(Number(text)) ? text : "";
}

function normalizeStringList(values: unknown): string[] {
  if (!Array.isArray(values)) {
    return [];
  }

  const normalized: string[] = [];
  for (const value of values) {
    const text = normalizeText(value);
    if (text && !normalized.includes(text)) {
      normalized.push(text);
    }
  }
  return normalized;
}

function normalizeLimit(value: unknown): number {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  if (!Number.isFinite(parsed)) {
    return DEFAULT_LOCAL_SCREENER_DRAFT.limit;
  }
  return Math.min(200, Math.max(1, parsed));
}

function normalizeOffset(value: unknown): number {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  if (!Number.isFinite(parsed)) {
    return 0;
  }
  return Math.max(0, parsed);
}

function normalizeDraft(value: unknown): LocalScreenerDraft {
  const candidate = value && typeof value === "object" && !Array.isArray(value) ? (value as Partial<LocalScreenerDraft>) : {};
  const filters = candidate.filters && typeof candidate.filters === "object" && !Array.isArray(candidate.filters)
    ? (candidate.filters as Partial<LocalScreenerFilters>)
    : {};

  return {
    periodType: PERIOD_TYPES.includes(candidate.periodType as ScreenerPeriodType)
      ? (candidate.periodType as ScreenerPeriodType)
      : DEFAULT_LOCAL_SCREENER_DRAFT.periodType,
    tickerUniverseText: normalizeText(candidate.tickerUniverseText).toUpperCase(),
    sortField: SORT_FIELDS.includes(candidate.sortField as ScreenerSortField)
      ? (candidate.sortField as ScreenerSortField)
      : DEFAULT_LOCAL_SCREENER_DRAFT.sortField,
    sortDirection: SORT_DIRECTIONS.includes(candidate.sortDirection as ScreenerSortDirection)
      ? (candidate.sortDirection as ScreenerSortDirection)
      : DEFAULT_LOCAL_SCREENER_DRAFT.sortDirection,
    limit: normalizeLimit(candidate.limit),
    offset: normalizeOffset(candidate.offset),
    filters: {
      revenue_growth_min: normalizeNumberInput(filters.revenue_growth_min),
      operating_margin_min: normalizeNumberInput(filters.operating_margin_min),
      fcf_margin_min: normalizeNumberInput(filters.fcf_margin_min),
      leverage_ratio_max: normalizeNumberInput(filters.leverage_ratio_max),
      dilution_max: normalizeNumberInput(filters.dilution_max),
      sbc_burden_max: normalizeNumberInput(filters.sbc_burden_max),
      shareholder_yield_min: normalizeNumberInput(filters.shareholder_yield_min),
      max_filing_lag_days: normalizeNumberInput(filters.max_filing_lag_days),
      exclude_restatements: normalizeBoolean(filters.exclude_restatements),
      exclude_stale_periods: normalizeBoolean(filters.exclude_stale_periods),
      excluded_quality_flags: normalizeStringList(filters.excluded_quality_flags),
    },
  };
}

function normalizePreset(value: unknown): LocalScreenerPreset | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }

  const candidate = value as Partial<LocalScreenerPreset>;
  const name = normalizeText(candidate.name);
  if (!name) {
    return null;
  }

  return {
    id: normalizeText(candidate.id) || buildPresetId(name),
    name,
    updatedAt: normalizeText(candidate.updatedAt) || new Date(0).toISOString(),
    draft: {
      ...normalizeDraft(candidate.draft),
      offset: 0,
    },
  };
}

function normalizeLocalScreenerState(value: unknown): LocalScreenerState {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return EMPTY_STATE;
  }

  const candidate = value as Partial<LocalScreenerState>;
  const presets = Array.isArray(candidate.presets)
    ? candidate.presets
        .map(normalizePreset)
        .filter((preset): preset is LocalScreenerPreset => preset !== null)
        .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))
    : [];

  return {
    draft: normalizeDraft(candidate.draft),
    presets,
  };
}

export function readLocalScreenerState(): LocalScreenerState {
  if (!canUseStorage()) {
    return EMPTY_STATE;
  }

  const raw = window.localStorage.getItem(LOCAL_SCREENER_STORAGE_KEY);
  if (!raw) {
    return EMPTY_STATE;
  }

  try {
    return normalizeLocalScreenerState(JSON.parse(raw));
  } catch {
    window.localStorage.removeItem(LOCAL_SCREENER_STORAGE_KEY);
    return EMPTY_STATE;
  }
}

export function subscribeLocalScreener(onChange: () => void): () => void {
  if (!canUseStorage()) {
    return () => undefined;
  }

  function handleStorage(event: StorageEvent) {
    if (event.key === LOCAL_SCREENER_STORAGE_KEY) {
      onChange();
    }
  }

  window.addEventListener(LOCAL_SCREENER_EVENT, onChange as EventListener);
  window.addEventListener("storage", handleStorage);
  return () => {
    window.removeEventListener(LOCAL_SCREENER_EVENT, onChange as EventListener);
    window.removeEventListener("storage", handleStorage);
  };
}

function updateLocalScreenerState(updater: (current: LocalScreenerState) => LocalScreenerState): LocalScreenerState {
  const nextState = normalizeLocalScreenerState(updater(readLocalScreenerState()));
  writeLocalScreenerState(nextState);
  return nextState;
}

export function saveLocalScreenerDraft(draft: LocalScreenerDraft): LocalScreenerState {
  return updateLocalScreenerState((current) => ({
    ...current,
    draft: normalizeDraft(draft),
  }));
}

export function resetLocalScreenerDraft(): LocalScreenerState {
  return saveLocalScreenerDraft(DEFAULT_LOCAL_SCREENER_DRAFT);
}

export function saveLocalScreenerPreset(name: string, draft: LocalScreenerDraft): LocalScreenerState {
  const normalizedName = normalizeText(name);
  if (!normalizedName) {
    throw new Error("Preset name is required.");
  }

  return updateLocalScreenerState((current) => {
    const now = new Date().toISOString();
    const nextPreset: LocalScreenerPreset = {
      id: current.presets.find((preset) => preset.name.localeCompare(normalizedName, undefined, { sensitivity: "accent" }) === 0)?.id ?? buildPresetId(normalizedName),
      name: normalizedName,
      updatedAt: now,
      draft: {
        ...normalizeDraft(draft),
        offset: 0,
      },
    };

    const nextPresets = [
      nextPreset,
      ...current.presets.filter((preset) => preset.id !== nextPreset.id && preset.name.toLowerCase() !== normalizedName.toLowerCase()),
    ].sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));

    return {
      ...current,
      presets: nextPresets,
    };
  });
}

export function deleteLocalScreenerPreset(presetId: string): LocalScreenerState {
  return updateLocalScreenerState((current) => ({
    ...current,
    presets: current.presets.filter((preset) => preset.id !== presetId),
  }));
}

function parseNumberInput(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

export function parseTickerUniverse(text: string): string[] {
  const tickers = text
    .split(/[\s,]+/)
    .map((value) => value.trim().toUpperCase())
    .filter(Boolean);

  return Array.from(new Set(tickers));
}

export function buildOfficialScreenerSearchRequest(draft: LocalScreenerDraft): OfficialScreenerSearchRequest {
  const normalizedDraft = normalizeDraft(draft);

  return {
    period_type: normalizedDraft.periodType,
    ticker_universe: parseTickerUniverse(normalizedDraft.tickerUniverseText),
    filters: {
      revenue_growth_min: parseNumberInput(normalizedDraft.filters.revenue_growth_min),
      operating_margin_min: parseNumberInput(normalizedDraft.filters.operating_margin_min),
      fcf_margin_min: parseNumberInput(normalizedDraft.filters.fcf_margin_min),
      leverage_ratio_max: parseNumberInput(normalizedDraft.filters.leverage_ratio_max),
      dilution_max: parseNumberInput(normalizedDraft.filters.dilution_max),
      sbc_burden_max: parseNumberInput(normalizedDraft.filters.sbc_burden_max),
      shareholder_yield_min: parseNumberInput(normalizedDraft.filters.shareholder_yield_min),
      max_filing_lag_days: parseNumberInput(normalizedDraft.filters.max_filing_lag_days),
      exclude_restatements: normalizedDraft.filters.exclude_restatements,
      exclude_stale_periods: normalizedDraft.filters.exclude_stale_periods,
      excluded_quality_flags: [...normalizedDraft.filters.excluded_quality_flags],
    },
    sort: {
      field: normalizedDraft.sortField,
      direction: normalizedDraft.sortDirection,
    },
    limit: normalizedDraft.limit,
    offset: normalizedDraft.offset,
  };
}

export function countActiveScreenerFilters(draft: LocalScreenerDraft): number {
  const normalizedDraft = normalizeDraft(draft);
  let count = 0;

  for (const field of NUMERIC_FILTER_FIELDS) {
    if (normalizedDraft.filters[field]) {
      count += 1;
    }
  }

  if (normalizedDraft.filters.exclude_restatements) {
    count += 1;
  }
  if (normalizedDraft.filters.exclude_stale_periods) {
    count += 1;
  }
  if (normalizedDraft.filters.excluded_quality_flags.length) {
    count += 1;
  }
  if (parseTickerUniverse(normalizedDraft.tickerUniverseText).length) {
    count += 1;
  }

  return count;
}

export function areLocalScreenerDraftsEqual(left: LocalScreenerDraft, right: LocalScreenerDraft): boolean {
  return JSON.stringify(normalizeDraft(left)) === JSON.stringify(normalizeDraft(right));
}

function buildPresetId(name: string): string {
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "preset";
  return `${slug}-${Date.now()}`;
}