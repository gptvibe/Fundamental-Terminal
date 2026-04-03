export interface LocalCompareCompany {
  ticker: string;
  name: string | null;
  sector: string | null;
  addedAt: string;
}

export interface LocalCompareSnapshot {
  ticker: string;
  name?: string | null;
  sector?: string | null;
}

export const LOCAL_COMPARE_SET_STORAGE_KEY = "ft-local-compare-set";
export const LOCAL_COMPARE_SET_EVENT = "ft:local-compare-set";
export const MAX_COMPARE_TICKERS = 5;

function canUseStorage() {
  return typeof window !== "undefined";
}

function normalizeTicker(value: string): string {
  return value.trim().toUpperCase();
}

function sanitizeText(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function normalizeSnapshot(snapshot: LocalCompareSnapshot): LocalCompareSnapshot {
  return {
    ticker: normalizeTicker(snapshot.ticker),
    name: sanitizeText(snapshot.name) ?? null,
    sector: sanitizeText(snapshot.sector) ?? null,
  };
}

function normalizeCompareSet(value: unknown): LocalCompareCompany[] {
  if (!Array.isArray(value)) {
    return [];
  }

  const seen = new Set<string>();
  const items: LocalCompareCompany[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const candidate = item as Partial<LocalCompareCompany>;
    const ticker = normalizeTicker(typeof candidate.ticker === "string" ? candidate.ticker : "");
    if (!ticker || seen.has(ticker)) {
      continue;
    }
    seen.add(ticker);
    items.push({
      ticker,
      name: sanitizeText(candidate.name) ?? null,
      sector: sanitizeText(candidate.sector) ?? null,
      addedAt: typeof candidate.addedAt === "string" && candidate.addedAt ? candidate.addedAt : new Date(0).toISOString(),
    });
    if (items.length >= MAX_COMPARE_TICKERS) {
      break;
    }
  }
  return items;
}

function writeCompareSet(items: LocalCompareCompany[]): void {
  if (!canUseStorage()) {
    return;
  }

  window.localStorage.setItem(LOCAL_COMPARE_SET_STORAGE_KEY, JSON.stringify(items));
  window.dispatchEvent(new CustomEvent(LOCAL_COMPARE_SET_EVENT, { detail: items }));
}

export function readLocalCompareSet(): LocalCompareCompany[] {
  if (!canUseStorage()) {
    return [];
  }

  const raw = window.localStorage.getItem(LOCAL_COMPARE_SET_STORAGE_KEY);
  if (!raw) {
    return [];
  }

  try {
    return normalizeCompareSet(JSON.parse(raw));
  } catch {
    window.localStorage.removeItem(LOCAL_COMPARE_SET_STORAGE_KEY);
    return [];
  }
}

export function subscribeLocalCompareSet(onChange: () => void): () => void {
  if (!canUseStorage()) {
    return () => undefined;
  }

  function handleStorage(event: StorageEvent) {
    if (event.key === LOCAL_COMPARE_SET_STORAGE_KEY) {
      onChange();
    }
  }

  window.addEventListener(LOCAL_COMPARE_SET_EVENT, onChange as EventListener);
  window.addEventListener("storage", handleStorage);
  return () => {
    window.removeEventListener(LOCAL_COMPARE_SET_EVENT, onChange as EventListener);
    window.removeEventListener("storage", handleStorage);
  };
}

export function updateLocalCompareSet(updater: (current: LocalCompareCompany[]) => LocalCompareCompany[]): LocalCompareCompany[] {
  const next = normalizeCompareSet(updater(readLocalCompareSet()));
  writeCompareSet(next);
  return next;
}

export function addCompareCompanies(snapshots: LocalCompareSnapshot[]): LocalCompareCompany[] {
  return updateLocalCompareSet((current) => {
    const byTicker = new Map(current.map((item) => [item.ticker, item]));
    for (const snapshot of snapshots) {
      const normalized = normalizeSnapshot(snapshot);
      if (!normalized.ticker) {
        continue;
      }
      const existing = byTicker.get(normalized.ticker);
      byTicker.set(normalized.ticker, {
        ticker: normalized.ticker,
        name: normalized.name ?? existing?.name ?? null,
        sector: normalized.sector ?? existing?.sector ?? null,
        addedAt: existing?.addedAt ?? new Date().toISOString(),
      });
    }

    return [...byTicker.values()]
      .sort((left, right) => right.addedAt.localeCompare(left.addedAt))
      .slice(0, MAX_COMPARE_TICKERS);
  });
}

export function removeCompareCompany(ticker: string): LocalCompareCompany[] {
  const normalized = normalizeTicker(ticker);
  return updateLocalCompareSet((current) => current.filter((item) => item.ticker !== normalized));
}

export function clearCompareCompanies(): LocalCompareCompany[] {
  writeCompareSet([]);
  return [];
}

export function toggleCompareCompany(snapshot: LocalCompareSnapshot): { saved: boolean; items: LocalCompareCompany[] } {
  const normalized = normalizeSnapshot(snapshot);
  const exists = readLocalCompareSet().some((item) => item.ticker === normalized.ticker);
  const items = exists ? removeCompareCompany(normalized.ticker) : addCompareCompanies([normalized]);
  return { saved: !exists, items };
}

export function syncCompareCompanyMetadata(snapshot: LocalCompareSnapshot): LocalCompareCompany[] {
  const normalized = normalizeSnapshot(snapshot);
  return updateLocalCompareSet((current) =>
    current.map((item) =>
      item.ticker === normalized.ticker
        ? {
            ...item,
            name: normalized.name ?? item.name,
            sector: normalized.sector ?? item.sector,
          }
        : item
    )
  );
}

export function buildCompareHref(tickers: string[]): string {
  const normalized = tickers
    .map((ticker) => normalizeTicker(ticker))
    .filter(Boolean)
    .slice(0, MAX_COMPARE_TICKERS);
  const params = new URLSearchParams({ tickers: normalized.join(",") });
  return `/compare?${params.toString()}`;
}