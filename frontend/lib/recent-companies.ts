export interface RecentCompanySnapshot {
  ticker: string;
  name?: string | null;
  sector?: string | null;
  market_sector?: string | null;
  openedAt?: string | null;
}

export interface RecentCompany {
  ticker: string;
  name: string | null;
  sector: string | null;
  openedAt: string;
}

export const RECENT_COMPANIES_STORAGE_KEY = "ft-home-recent-companies";
export const RECENT_COMPANIES_EVENT = "ft:recent-companies";

const MAX_RECENT_COMPANIES = 6;

function canUseStorage() {
  return typeof window !== "undefined";
}

function sanitizeRecentCompanyText(value: string | null | undefined): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function toTimestamp(value: string | null | undefined): number {
  if (!value) {
    return 0;
  }

  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function normalizeRecentCompany(value: Partial<RecentCompanySnapshot> & { ticker?: string | null }): RecentCompany | null {
  const ticker = sanitizeRecentCompanyText(value.ticker)?.toUpperCase() ?? null;
  if (!ticker) {
    return null;
  }

  return {
    ticker,
    name: sanitizeRecentCompanyText(value.name),
    sector: sanitizeRecentCompanyText(value.sector ?? value.market_sector),
    openedAt: sanitizeRecentCompanyText(value.openedAt) ?? new Date(0).toISOString(),
  };
}

function writeRecentCompanies(companies: RecentCompany[]) {
  if (!canUseStorage()) {
    return;
  }

  window.localStorage.setItem(RECENT_COMPANIES_STORAGE_KEY, JSON.stringify(companies));
  window.dispatchEvent(new CustomEvent(RECENT_COMPANIES_EVENT, { detail: companies }));
}

export function readRecentCompanies(): RecentCompany[] {
  if (!canUseStorage()) {
    return [];
  }

  const rawValue = window.localStorage.getItem(RECENT_COMPANIES_STORAGE_KEY);
  if (!rawValue) {
    return [];
  }

  try {
    const parsed = JSON.parse(rawValue);
    if (!Array.isArray(parsed)) {
      return [];
    }

    const seen = new Set<string>();
    return parsed
      .map((item) => normalizeRecentCompany(item as Partial<RecentCompanySnapshot>))
      .filter((item): item is RecentCompany => Boolean(item))
      .filter((item) => {
        if (seen.has(item.ticker)) {
          return false;
        }

        seen.add(item.ticker);
        return true;
      })
      .sort((left, right) => toTimestamp(right.openedAt) - toTimestamp(left.openedAt))
      .slice(0, MAX_RECENT_COMPANIES);
  } catch {
    window.localStorage.removeItem(RECENT_COMPANIES_STORAGE_KEY);
    return [];
  }
}

export function recordRecentCompany(snapshot: RecentCompanySnapshot): RecentCompany[] {
  const normalizedTicker = sanitizeRecentCompanyText(snapshot.ticker)?.toUpperCase() ?? null;
  if (!normalizedTicker) {
    return readRecentCompanies();
  }

  const current = readRecentCompanies();
  const existing = current.find((item) => item.ticker === normalizedTicker) ?? null;
  const nextEntry: RecentCompany = {
    ticker: normalizedTicker,
    name: sanitizeRecentCompanyText(snapshot.name) ?? existing?.name ?? null,
    sector: sanitizeRecentCompanyText(snapshot.sector ?? snapshot.market_sector) ?? existing?.sector ?? null,
    openedAt: snapshot.openedAt ? sanitizeRecentCompanyText(snapshot.openedAt) ?? new Date().toISOString() : new Date().toISOString(),
  };
  const nextCompanies = [nextEntry, ...current.filter((item) => item.ticker !== normalizedTicker)].slice(0, MAX_RECENT_COMPANIES);

  writeRecentCompanies(nextCompanies);
  return nextCompanies;
}

export function clearRecentCompanies(): RecentCompany[] {
  if (!canUseStorage()) {
    return [];
  }

  writeRecentCompanies([]);
  return [];
}

export function subscribeRecentCompanies(onChange: () => void): () => void {
  if (!canUseStorage()) {
    return () => undefined;
  }

  function handleStorage(event: StorageEvent) {
    if (event.key === RECENT_COMPANIES_STORAGE_KEY) {
      onChange();
    }
  }

  window.addEventListener(RECENT_COMPANIES_EVENT, onChange as EventListener);
  window.addEventListener("storage", handleStorage);

  return () => {
    window.removeEventListener(RECENT_COMPANIES_EVENT, onChange as EventListener);
    window.removeEventListener("storage", handleStorage);
  };
}