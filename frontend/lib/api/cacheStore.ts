import type { ApiReadCacheState, CacheEntry, PersistedCacheEntry, ReadCachePolicy } from "./types";
import { resolveReadPolicy, shouldBypassReadCache } from "./cachePolicy";

const CACHE_STORAGE_PREFIX = "ft:api-cache:v5:";
const CACHE_BROADCAST_CHANNEL = "ft:api-cache-events";
const CACHE_INVALIDATION_STORAGE_KEY = `${CACHE_STORAGE_PREFIX}invalidation`;

const MEMORY_CACHE_MAX_ENTRIES = 160;
const MEMORY_CACHE_MAX_BYTES = 8 * 1024 * 1024;
const PERSISTED_CACHE_MAX_ENTRIES = 240;
const PERSISTED_CACHE_MAX_BYTES = 32 * 1024 * 1024;
const PERSISTED_CACHE_MAX_ENTRY_BYTES = 2 * 1024 * 1024;

const IDB_DATABASE_NAME = "ft-api-cache";
const IDB_DATABASE_VERSION = 1;
const IDB_STORE_NAME = "entries";

const readCache = new Map<string, CacheEntry>();
let cacheSyncInitialized = false;
let memoryCacheApproxBytes = 0;
let broadcastChannel: BroadcastChannel | null = null;
let idbDatabasePromise: Promise<IDBDatabase | null> | null = null;

function cacheStorageKey(cacheKey: string): string {
  return `${CACHE_STORAGE_PREFIX}${cacheKey}`;
}

function estimateMemoryEntryBytes(value: unknown): number {
  if (value == null) {
    return 64;
  }

  if (typeof value === "string") {
    return Math.min(512 * 1024, Math.max(128, value.length * 2));
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return 64;
  }

  if (Array.isArray(value)) {
    return Math.min(512 * 1024, Math.max(256, value.length * 64));
  }

  if (typeof value === "object") {
    return 2_048;
  }

  return 256;
}

function estimateSerializedBytes(value: unknown): number | null {
  try {
    const serialized = JSON.stringify(value);
    if (serialized == null) {
      return null;
    }

    if (typeof TextEncoder !== "undefined") {
      return new TextEncoder().encode(serialized).length;
    }

    return serialized.length * 2;
  } catch {
    return null;
  }
}

function upsertMemoryCacheEntry(cacheKey: string, entry: CacheEntry): void {
  const previous = readCache.get(cacheKey);
  if (previous) {
    memoryCacheApproxBytes -= previous.approxSizeBytes;
  }

  readCache.set(cacheKey, entry);
  memoryCacheApproxBytes += entry.approxSizeBytes;
  evictMemoryCacheIfNeeded();
}

export function deleteMemoryCacheEntry(cacheKey: string): void {
  const previous = readCache.get(cacheKey);
  if (!previous) {
    return;
  }

  memoryCacheApproxBytes -= previous.approxSizeBytes;
  if (memoryCacheApproxBytes < 0) {
    memoryCacheApproxBytes = 0;
  }
  readCache.delete(cacheKey);
}

function evictMemoryCacheIfNeeded(): void {
  if (readCache.size <= MEMORY_CACHE_MAX_ENTRIES && memoryCacheApproxBytes <= MEMORY_CACHE_MAX_BYTES) {
    return;
  }

  const entriesByAge = [...readCache.entries()].sort((a, b) => a[1].lastAccessedAt - b[1].lastAccessedAt);
  for (const [cacheKey] of entriesByAge) {
    if (readCache.size <= MEMORY_CACHE_MAX_ENTRIES && memoryCacheApproxBytes <= MEMORY_CACHE_MAX_BYTES) {
      break;
    }
    deleteMemoryCacheEntry(cacheKey);
  }
}

function requestToPromise<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("IndexedDB request failed"));
  });
}

function openIndexedDb(): Promise<IDBDatabase | null> {
  if (typeof window === "undefined" || typeof indexedDB === "undefined") {
    return Promise.resolve(null);
  }

  if (idbDatabasePromise) {
    return idbDatabasePromise;
  }

  idbDatabasePromise = new Promise((resolve) => {
    try {
      const request = indexedDB.open(IDB_DATABASE_NAME, IDB_DATABASE_VERSION);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(IDB_STORE_NAME)) {
          db.createObjectStore(IDB_STORE_NAME, { keyPath: "cacheKey" });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => resolve(null);
      request.onblocked = () => resolve(null);
    } catch {
      resolve(null);
    }
  });

  return idbDatabasePromise;
}

async function withIndexedDbStore<T>(mode: IDBTransactionMode, operation: (store: IDBObjectStore) => Promise<T>): Promise<T | null> {
  const db = await openIndexedDb();
  if (!db) {
    return null;
  }

  try {
    const transaction = db.transaction(IDB_STORE_NAME, mode);
    const store = transaction.objectStore(IDB_STORE_NAME);
    const result = await operation(store);

    await new Promise<void>((resolve, reject) => {
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error ?? new Error("IndexedDB transaction failed"));
      transaction.onabort = () => reject(transaction.error ?? new Error("IndexedDB transaction aborted"));
    });

    return result;
  } catch {
    return null;
  }
}

async function readPersistentCache(cacheKey: string): Promise<CacheEntry | null> {
  const persisted = await withIndexedDbStore("readwrite", async (store) => {
    const raw = await requestToPromise(store.get(cacheStorageKey(cacheKey)) as IDBRequest<PersistedCacheEntry | undefined>);
    if (!raw) {
      return null;
    }

    raw.lastAccessedAt = Date.now();
    store.put(raw);
    return raw;
  });

  if (!persisted || typeof persisted.updatedAt !== "number") {
    return null;
  }

  return {
    data: persisted.data,
    updatedAt: persisted.updatedAt,
    approxSizeBytes: typeof persisted.approxSizeBytes === "number" && persisted.approxSizeBytes > 0 ? persisted.approxSizeBytes : estimateMemoryEntryBytes(persisted.data),
    lastAccessedAt: typeof persisted.lastAccessedAt === "number" && persisted.lastAccessedAt > 0 ? persisted.lastAccessedAt : Date.now(),
  };
}

async function writePersistentCache(cacheKey: string, entry: CacheEntry): Promise<void> {
  const approxSizeBytes = estimateSerializedBytes(entry.data);
  if (approxSizeBytes == null || approxSizeBytes > PERSISTED_CACHE_MAX_ENTRY_BYTES) {
    await removePersistentCache(cacheKey);
    return;
  }

  await withIndexedDbStore("readwrite", async (store) => {
    const persisted: PersistedCacheEntry = {
      cacheKey: cacheStorageKey(cacheKey),
      data: entry.data,
      updatedAt: entry.updatedAt,
      approxSizeBytes,
      lastAccessedAt: entry.lastAccessedAt,
    };
    store.put(persisted);
    return null;
  });

  await evictPersistentCacheIfNeeded();
}

async function removePersistentCache(cacheKey: string): Promise<void> {
  await withIndexedDbStore("readwrite", async (store) => {
    store.delete(cacheStorageKey(cacheKey));
    return null;
  });
}

export async function removePersistentCacheByPrefix(prefix: string): Promise<void> {
  await withIndexedDbStore("readwrite", async (store) => {
    if (!prefix) {
      store.clear();
      return null;
    }

    const range = IDBKeyRange.bound(cacheStorageKey(prefix), cacheStorageKey(`${prefix}\uffff`));
    await new Promise<void>((resolve, reject) => {
      const request = store.openCursor(range);
      request.onsuccess = () => {
        const cursor = request.result;
        if (!cursor) {
          resolve();
          return;
        }
        cursor.delete();
        cursor.continue();
      };
      request.onerror = () => reject(request.error ?? new Error("IndexedDB cursor failed"));
    });
    return null;
  });
}

async function evictPersistentCacheIfNeeded(): Promise<void> {
  await withIndexedDbStore("readwrite", async (store) => {
    let entryCount = 0;
    let totalBytes = 0;
    const entries: Array<{ key: string; approxSizeBytes: number; lastAccessedAt: number }> = [];

    await new Promise<void>((resolve, reject) => {
      const request = store.openCursor();
      request.onsuccess = () => {
        const cursor = request.result;
        if (!cursor) {
          resolve();
          return;
        }

        const value = cursor.value as PersistedCacheEntry;
        const approxSizeBytes = typeof value?.approxSizeBytes === "number" && value.approxSizeBytes > 0 ? value.approxSizeBytes : 0;
        const lastAccessedAt = typeof value?.lastAccessedAt === "number" && value.lastAccessedAt > 0 ? value.lastAccessedAt : 0;
        entryCount += 1;
        totalBytes += approxSizeBytes;
        entries.push({ key: String(cursor.key), approxSizeBytes, lastAccessedAt });
        cursor.continue();
      };
      request.onerror = () => reject(request.error ?? new Error("IndexedDB cursor failed"));
    });

    if (entryCount <= PERSISTED_CACHE_MAX_ENTRIES && totalBytes <= PERSISTED_CACHE_MAX_BYTES) {
      return null;
    }

    const sorted = entries.sort((a, b) => a.lastAccessedAt - b.lastAccessedAt);
    let remainingCount = entryCount;
    let remainingBytes = totalBytes;
    for (const entry of sorted) {
      if (remainingCount <= PERSISTED_CACHE_MAX_ENTRIES && remainingBytes <= PERSISTED_CACHE_MAX_BYTES) {
        break;
      }
      store.delete(entry.key);
      remainingCount -= 1;
      remainingBytes -= entry.approxSizeBytes;
    }

    return null;
  });
}

function setupCrossTabCacheSync(): void {
  if (cacheSyncInitialized || typeof window === "undefined") {
    return;
  }

  cacheSyncInitialized = true;
  window.addEventListener("storage", (event) => {
    if (event.key !== CACHE_INVALIDATION_STORAGE_KEY || !event.newValue) {
      return;
    }

    try {
      const parsed = JSON.parse(event.newValue) as { prefix?: string };
      invalidateApiReadCache(typeof parsed.prefix === "string" ? parsed.prefix : "", { emitCrossTab: false });
    } catch {
      // Ignore malformed external invalidation metadata.
    }
  });

  if (typeof BroadcastChannel !== "undefined") {
    broadcastChannel = new BroadcastChannel(CACHE_BROADCAST_CHANNEL);
    broadcastChannel.onmessage = (event: MessageEvent<{ type: "invalidate"; prefix: string }>) => {
      const payload = event.data;
      if (payload?.type !== "invalidate") {
        return;
      }
      invalidateApiReadCache(payload.prefix, { emitCrossTab: false });
    };
  }
}

function emitInvalidation(prefix: string): void {
  if (typeof window === "undefined") {
    return;
  }

  if (broadcastChannel) {
    broadcastChannel.postMessage({ type: "invalidate", prefix });
  }

  try {
    window.localStorage.setItem(CACHE_INVALIDATION_STORAGE_KEY, JSON.stringify({ prefix, ts: Date.now() }));
  } catch {
    // Ignore metadata storage errors.
  }
}

// ---------------------------------------------------------------------------
// Payload compatibility guards
// ---------------------------------------------------------------------------

function isRecord(value: unknown): value is Record<string, unknown> {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

function isFinancialsResponseLike(value: unknown): boolean {
  if (!isRecord(value)) {
    return false;
  }

  return Array.isArray(value.financials) && Array.isArray(value.price_history) && isRecord(value.refresh);
}

function isOverviewResponseLike(value: unknown): boolean {
  if (!isRecord(value)) {
    return false;
  }

  return isRecord(value.financials) && isResearchBriefResponseLike(value.brief);
}

function isWorkspaceBootstrapResponseLike(value: unknown): boolean {
  if (!isRecord(value)) {
    return false;
  }

  return (
    (value.company == null || isRecord(value.company)) &&
    isFinancialsResponseLike(value.financials) &&
    ("brief" in value) &&
    ("earnings_summary" in value) &&
    ("insider_trades" in value) &&
    ("institutional_holdings" in value) &&
    isRecord(value.errors)
  );
}

function isResearchBriefResponseLike(value: unknown): boolean {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.schema_version === "string" &&
    typeof value.generated_at === "string" &&
    isRecord(value.refresh) &&
    typeof value.build_state === "string" &&
    typeof value.build_status === "string" &&
    Array.isArray(value.available_sections) &&
    Array.isArray(value.section_statuses) &&
    Array.isArray(value.filing_timeline) &&
    Array.isArray(value.stale_summary_cards) &&
    isRecord(value.snapshot) &&
    isRecord(value.what_changed) &&
    isRecord(value.business_quality) &&
    isRecord(value.capital_and_risk) &&
    isRecord(value.valuation) &&
    isRecord(value.monitor)
  );
}

function isMissingFinancialsPlaceholderPayload(value: unknown): boolean {
  if (!isRecord(value)) {
    return false;
  }

  const noCoverage = hasNoFinancialCoverage(value);
  if (!noCoverage) {
    return false;
  }

  if (payloadTreeHasCompanyMissingMarker(value)) {
    return true;
  }

  return hasMissingOrPlaceholderCompany(value.company);
}

function isMissingResearchBriefPlaceholderPayload(value: unknown): boolean {
  if (!isRecord(value)) {
    return false;
  }

  const noAvailableSections = Array.isArray(value.available_sections) && value.available_sections.length === 0;
  const noTimeline = Array.isArray(value.filing_timeline) && value.filing_timeline.length === 0;
  const noSummaryCards = Array.isArray(value.stale_summary_cards) && value.stale_summary_cards.length === 0;
  const buildState = typeof value.build_state === "string" ? value.build_state : null;
  if (!noAvailableSections || !noTimeline || !noSummaryCards || buildState === "ready") {
    return false;
  }

  if (payloadTreeHasCompanyMissingMarker(value)) {
    return true;
  }

  return hasMissingOrPlaceholderCompany(value.company);
}

function isMissingOverviewPlaceholderPayload(value: unknown): boolean {
  if (!isRecord(value)) {
    return false;
  }

  return (
    isMissingFinancialsPlaceholderPayload(value.financials) ||
    (value.brief != null && isMissingResearchBriefPlaceholderPayload(value.brief))
  );
}

function isMissingWorkspaceBootstrapPlaceholderPayload(value: unknown): boolean {
  if (!isRecord(value)) {
    return false;
  }

  if (
    isMissingFinancialsPlaceholderPayload(value.financials) ||
    (value.brief != null && isMissingResearchBriefPlaceholderPayload(value.brief))
  ) {
    return true;
  }

  if (value.brief != null) {
    return false;
  }

  return isRecord(value.financials) && hasNoFinancialCoverage(value.financials) && hasMissingOrPlaceholderCompany(value.company);
}

function hasNoFinancialCoverage(value: Record<string, unknown>): boolean {
  const noFinancialHistory = Array.isArray(value.financials) && value.financials.length === 0;
  const noPriceHistory = Array.isArray(value.price_history) && value.price_history.length === 0;
  return noFinancialHistory && noPriceHistory;
}

function hasMissingOrPlaceholderCompany(value: unknown): boolean {
  return value == null || (isRecord(value) && value.cache_state === "missing");
}

function payloadTreeHasCompanyMissingMarker(value: unknown, seen = new WeakSet<object>()): boolean {
  if (value == null || typeof value !== "object") {
    return false;
  }

  if (seen.has(value)) {
    return false;
  }
  seen.add(value);

  if (Array.isArray(value)) {
    return value.some((item) => payloadTreeHasCompanyMissingMarker(item, seen));
  }

  const record = value as Record<string, unknown>;
  if (record.company_missing === true) {
    return true;
  }

  if (isRecord(record.refresh) && record.refresh.reason === "missing") {
    return true;
  }

  return Object.values(record).some((entry) => payloadTreeHasCompanyMissingMarker(entry, seen));
}

export function isCompatibleCachedPayload(path: string, data: unknown): boolean {
  if (/^\/companies\/[^/]+\/financials(?:\?|$)/.test(path)) {
    return isFinancialsResponseLike(data) && !isMissingFinancialsPlaceholderPayload(data);
  }

  if (/^\/companies\/[^/]+\/brief(?:\?|$)/.test(path)) {
    return isResearchBriefResponseLike(data) && !isMissingResearchBriefPlaceholderPayload(data);
  }

  if (/^\/companies\/[^/]+\/overview(?:\?|$)/.test(path)) {
    return isOverviewResponseLike(data) && !isMissingOverviewPlaceholderPayload(data);
  }

  if (/^\/companies\/[^/]+\/workspace-bootstrap(?:\?|$)/.test(path)) {
    return isWorkspaceBootstrapResponseLike(data) && !isMissingWorkspaceBootstrapPlaceholderPayload(data);
  }

  return true;
}

// ---------------------------------------------------------------------------
// Public cache API
// ---------------------------------------------------------------------------

export async function readCachedValue<T>(cacheKey: string, path: string, policyOverride?: ReadCachePolicy): Promise<{
  data: T;
  stale: boolean;
  cacheSource: "memory-cache" | "indexeddb-cache";
  policy: ReadCachePolicy;
  payloadBytes: number | null;
} | null> {
  setupCrossTabCacheSync();
  const now = Date.now();
  const policy = policyOverride ?? resolveReadPolicy(path);
  const inMemory = readCache.get(cacheKey);
  const cacheSource: "memory-cache" | "indexeddb-cache" = inMemory ? "memory-cache" : "indexeddb-cache";
  const entry = inMemory ?? (await readPersistentCache(cacheKey));
  if (!entry) {
    return null;
  }

  if (!inMemory) {
    upsertMemoryCacheEntry(cacheKey, entry);
  } else {
    inMemory.lastAccessedAt = now;
  }

  if (!isCompatibleCachedPayload(path, entry.data)) {
    deleteMemoryCacheEntry(cacheKey);
    void removePersistentCache(cacheKey);
    return null;
  }

  if (now - entry.updatedAt > policy.staleMs) {
    deleteMemoryCacheEntry(cacheKey);
    void removePersistentCache(cacheKey);
    return null;
  }

  entry.lastAccessedAt = now;
  if (!inMemory) {
    void writePersistentCache(cacheKey, entry);
  }

  return {
    data: entry.data as T,
    stale: now - entry.updatedAt > policy.ttlMs,
    cacheSource,
    policy,
    payloadBytes: entry.approxSizeBytes,
  };
}

export function cacheValue(cacheKey: string, data: unknown): void {
  const now = Date.now();
  const entry: CacheEntry = {
    data,
    updatedAt: now,
    approxSizeBytes: estimateMemoryEntryBytes(data),
    lastAccessedAt: now,
  };
  upsertMemoryCacheEntry(cacheKey, entry);
  queueMicrotask(() => {
    void writePersistentCache(cacheKey, entry);
  });
}

export function shareReadCacheValue(cacheKey: string, sourceData: unknown): void {
  cacheValue(cacheKey, sourceData);
}

export function invalidateApiReadCache(prefix = "", options?: { emitCrossTab?: boolean }): void {
  for (const key of [...readCache.keys()]) {
    if (!prefix || key.startsWith(prefix)) {
      deleteMemoryCacheEntry(key);
    }
  }

  void removePersistentCacheByPrefix(prefix);

  if (options?.emitCrossTab !== false) {
    emitInvalidation(prefix);
  }
}

export function invalidateApiReadCacheForTicker(ticker: string): void {
  const normalized = encodeURIComponent(ticker.trim().toUpperCase());
  invalidateApiReadCache(`/companies/${normalized}/`);
}

export async function getApiReadCacheState(path: string): Promise<ApiReadCacheState> {
  if (shouldBypassReadCache(path)) {
    return "missing";
  }

  const cached = await readCachedValue<unknown>(path, path);
  if (!cached) {
    return "missing";
  }

  return cached.stale ? "stale" : "fresh";
}
