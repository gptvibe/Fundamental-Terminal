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

export interface LocalUserData {
  watchlist: LocalWatchlistItem[];
  notes: Record<string, LocalCompanyNote>;
}

export interface LocalCompanySnapshot {
  ticker: string;
  name?: string | null;
  sector?: string | null;
}

export const LOCAL_USER_DATA_STORAGE_KEY = "ft-local-user-data";
export const LOCAL_USER_DATA_EVENT = "ft:local-user-data";

const EMPTY_USER_DATA: LocalUserData = {
  watchlist: [],
  notes: {}
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

function normalizeLocalUserData(value: unknown): LocalUserData {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return EMPTY_USER_DATA;
  }

  const candidate = value as Partial<LocalUserData>;
  return {
    watchlist: normalizeWatchlist(candidate.watchlist),
    notes: normalizeNotes(candidate.notes)
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
      notes: nextNotes
    };
  });
}

