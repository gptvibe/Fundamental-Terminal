export interface LocalWatchlistItem {
  ticker: string;
  name: string | null;
  sector: string | null;
  savedAt: string;
}

export interface LocalCompanyNote {
  ticker: string;
  name: string | null;
  sector: string | null;
  note: string;
  updatedAt: string;
}

import {
  buildDefaultMonitoringEntry,
  DEFAULT_WATCHLIST_VIEW_CRITERIA,
  isWatchlistMonitoringProfileKey,
  isWatchlistPrimaryFilter,
  isWatchlistSort,
  isWatchlistTriageState,
  type LocalWatchlistMonitoringEntry,
  type LocalWatchlistSavedView,
  type WatchlistSavedViewCriteria,
} from "@/lib/watchlist-monitoring";

export interface LocalUserData {
  watchlist: LocalWatchlistItem[];
  notes: Record<string, LocalCompanyNote>;
  monitoring: Record<string, LocalWatchlistMonitoringEntry>;
  savedWatchlistViews: LocalWatchlistSavedView[];
}

export interface LocalCompanySnapshot {
  ticker: string;
  name?: string | null;
  sector?: string | null;
}

export type LocalImportMode = "merge" | "replace";

export const LOCAL_USER_DATA_STORAGE_KEY = "ft-local-user-data";
export const LOCAL_USER_DATA_EVENT = "ft:local-user-data";

const EMPTY_USER_DATA: LocalUserData = {
  watchlist: [],
  notes: {},
  monitoring: {},
  savedWatchlistViews: [],
};

function normalizeTicker(value: string): string {
  return value.trim().toUpperCase();
}

function canUseStorage() {
  return typeof window !== "undefined";
}

function sanitizeText(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function sanitizeIsoString(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function normalizeCompanySnapshot(snapshot: LocalCompanySnapshot): LocalCompanySnapshot {
  return {
    ticker: normalizeTicker(snapshot.ticker),
    name: sanitizeText(snapshot.name) ?? null,
    sector: sanitizeText(snapshot.sector) ?? null
  };
}

function normalizeWatchlist(items: unknown): LocalWatchlistItem[] {
  if (!Array.isArray(items)) {
    return [];
  }

  const seen = new Set<string>();
  const normalizedItems: LocalWatchlistItem[] = [];

  for (const item of items) {
    if (!item || typeof item !== "object") {
      continue;
    }

    const candidate = item as Partial<LocalWatchlistItem>;
    const ticker = normalizeTicker(typeof candidate.ticker === "string" ? candidate.ticker : "");
    if (!ticker || seen.has(ticker)) {
      continue;
    }

    seen.add(ticker);
    normalizedItems.push({
      ticker,
      name: sanitizeText(candidate.name) ?? null,
      sector: sanitizeText(candidate.sector) ?? null,
      savedAt: typeof candidate.savedAt === "string" && candidate.savedAt ? candidate.savedAt : new Date(0).toISOString()
    });
  }

  return normalizedItems.sort((left, right) => right.savedAt.localeCompare(left.savedAt));
}

function normalizeNotes(notes: unknown): Record<string, LocalCompanyNote> {
  if (!notes || typeof notes !== "object" || Array.isArray(notes)) {
    return {};
  }

  return Object.entries(notes).reduce<Record<string, LocalCompanyNote>>((result, [rawTicker, value]) => {
    if (!value || typeof value !== "object") {
      return result;
    }

    const candidate = value as Partial<LocalCompanyNote>;
    const ticker = normalizeTicker(candidate.ticker ?? rawTicker);
    const note = typeof candidate.note === "string" ? candidate.note.trim() : "";
    if (!ticker || !note) {
      return result;
    }

    result[ticker] = {
      ticker,
      name: sanitizeText(candidate.name) ?? null,
      sector: sanitizeText(candidate.sector) ?? null,
      note,
      updatedAt: typeof candidate.updatedAt === "string" && candidate.updatedAt ? candidate.updatedAt : new Date(0).toISOString()
    };
    return result;
  }, {});
}

function normalizeMonitoring(value: unknown): Record<string, LocalWatchlistMonitoringEntry> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }

  return Object.entries(value).reduce<Record<string, LocalWatchlistMonitoringEntry>>((result, [rawTicker, rawEntry]) => {
    if (!rawEntry || typeof rawEntry !== "object") {
      return result;
    }

    const candidate = rawEntry as Partial<LocalWatchlistMonitoringEntry>;
    const ticker = normalizeTicker(candidate.ticker ?? rawTicker);
    if (!ticker) {
      return result;
    }

    result[ticker] = {
      ticker,
      triageState: isWatchlistTriageState(candidate.triageState) ? candidate.triageState : "inbox",
      profileKey: isWatchlistMonitoringProfileKey(candidate.profileKey) ? candidate.profileKey : null,
      rationale: typeof candidate.rationale === "string" ? candidate.rationale.trim() : "",
      lastReviewedAt: sanitizeIsoString(candidate.lastReviewedAt),
      nextReviewAt: sanitizeIsoString(candidate.nextReviewAt),
      snoozedUntil: sanitizeIsoString(candidate.snoozedUntil),
      holdUntil: sanitizeIsoString(candidate.holdUntil),
      updatedAt: sanitizeIsoString(candidate.updatedAt) ?? new Date(0).toISOString(),
    };
    return result;
  }, {});
}

function normalizeSavedViewCriteria(value: unknown): WatchlistSavedViewCriteria {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return DEFAULT_WATCHLIST_VIEW_CRITERIA;
  }

  const candidate = value as Partial<WatchlistSavedViewCriteria>;
  const triageStates = Array.isArray(candidate.triageStates)
    ? candidate.triageStates.filter((item): item is WatchlistSavedViewCriteria["triageStates"][number] => isWatchlistTriageState(item))
    : [];

  return {
    primaryFilter: isWatchlistPrimaryFilter(candidate.primaryFilter) ? candidate.primaryFilter : DEFAULT_WATCHLIST_VIEW_CRITERIA.primaryFilter,
    triageStates: [...new Set(triageStates)],
    sortBy: isWatchlistSort(candidate.sortBy) ? candidate.sortBy : DEFAULT_WATCHLIST_VIEW_CRITERIA.sortBy,
    searchText: typeof candidate.searchText === "string" ? candidate.searchText.trim() : "",
    profileKey: isWatchlistMonitoringProfileKey(candidate.profileKey) ? candidate.profileKey : null,
  };
}

function slugifySavedViewName(value: string): string {
  const normalized = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return normalized || "watchlist-view";
}

function normalizeSavedWatchlistViews(value: unknown): LocalWatchlistSavedView[] {
  if (!Array.isArray(value)) {
    return [];
  }

  const seen = new Set<string>();
  return value.reduce<LocalWatchlistSavedView[]>((result, rawView, index) => {
    if (!rawView || typeof rawView !== "object") {
      return result;
    }

    const candidate = rawView as Partial<LocalWatchlistSavedView>;
    const name = typeof candidate.name === "string" ? candidate.name.trim() : "";
    if (!name) {
      return result;
    }

    let id = typeof candidate.id === "string" ? candidate.id.trim() : "";
    if (!id) {
      id = `${slugifySavedViewName(name)}-${index + 1}`;
    }
    if (seen.has(id)) {
      return result;
    }
    seen.add(id);

    result.push({
      id,
      name,
      criteria: normalizeSavedViewCriteria(candidate.criteria),
      createdAt: sanitizeIsoString(candidate.createdAt) ?? new Date(0).toISOString(),
      updatedAt: sanitizeIsoString(candidate.updatedAt) ?? new Date(0).toISOString(),
    });
    return result;
  }, []);
}

function normalizeLocalUserData(value: unknown): LocalUserData {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return EMPTY_USER_DATA;
  }

  const candidate = value as Partial<LocalUserData>;
  return {
    watchlist: normalizeWatchlist(candidate.watchlist),
    notes: normalizeNotes(candidate.notes),
    monitoring: normalizeMonitoring(candidate.monitoring),
    savedWatchlistViews: normalizeSavedWatchlistViews(candidate.savedWatchlistViews),
  };
}

function writeLocalUserData(data: LocalUserData) {
  if (!canUseStorage()) {
    return;
  }

  window.localStorage.setItem(LOCAL_USER_DATA_STORAGE_KEY, JSON.stringify(data));
  window.dispatchEvent(new CustomEvent(LOCAL_USER_DATA_EVENT, { detail: data }));
}

function upsertWatchlistItem(items: LocalWatchlistItem[], snapshot: LocalCompanySnapshot): LocalWatchlistItem[] {
  const normalizedSnapshot = normalizeCompanySnapshot(snapshot);
  if (!normalizedSnapshot.ticker) {
    return items;
  }

  const existingIndex = items.findIndex((item) => item.ticker === normalizedSnapshot.ticker);
  if (existingIndex === -1) {
    return [
      {
        ticker: normalizedSnapshot.ticker,
        name: normalizedSnapshot.name ?? null,
        sector: normalizedSnapshot.sector ?? null,
        savedAt: new Date().toISOString()
      },
      ...items
    ].sort((left, right) => right.savedAt.localeCompare(left.savedAt));
  }

  const existing = items[existingIndex];
  const nextItems = [...items];
  nextItems[existingIndex] = {
    ...existing,
    name: normalizedSnapshot.name ?? existing.name,
    sector: normalizedSnapshot.sector ?? existing.sector
  };
  return nextItems;
}

export function readLocalUserData(): LocalUserData {
  if (!canUseStorage()) {
    return EMPTY_USER_DATA;
  }

  const rawValue = window.localStorage.getItem(LOCAL_USER_DATA_STORAGE_KEY);
  if (!rawValue) {
    return EMPTY_USER_DATA;
  }

  try {
    return normalizeLocalUserData(JSON.parse(rawValue));
  } catch {
    window.localStorage.removeItem(LOCAL_USER_DATA_STORAGE_KEY);
    return EMPTY_USER_DATA;
  }
}

export function subscribeLocalUserData(onChange: () => void): () => void {
  if (!canUseStorage()) {
    return () => undefined;
  }

  function handleStorage(event: StorageEvent) {
    if (event.key === LOCAL_USER_DATA_STORAGE_KEY) {
      onChange();
    }
  }

  window.addEventListener(LOCAL_USER_DATA_EVENT, onChange as EventListener);
  window.addEventListener("storage", handleStorage);
  return () => {
    window.removeEventListener(LOCAL_USER_DATA_EVENT, onChange as EventListener);
    window.removeEventListener("storage", handleStorage);
  };
}

export function updateLocalUserData(updater: (current: LocalUserData) => LocalUserData): LocalUserData {
  const nextValue = normalizeLocalUserData(updater(readLocalUserData()));
  writeLocalUserData(nextValue);
  return nextValue;
}

export function exportLocalUserData(): LocalUserData {
  return normalizeLocalUserData(readLocalUserData());
}

export function importLocalUserData(rawJson: string, options?: { mode?: LocalImportMode }): LocalUserData {
  let parsed: unknown;
  try {
    parsed = JSON.parse(rawJson);
  } catch {
    throw new Error("Import file is not valid JSON.");
  }

  const incoming = normalizeLocalUserData(parsed);
  const mode = options?.mode ?? "merge";

  const nextValue =
    mode === "replace"
      ? incoming
      : updateLocalUserData((current) => ({
          watchlist: normalizeWatchlist([...current.watchlist, ...incoming.watchlist]),
          notes: normalizeNotes({ ...current.notes, ...incoming.notes }),
          monitoring: normalizeMonitoring({ ...current.monitoring, ...incoming.monitoring }),
          savedWatchlistViews: normalizeSavedWatchlistViews([...current.savedWatchlistViews, ...incoming.savedWatchlistViews]),
        }));

  if (mode === "replace") {
    writeLocalUserData(nextValue);
  }
  return nextValue;
}

export function clearAllLocalUserData(): LocalUserData {
  writeLocalUserData(EMPTY_USER_DATA);
  return EMPTY_USER_DATA;
}

export function toggleWatchlistCompany(snapshot: LocalCompanySnapshot): { saved: boolean; data: LocalUserData } {
  const normalizedSnapshot = normalizeCompanySnapshot(snapshot);
  let saved = false;

  const data = updateLocalUserData((current) => {
    const exists = current.watchlist.some((item) => item.ticker === normalizedSnapshot.ticker);
    saved = !exists;

    return {
      ...current,
      watchlist: exists
        ? current.watchlist.filter((item) => item.ticker !== normalizedSnapshot.ticker)
        : upsertWatchlistItem(current.watchlist, normalizedSnapshot)
    };
  });

  return { saved, data };
}

export function removeWatchlistCompany(ticker: string): LocalUserData {
  const normalizedTicker = normalizeTicker(ticker);
  return updateLocalUserData((current) => ({
    ...current,
    watchlist: current.watchlist.filter((item) => item.ticker !== normalizedTicker)
  }));
}

export function saveCompanyNote(snapshot: LocalCompanySnapshot, note: string): LocalUserData {
  const normalizedSnapshot = normalizeCompanySnapshot(snapshot);
  const normalizedNote = note.trim();

  return updateLocalUserData((current) => {
    const nextNotes = { ...current.notes };
    if (!normalizedNote) {
      delete nextNotes[normalizedSnapshot.ticker];
      return {
        ...current,
        notes: nextNotes
      };
    }

    nextNotes[normalizedSnapshot.ticker] = {
      ticker: normalizedSnapshot.ticker,
      name: normalizedSnapshot.name ?? current.notes[normalizedSnapshot.ticker]?.name ?? null,
      sector: normalizedSnapshot.sector ?? current.notes[normalizedSnapshot.ticker]?.sector ?? null,
      note: normalizedNote,
      updatedAt: new Date().toISOString()
    };

    return {
      ...current,
      notes: nextNotes
    };
  });
}

export function saveWatchlistMonitoringEntry(entry: LocalWatchlistMonitoringEntry): LocalUserData {
  const normalizedTicker = normalizeTicker(entry.ticker);
  if (!normalizedTicker) {
    return readLocalUserData();
  }

  return updateLocalUserData((current) => ({
    ...current,
    monitoring: {
      ...current.monitoring,
      [normalizedTicker]: {
        ...buildDefaultMonitoringEntry(normalizedTicker),
        ...normalizeMonitoring({ [normalizedTicker]: entry })[normalizedTicker],
        ticker: normalizedTicker,
        updatedAt: new Date().toISOString(),
      },
    },
  }));
}

export function saveWatchlistSavedView(view: { id?: string; name: string; criteria: WatchlistSavedViewCriteria }): LocalUserData {
  const name = view.name.trim();
  if (!name) {
    return readLocalUserData();
  }

  return updateLocalUserData((current) => {
    const now = new Date().toISOString();
    const normalizedView: LocalWatchlistSavedView = {
      id: view.id?.trim() || `${slugifySavedViewName(name)}-${current.savedWatchlistViews.length + 1}`,
      name,
      criteria: normalizeSavedViewCriteria(view.criteria),
      createdAt: current.savedWatchlistViews.find((item) => item.id === view.id)?.createdAt ?? now,
      updatedAt: now,
    };

    const remaining = current.savedWatchlistViews.filter((item) => item.id !== normalizedView.id);
    return {
      ...current,
      savedWatchlistViews: [...remaining, normalizedView].sort((left, right) => right.updatedAt.localeCompare(left.updatedAt)),
    };
  });
}

export function deleteWatchlistSavedView(id: string): LocalUserData {
  const normalizedId = id.trim();
  if (!normalizedId) {
    return readLocalUserData();
  }

  return updateLocalUserData((current) => ({
    ...current,
    savedWatchlistViews: current.savedWatchlistViews.filter((item) => item.id !== normalizedId),
  }));
}

export function clearCompanyNote(ticker: string): LocalUserData {
  const normalizedTicker = normalizeTicker(ticker);
  return updateLocalUserData((current) => {
    const nextNotes = { ...current.notes };
    delete nextNotes[normalizedTicker];
    return {
      ...current,
      notes: nextNotes
    };
  });
}

export function syncLocalCompanyMetadata(snapshot: LocalCompanySnapshot): LocalUserData {
  const normalizedSnapshot = normalizeCompanySnapshot(snapshot);
  if (!normalizedSnapshot.ticker || (!normalizedSnapshot.name && !normalizedSnapshot.sector)) {
    return readLocalUserData();
  }

  return updateLocalUserData((current) => {
    const nextWatchlist = current.watchlist.some((item) => item.ticker === normalizedSnapshot.ticker)
      ? upsertWatchlistItem(current.watchlist, normalizedSnapshot)
      : current.watchlist;

    const existingNote = current.notes[normalizedSnapshot.ticker];
    const nextNotes = existingNote
      ? {
          ...current.notes,
          [normalizedSnapshot.ticker]: {
            ...existingNote,
            name: normalizedSnapshot.name ?? existingNote.name,
            sector: normalizedSnapshot.sector ?? existingNote.sector
          }
        }
      : current.notes;

    return {
      watchlist: nextWatchlist,
      notes: nextNotes,
      monitoring: current.monitoring,
      savedWatchlistViews: current.savedWatchlistViews,
    };
  });
}

