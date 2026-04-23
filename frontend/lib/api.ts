import {
  CompanyActivityFeedResponse,
  CompanyActivityOverviewResponse,
  CompanyAlertsResponse,
  CompanyCommentLettersResponse,
  CompanyCapitalRaisesResponse,
  CompanyCompareResponse,
  CompanyCapitalMarketsSummaryResponse,
  CompanyCapitalStructureResponse,
  CompanyChartsForecastAccuracyResponse,
  CompanyChartsDashboardResponse,
  CompanyChartsWhatIfRequest,
  CompanyEquityClaimRiskResponse,
  CompanyChangesSinceLastFilingResponse,
  CompanyEarningsResponse,
  CompanyEarningsSummaryResponse,
  CompanyEarningsWorkspaceResponse,
  CompanyExecutiveCompensationResponse,
  CompanyDerivedMetricsResponse,
  CompanyDerivedMetricsSummaryResponse,
  CompanyFinancialsResponse,
  CompanyFinancialRestatementsResponse,
  CompanySegmentHistoryResponse,
  CompanyBeneficialOwnershipResponse,
  CompanyBeneficialOwnershipSummaryResponse,
  CompanyEventsResponse,
  CompanyFilingEventsSummaryResponse,
  CompanyFilingsResponse,
  CompanyFilingInsightsResponse,
  CompanyForm144Response,
  CompanyGovernanceResponse,
  CompanyGovernanceSummaryResponse,
  CompanyInsiderTradesResponse,
  CompanyInstitutionalHoldingsResponse,
  CompanyInstitutionalHoldingsSummaryResponse,
  ModelEvaluationResponse,
  CompanyModelsResponse,
  CompanyOilScenarioResponse,
  CompanyMarketContextResponse,
  CompanyResearchBriefResponse,
  CompanySectorContextResponse,
  CompanyMetricsTimeseriesResponse,
  CompanyOverviewResponse,
  CompanyWorkspaceBootstrapResponse,
  CompanyResolutionResponse,
  CompanyPeersResponse,
  CompanySearchResponse,
  CacheMetricsResponse,
  OfficialScreenerMetadataResponse,
  OfficialScreenerSearchRequest,
  OfficialScreenerSearchResponse,
  SourceRegistryResponse,
  WatchlistCalendarResponse,
  WatchlistSummaryResponse,
  FinancialHistoryPoint,
  RefreshQueuedResponse
} from "@/lib/types";
import {
  beginPerformanceAuditNetworkRequest,
  endPerformanceAuditNetworkRequest,
  getCurrentPerformanceAuditContext,
  isPerformanceAuditEnabled,
  recordPerformanceAuditRequest,
  type PerformanceAuditContext,
  type PerformanceAuditCacheDisposition,
} from "@/lib/performance-audit";

const API_PREFIX = "/backend/api";

type ReadCachePolicy = {
  ttlMs: number;
  staleMs: number;
};

type CacheEntry = {
  data: unknown;
  updatedAt: number;
  approxSizeBytes: number;
  lastAccessedAt: number;
};

const DEFAULT_READ_POLICY: ReadCachePolicy = {
  ttlMs: 45_000,
  staleMs: 180_000,
};

const READ_POLICY_BY_PATH: Array<{ pattern: RegExp; policy: ReadCachePolicy }> = [
  { pattern: /^\/companies\/search\?/, policy: { ttlMs: 20_000, staleMs: 90_000 } },
  { pattern: /^\/screener\/filters(?:\?|$)/, policy: { ttlMs: 300_000, staleMs: 900_000 } },
  { pattern: /^\/companies\/[^/]+\/financials(?:\?|$)/, policy: { ttlMs: 30_000, staleMs: 120_000 } },
  { pattern: /^\/companies\/[^/]+\/overview(?:\?|$)/, policy: { ttlMs: 30_000, staleMs: 120_000 } },
  { pattern: /^\/companies\/[^/]+\/workspace-bootstrap(?:\?|$)/, policy: { ttlMs: 30_000, staleMs: 120_000 } },
  { pattern: /^\/companies\/[^/]+\/segment-history(?:\?|$)/, policy: { ttlMs: 30_000, staleMs: 120_000 } },
  { pattern: /^\/companies\/[^/]+\/capital-structure(?:\?|$)/, policy: { ttlMs: 45_000, staleMs: 180_000 } },
  { pattern: /^\/companies\/[^/]+\/charts(?:\?|$)/, policy: { ttlMs: 45_000, staleMs: 180_000 } },
  { pattern: /^\/companies\/[^/]+\/brief(?:\?|$)/, policy: { ttlMs: 45_000, staleMs: 180_000 } },
  { pattern: /^\/companies\/[^/]+\/earnings\/summary(?:\?|$)/, policy: { ttlMs: 30_000, staleMs: 120_000 } },
  { pattern: /^\/companies\/[^/]+\/models(?:\?|$)/, policy: { ttlMs: 45_000, staleMs: 180_000 } },
  { pattern: /^\/companies\/[^/]+\/oil-scenario(?:\?|$)/, policy: { ttlMs: 45_000, staleMs: 180_000 } },
  { pattern: /^\/companies\/[^/]+\/oil-scenario-overlay(?:\?|$)/, policy: { ttlMs: 45_000, staleMs: 180_000 } },
  { pattern: /^\/model-evaluations\/latest(?:\?|$)/, policy: { ttlMs: 60_000, staleMs: 240_000 } },
  { pattern: /^\/companies\/[^/]+\/peers(?:\?|$)/, policy: { ttlMs: 45_000, staleMs: 180_000 } },
  { pattern: /^\/companies\/[^/]+\/sector-context(?:\?|$)/, policy: { ttlMs: 45_000, staleMs: 180_000 } },
  { pattern: /^\/companies\/[^/]+\/metrics(?:\?|$)/, policy: { ttlMs: 60_000, staleMs: 180_000 } },
  { pattern: /^\/companies\/[^/]+\/metrics-timeseries(?:\?|$)/, policy: { ttlMs: 60_000, staleMs: 180_000 } },
  { pattern: /^\/market-context(?:\?|$)/, policy: { ttlMs: 300_000, staleMs: 900_000 } },
  { pattern: /^\/source-registry(?:\?|$)/, policy: { ttlMs: 300_000, staleMs: 900_000 } },
  { pattern: /^\/watchlist\/summary(?:\?|$)/, policy: { ttlMs: 30_000, staleMs: 120_000 } },
];

const CACHE_STORAGE_PREFIX = "ft:api-cache:v4:";
const CACHE_BROADCAST_CHANNEL = "ft:api-cache-events";
const CACHE_INVALIDATION_STORAGE_KEY = `${CACHE_STORAGE_PREFIX}invalidation`;
const AUDIT_RECORDED_ERROR = Symbol("auditRecordedError");

const MEMORY_CACHE_MAX_ENTRIES = 160;
const MEMORY_CACHE_MAX_BYTES = 8 * 1024 * 1024;
const PERSISTED_CACHE_MAX_ENTRIES = 240;
const PERSISTED_CACHE_MAX_BYTES = 32 * 1024 * 1024;
const PERSISTED_CACHE_MAX_ENTRY_BYTES = 2 * 1024 * 1024;

const IDB_DATABASE_NAME = "ft-api-cache";
const IDB_DATABASE_VERSION = 1;
const IDB_STORE_NAME = "entries";

type PersistedCacheEntry = {
  cacheKey: string;
  data: unknown;
  updatedAt: number;
  approxSizeBytes: number;
  lastAccessedAt: number;
};

const readCache = new Map<string, CacheEntry>();
const inflightRequests = new Map<string, Promise<unknown>>();
let cacheSyncInitialized = false;
let memoryCacheApproxBytes = 0;
let broadcastChannel: BroadcastChannel | null = null;
let idbDatabasePromise: Promise<IDBDatabase | null> | null = null;

function resolveReadPolicy(path: string): ReadCachePolicy {
  return READ_POLICY_BY_PATH.find((entry) => entry.pattern.test(path))?.policy ?? DEFAULT_READ_POLICY;
}

function isReadRequest(init?: RequestInit): boolean {
  return !init?.method || init.method.toUpperCase() === "GET";
}

function shouldBypassReadCache(path: string): boolean {
  if (path.includes("/refresh")) {
    return true;
  }

  const queryIndex = path.indexOf("?");
  if (queryIndex < 0) {
    return false;
  }

  const params = new URLSearchParams(path.slice(queryIndex + 1));
  return params.get("refresh") === "true";
}

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

function deleteMemoryCacheEntry(cacheKey: string): void {
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

async function removePersistentCacheByPrefix(prefix: string): Promise<void> {
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

async function readCachedValue<T>(cacheKey: string, path: string): Promise<{ data: T; stale: boolean } | null> {
  setupCrossTabCacheSync();
  const now = Date.now();
  const policy = resolveReadPolicy(path);
  const inMemory = readCache.get(cacheKey);
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
  };
}

function cacheValue(cacheKey: string, data: unknown): void {
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

function shareReadCacheValue(cacheKey: string, sourceData: unknown): void {
  cacheValue(cacheKey, sourceData);
}

function isCompatibleCachedPayload(path: string, data: unknown): boolean {
  if (/^\/companies\/[^/]+\/brief(?:\?|$)/.test(path)) {
    return isResearchBriefResponseLike(data);
  }

  if (/^\/companies\/[^/]+\/overview(?:\?|$)/.test(path)) {
    return isOverviewResponseLike(data);
  }

  return true;
}

function isOverviewResponseLike(value: unknown): boolean {
  if (!isRecord(value)) {
    return false;
  }

  return isRecord(value.financials) && isResearchBriefResponseLike(value.brief);
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

function withApiPrefix(path: string): string {
  return `${API_PREFIX}${path}`;
}

function requestKeyForPath(path: string): string {
  return withApiPrefix(path);
}

async function fetchAndParse<T>(path: string, init?: RequestInit & { signal?: AbortSignal }): Promise<T> {
  return fetchAndParseWithAudit(path, init, {
    cacheDisposition: "network",
    backgroundRevalidate: false,
    context: getCurrentPerformanceAuditContext(),
  });
}

async function fetchJson<T>(path: string, init?: RequestInit & { signal?: AbortSignal }): Promise<T> {
  const readRequest = isReadRequest(init);
  const auditContext = getCurrentPerformanceAuditContext();
  if (!readRequest) {
    return fetchAndParseWithAudit<T>(path, { ...init, cache: "no-store" }, {
      cacheDisposition: "cache-bypass",
      backgroundRevalidate: false,
      context: auditContext,
    });
  }

  if (shouldBypassReadCache(path)) {
    return fetchAndParseWithAudit<T>(path, { ...init, cache: "no-store" }, {
      cacheDisposition: "cache-bypass",
      backgroundRevalidate: false,
      context: auditContext,
    });
  }

  const cacheKey = path;
  const requestKey = requestKeyForPath(path);
  const cached = await readCachedValue<T>(cacheKey, path);
  if (cached && !cached.stale) {
    recordCachedAudit(path, "GET", "fresh-cache-hit", auditContext);
    return cached.data;
  }

  const currentInflight = inflightRequests.get(requestKey) as Promise<T> | undefined;
  if (currentInflight) {
    recordCachedAudit(path, "GET", "inflight-dedupe", auditContext);
    return currentInflight;
  }

  if (cached?.stale) {
    recordCachedAudit(path, "GET", "stale-cache-hit", auditContext);
    void revalidateRead(path, cacheKey, init, {
      cacheDisposition: "network",
      backgroundRevalidate: true,
      context: auditContext,
    }).catch(() => {
      // Preserve stale serving behavior; background failures should not escape as unhandled rejections.
    });
    return cached.data;
  }

  return revalidateRead(path, cacheKey, init, {
    cacheDisposition: "network",
    backgroundRevalidate: false,
    context: auditContext,
  });
}

async function revalidateRead<T>(
  path: string,
  cacheKey: string,
  init?: RequestInit & { signal?: AbortSignal },
  audit?: {
    cacheDisposition: PerformanceAuditCacheDisposition;
    backgroundRevalidate: boolean;
    context: PerformanceAuditContext | null;
  }
): Promise<T> {
  const request = fetchAndParseWithAudit<T>(path, { ...init, cache: "no-store" }, audit)
    .then((payload) => {
      cacheValue(cacheKey, payload);
      return payload;
    })
    .finally(() => {
      inflightRequests.delete(requestKeyForPath(path));
    });

  inflightRequests.set(requestKeyForPath(path), request);
  return request;
}

async function fetchAndParseWithAudit<T>(
  path: string,
  init: (RequestInit & { signal?: AbortSignal }) | undefined,
  audit:
    | {
        cacheDisposition: PerformanceAuditCacheDisposition;
        backgroundRevalidate: boolean;
        context: PerformanceAuditContext | null;
      }
    | undefined
): Promise<T> {
  const auditEnabled = isPerformanceAuditEnabled();
  const startedAt = new Date().toISOString();
  const startedPerf = auditEnabled ? performance.now() : 0;
  const method = init?.method?.toUpperCase() ?? "GET";

  if (auditEnabled) {
    beginPerformanceAuditNetworkRequest();
  }

  try {
    try {
      const response = await fetch(withApiPrefix(path), {
        ...init,
        headers: {
          "Content-Type": "application/json",
          ...(init?.headers ?? {})
        },
        cache: init?.cache,
        signal: init?.signal
      });

      const responseBytes = auditEnabled ? resolveResponseBytes(response) : null;
      const durationMs = auditEnabled ? performance.now() - startedPerf : 0;

      if (!response.ok) {
        const requestError = new Error(`API request failed: ${response.status} ${response.statusText}`) as Error & { [AUDIT_RECORDED_ERROR]?: boolean };
        requestError[AUDIT_RECORDED_ERROR] = true;
        recordPerformanceAuditRequest({
          context: audit?.context ?? null,
          startedAt,
          method,
          path,
          cacheDisposition: audit?.cacheDisposition ?? "network",
          networkRequest: true,
          backgroundRevalidate: audit?.backgroundRevalidate ?? false,
          statusCode: response.status,
          durationMs,
          responseBytes,
          error: requestError.message,
        });
        throw requestError;
      }

      const payload = await parseJsonResponse<T>(response);

      if (auditEnabled) {
        recordPerformanceAuditRequest({
          context: audit?.context ?? null,
          startedAt,
          method,
          path,
          cacheDisposition: audit?.cacheDisposition ?? "network",
          networkRequest: true,
          backgroundRevalidate: audit?.backgroundRevalidate ?? false,
          statusCode: response.status,
          durationMs,
          responseBytes,
          error: null,
        });
      }

      return payload;
    } catch (error) {
      const isAbortError = typeof DOMException !== "undefined" && error instanceof DOMException && error.name === "AbortError";
      const isAborted = init?.signal?.aborted || isAbortError;
      const alreadyRecorded = typeof error === "object" && error !== null && AUDIT_RECORDED_ERROR in error;
      if (auditEnabled && !alreadyRecorded) {
        recordPerformanceAuditRequest({
          context: audit?.context ?? null,
          startedAt,
          method,
          path,
          cacheDisposition: audit?.cacheDisposition ?? "network",
          networkRequest: true,
          backgroundRevalidate: audit?.backgroundRevalidate ?? false,
          statusCode: null,
          durationMs: performance.now() - startedPerf,
          responseBytes: null,
          error: isAborted ? "aborted" : (error instanceof Error ? error.message : String(error)),
        });
      }
      throw error;
    }
  } finally {
    if (auditEnabled) {
      endPerformanceAuditNetworkRequest();
    }
  }
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  if (response.status === 204 || response.status === 205 || response.status === 304) {
    return null as T;
  }

  const responseBytes = resolveResponseBytes(response);
  if (responseBytes === 0) {
    return null as T;
  }

  return (await response.json()) as T;
}

function resolveResponseBytes(response: Response): number | null {
  const headerValue = response.headers?.get("content-length") ?? null;
  if (!headerValue) {
    return null;
  }

  const parsed = Number.parseInt(headerValue, 10);
  if (!Number.isFinite(parsed) || parsed < 0) {
    return null;
  }

  return parsed;
}

function recordCachedAudit(
  path: string,
  method: string,
  cacheDisposition: PerformanceAuditCacheDisposition,
  context: PerformanceAuditContext | null
): void {
  if (!isPerformanceAuditEnabled()) {
    return;
  }

  recordPerformanceAuditRequest({
    context,
    method,
    path,
    cacheDisposition,
    networkRequest: false,
    backgroundRevalidate: false,
    statusCode: null,
    durationMs: 0,
    responseBytes: null,
    error: null,
  });
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

export async function __resetApiClientCacheForTests(): Promise<void> {
  invalidateApiReadCache("", { emitCrossTab: false });
  inflightRequests.clear();
  await removePersistentCacheByPrefix("");
}

export function searchCompanies(
  query: string,
  options?: { refresh?: boolean; signal?: AbortSignal }
): Promise<CompanySearchResponse> {
  const params = new URLSearchParams({ query });
  params.set("refresh", String(options?.refresh ?? true));
  return fetchJson(`/companies/search?${params.toString()}`, { signal: options?.signal });
}

export function resolveCompanyIdentifier(query: string): Promise<CompanyResolutionResponse> {
  return fetchJson(`/companies/resolve?query=${encodeURIComponent(query)}`);
}

export function getOfficialScreenerMetadata(): Promise<OfficialScreenerMetadataResponse> {
  return fetchJson("/screener/filters");
}

export function searchOfficialScreener(
  payload: OfficialScreenerSearchRequest
): Promise<OfficialScreenerSearchResponse> {
  return fetchJson("/screener/search", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

function currentAsOfParam(): string | undefined {
  if (typeof window === "undefined") {
    return undefined;
  }
  const value = new URLSearchParams(window.location.search).get("as_of")?.trim();
  return value || undefined;
}

function appendAsOf(params: URLSearchParams, asOf?: string | null): void {
  const value = asOf?.trim() || currentAsOfParam();
  if (value) {
    params.set("as_of", value);
  }
}

export function getCompanyFinancials(
  ticker: string,
  options?: { asOf?: string | null; view?: "full" | "core_segments" | "core"; signal?: AbortSignal }
): Promise<CompanyFinancialsResponse> {
  const params = new URLSearchParams();
  if (options?.view && options.view !== "full") {
    params.set("view", options.view);
  }
  appendAsOf(params, options?.asOf);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/financials${suffix}`, { signal: options?.signal });
}

export function getCompanyOverview(
  ticker: string,
  options?: { asOf?: string | null; financialsView?: "full" | "core_segments" | "core"; signal?: AbortSignal }
): Promise<CompanyOverviewResponse> {
  const params = new URLSearchParams();
  if (options?.financialsView && options.financialsView !== "full") {
    params.set("financials_view", options.financialsView);
  }
  appendAsOf(params, options?.asOf);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const financialsParams = new URLSearchParams();
  if (options?.financialsView && options.financialsView !== "full") {
    financialsParams.set("view", options.financialsView);
  }
  appendAsOf(financialsParams, options?.asOf);
  const financialsSuffix = financialsParams.toString() ? `?${financialsParams.toString()}` : "";
  const normalizedTicker = encodeURIComponent(ticker);
  return fetchJson<CompanyOverviewResponse>(`/companies/${normalizedTicker}/overview${suffix}`, { signal: options?.signal }).then((payload) => {
    shareReadCacheValue(`/companies/${normalizedTicker}/financials${financialsSuffix}`, payload.financials);
    return payload;
  });
}

export function getCompanyWorkspaceBootstrap(
  ticker: string,
  options?: {
    asOf?: string | null;
    financialsView?: "full" | "core_segments" | "core";
    includeOverviewBrief?: boolean;
    includeInsiders?: boolean;
    includeInstitutional?: boolean;
    includeEarningsSummary?: boolean;
    signal?: AbortSignal;
  }
): Promise<CompanyWorkspaceBootstrapResponse> {
  const params = new URLSearchParams();
  if (options?.financialsView && options.financialsView !== "full") {
    params.set("financials_view", options.financialsView);
  }
  if (options?.includeOverviewBrief) {
    params.set("include_overview_brief", "true");
  }
  if (options?.includeInsiders) {
    params.set("include_insiders", "true");
  }
  if (options?.includeInstitutional) {
    params.set("include_institutional", "true");
  }
  if (options?.includeEarningsSummary) {
    params.set("include_earnings_summary", "true");
  }
  appendAsOf(params, options?.asOf);

  const suffix = params.toString() ? `?${params.toString()}` : "";
  const normalizedTicker = encodeURIComponent(ticker);
  const financialsParams = new URLSearchParams();
  if (options?.financialsView && options.financialsView !== "full") {
    financialsParams.set("view", options.financialsView);
  }
  appendAsOf(financialsParams, options?.asOf);
  const financialsSuffix = financialsParams.toString() ? `?${financialsParams.toString()}` : "";

  return fetchJson<CompanyWorkspaceBootstrapResponse>(`/companies/${normalizedTicker}/workspace-bootstrap${suffix}`, {
    signal: options?.signal,
  }).then((payload) => {
    shareReadCacheValue(`/companies/${normalizedTicker}/financials${financialsSuffix}`, payload.financials);
    if (payload.brief) {
      const overviewParams = new URLSearchParams();
      if (options?.financialsView && options.financialsView !== "full") {
        overviewParams.set("financials_view", options.financialsView);
      }
      appendAsOf(overviewParams, options?.asOf);
      const overviewSuffix = overviewParams.toString() ? `?${overviewParams.toString()}` : "";
      shareReadCacheValue(`/companies/${normalizedTicker}/overview${overviewSuffix}`, {
        company: payload.company,
        financials: payload.financials,
        brief: payload.brief,
      });
    }
    return payload;
  });
}

export function getCompaniesCompare(
  tickers: string[],
  options?: { asOf?: string | null; signal?: AbortSignal }
): Promise<CompanyCompareResponse> {
  const normalized = tickers
    .map((ticker) => ticker.trim().toUpperCase())
    .filter(Boolean)
    .slice(0, 5);
  const params = new URLSearchParams({ tickers: normalized.join(",") });
  appendAsOf(params, options?.asOf);
  return fetchJson(`/companies/compare?${params.toString()}`, { signal: options?.signal });
}

export function getCompanyCapitalStructure(
  ticker: string,
  options?: { maxPeriods?: number; asOf?: string | null; signal?: AbortSignal }
): Promise<CompanyCapitalStructureResponse> {
  const params = new URLSearchParams();
  if (options?.maxPeriods != null) {
    params.set("max_periods", String(options.maxPeriods));
  }
  appendAsOf(params, options?.asOf);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/capital-structure${suffix}`, { signal: options?.signal });
}

export function getCompanyCharts(
  ticker: string,
  options?: { asOf?: string | null; signal?: AbortSignal }
): Promise<CompanyChartsDashboardResponse> {
  const params = new URLSearchParams();
  appendAsOf(params, options?.asOf);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/charts${suffix}`, { signal: options?.signal });
}

export function getCompanyChartsForecastAccuracy(
  ticker: string,
  options?: { asOf?: string | null; signal?: AbortSignal }
): Promise<CompanyChartsForecastAccuracyResponse> {
  const params = new URLSearchParams();
  appendAsOf(params, options?.asOf);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/charts/forecast-accuracy${suffix}`, { signal: options?.signal });
}

export function getCompanyChartsWhatIf(
  ticker: string,
  body: CompanyChartsWhatIfRequest,
  options?: { asOf?: string | null; signal?: AbortSignal }
): Promise<CompanyChartsDashboardResponse> {
  const params = new URLSearchParams();
  appendAsOf(params, options?.asOf);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/charts/what-if${suffix}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    signal: options?.signal,
  });
}

export function getCompanyEquityClaimRisk(
  ticker: string,
  options?: { asOf?: string | null; signal?: AbortSignal }
): Promise<CompanyEquityClaimRiskResponse> {
  const params = new URLSearchParams();
  appendAsOf(params, options?.asOf);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/equity-claim-risk${suffix}`, { signal: options?.signal });
}

export function getCompanySegmentHistory(
  ticker: string,
  options?: {
    kind?: "business" | "geographic";
    years?: number;
    asOf?: string | null;
    signal?: AbortSignal;
  }
): Promise<CompanySegmentHistoryResponse> {
  const params = new URLSearchParams();
  if (options?.kind) {
    params.set("kind", options.kind);
  }
  if (options?.years != null) {
    params.set("years", String(options.years));
  }
  appendAsOf(params, options?.asOf);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/segment-history${suffix}`, { signal: options?.signal });
}

export function getCompanyChangesSinceLastFiling(
  ticker: string,
  options?: { asOf?: string | null; signal?: AbortSignal }
): Promise<CompanyChangesSinceLastFilingResponse> {
  const params = new URLSearchParams();
  appendAsOf(params, options?.asOf);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/changes-since-last-filing${suffix}`, { signal: options?.signal });
}

export function getCompanyFinancialRestatements(
  ticker: string,
  options?: { asOf?: string | null; signal?: AbortSignal }
): Promise<CompanyFinancialRestatementsResponse> {
  const params = new URLSearchParams();
  appendAsOf(params, options?.asOf);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/financial-restatements${suffix}`, { signal: options?.signal });
}

export function getCompanyMetricsTimeseries(
  ticker: string,
  options?: { cadence?: "quarterly" | "annual" | "ttm"; maxPoints?: number; asOf?: string | null; signal?: AbortSignal }
): Promise<CompanyMetricsTimeseriesResponse> {
  const params = new URLSearchParams();
  if (options?.cadence) {
    params.set("cadence", options.cadence);
  }
  if (options?.maxPoints != null) {
    params.set("max_points", String(options.maxPoints));
  }
  appendAsOf(params, options?.asOf);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/metrics-timeseries${suffix}`, { signal: options?.signal });
}

export function getCompanyDerivedMetrics(
  ticker: string,
  options?: { periodType?: "quarterly" | "annual" | "ttm"; maxPeriods?: number; asOf?: string | null; signal?: AbortSignal }
): Promise<CompanyDerivedMetricsResponse> {
  const params = new URLSearchParams();
  if (options?.periodType) {
    params.set("period_type", options.periodType);
  }
  if (options?.maxPeriods != null) {
    params.set("max_periods", String(options.maxPeriods));
  }
  appendAsOf(params, options?.asOf);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/metrics${suffix}`, { signal: options?.signal });
}

export function getCompanyDerivedMetricsSummary(
  ticker: string,
  options?: { periodType?: "quarterly" | "annual" | "ttm"; asOf?: string | null; signal?: AbortSignal }
): Promise<CompanyDerivedMetricsSummaryResponse> {
  const params = new URLSearchParams();
  if (options?.periodType) {
    params.set("period_type", options.periodType);
  }
  appendAsOf(params, options?.asOf);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/metrics/summary${suffix}`, { signal: options?.signal });
}

export function getCompanyFilings(ticker: string): Promise<CompanyFilingsResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/filings`);
}

export function getCompanyBeneficialOwnership(ticker: string): Promise<CompanyBeneficialOwnershipResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/beneficial-ownership`);
}

export function getCompanyBeneficialOwnershipSummary(ticker: string): Promise<CompanyBeneficialOwnershipSummaryResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/beneficial-ownership/summary`);
}

export function getCompanyGovernance(ticker: string): Promise<CompanyGovernanceResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/governance`);
}

export function getCompanyGovernanceSummary(ticker: string): Promise<CompanyGovernanceSummaryResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/governance/summary`);
}

export function getCompanyExecutiveCompensation(ticker: string): Promise<CompanyExecutiveCompensationResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/executive-compensation`);
}

export function getCompanyEvents(ticker: string): Promise<CompanyEventsResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/events`);
}

export function getCompanyFilingEvents(ticker: string): Promise<CompanyEventsResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/filing-events`);
}

export function getCompanyFilingEventsSummary(ticker: string): Promise<CompanyFilingEventsSummaryResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/filing-events/summary`);
}

export function getCompanyCapitalRaises(ticker: string): Promise<CompanyCapitalRaisesResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/capital-raises`);
}

export function getCompanyCapitalMarkets(ticker: string): Promise<CompanyCapitalRaisesResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/capital-markets`);
}

export function getCompanyCapitalMarketsSummary(ticker: string): Promise<CompanyCapitalMarketsSummaryResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/capital-markets/summary`);
}

export function getCompanyEarnings(ticker: string): Promise<CompanyEarningsResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/earnings`);
}

export function getCompanyEarningsSummary(
  ticker: string,
  options?: { signal?: AbortSignal }
): Promise<CompanyEarningsSummaryResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/earnings/summary`, { signal: options?.signal });
}

export function getCompanyEarningsWorkspace(ticker: string): Promise<CompanyEarningsWorkspaceResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/earnings/workspace`);
}

export function getCompanyActivityFeed(ticker: string): Promise<CompanyActivityFeedResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/activity-feed`);
}

export function getCompanyAlerts(ticker: string): Promise<CompanyAlertsResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/alerts`);
}

export function getCompanyActivityOverview(ticker: string): Promise<CompanyActivityOverviewResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/activity-overview`);
}

export function getCompanyCommentLetters(ticker: string): Promise<CompanyCommentLettersResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/comment-letters`);
}



export function getCompanyFilingInsights(ticker: string): Promise<CompanyFilingInsightsResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/filing-insights`);
}

export function getCompanyInsiderTrades(
  ticker: string,
  options?: { signal?: AbortSignal }
): Promise<CompanyInsiderTradesResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/insider-trades`, { signal: options?.signal });
}

export function getCompanyForm144Filings(ticker: string): Promise<CompanyForm144Response> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/form-144-filings`);
}

export function getCompanyInstitutionalHoldings(
  ticker: string,
  options?: { signal?: AbortSignal }
): Promise<CompanyInstitutionalHoldingsResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/institutional-holdings`, { signal: options?.signal });
}

export function getCompanyInstitutionalHoldingsSummary(ticker: string): Promise<CompanyInstitutionalHoldingsSummaryResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/institutional-holdings/summary`);
}

export function getCompanyModels(
  ticker: string,
  modelNames?: string[],
  options?: { dupontMode?: "auto" | "annual" | "ttm"; asOf?: string | null; expandInputPeriods?: boolean; signal?: AbortSignal }
): Promise<CompanyModelsResponse> {
  const params = new URLSearchParams();
  if (modelNames?.length) {
    params.set("model", modelNames.join(","));
  }
  if (options?.expandInputPeriods) {
    params.set("expand", "input_periods");
  }
  if (options?.dupontMode) {
    params.set("dupont_mode", options.dupontMode);
  }
  appendAsOf(params, options?.asOf);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/models${suffix}`, { signal: options?.signal });
}

export function getCompanyOilScenarioOverlay(
  ticker: string,
  options?: { asOf?: string | null; signal?: AbortSignal }
): Promise<CompanyOilScenarioResponse> {
  return getCompanyOilScenario(ticker, options);
}

export function getCompanyOilScenario(
  ticker: string,
  options?: { asOf?: string | null; signal?: AbortSignal }
): Promise<CompanyOilScenarioResponse> {
  const params = new URLSearchParams();
  appendAsOf(params, options?.asOf);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/oil-scenario${suffix}`, { signal: options?.signal });
}

export function getLatestModelEvaluation(
  suiteKey?: string | null,
  options?: { signal?: AbortSignal }
): Promise<ModelEvaluationResponse> {
  const params = new URLSearchParams();
  if (suiteKey) {
    params.set("suite_key", suiteKey);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/model-evaluations/latest${suffix}`, { signal: options?.signal });
}

export function getCompanyMarketContext(
  ticker: string,
  options?: { signal?: AbortSignal }
): Promise<CompanyMarketContextResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/market-context`, { signal: options?.signal });
}

export function getCompanySectorContext(
  ticker: string,
  options?: { signal?: AbortSignal }
): Promise<CompanySectorContextResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/sector-context`, { signal: options?.signal });
}

export function getGlobalMarketContext(): Promise<CompanyMarketContextResponse> {
  return fetchJson("/market-context");
}

export function getCompanyResearchBrief(
  ticker: string,
  options?: { asOf?: string | null; signal?: AbortSignal }
): Promise<CompanyResearchBriefResponse> {
  const params = new URLSearchParams();
  appendAsOf(params, options?.asOf);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/brief${suffix}`, { signal: options?.signal });
}

export function getCompanyPeers(
  ticker: string,
  peers?: string[],
  options?: { asOf?: string | null }
): Promise<CompanyPeersResponse> {
  const params = new URLSearchParams();
  if (peers?.length) {
    params.set("peers", peers.join(","));
  }
  appendAsOf(params, options?.asOf);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/peers${suffix}`);
}

export function refreshCompany(ticker: string, force = false): Promise<RefreshQueuedResponse> {
  const suffix = force ? "?force=true" : "";
  return fetchJson<RefreshQueuedResponse>(`/companies/${encodeURIComponent(ticker)}/refresh${suffix}`, { method: "POST" }).then((response) => {
    invalidateApiReadCacheForTicker(ticker);
    return response;
  });
}

export function getWatchlistSummary(tickers: string[]): Promise<WatchlistSummaryResponse> {
  return fetchJson("/watchlist/summary", {
    method: "POST",
    body: JSON.stringify({ tickers }),
  });
}

export function getWatchlistCalendar(tickers: string[]): Promise<WatchlistCalendarResponse> {
  const params = new URLSearchParams();
  for (const ticker of tickers) {
    params.append("tickers", ticker);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/watchlist/calendar${suffix}`);
}

export function getSourceRegistry(): Promise<SourceRegistryResponse> {
  return fetchJson("/source-registry");
}

export function getCacheMetrics(): Promise<CacheMetricsResponse> {
  return fetchJson("/internal/cache-metrics");
}

export async function getCompanyFinancialHistory(
  cik: string,
  options?: { signal?: AbortSignal }
): Promise<FinancialHistoryPoint[]> {
  const payload = await fetchJson<CompanyFactsPayload>(
    `/companies/${encodeURIComponent(cik)}/financial-history`,
    { signal: options?.signal }
  );

  return parseCompanyFacts(payload);
}

export type CompanyFactsPayload = {
  facts?: Record<string, Record<string, { units?: Record<string, Array<Record<string, unknown>>> }>>;
};

type FinancialHistoryMetric = "revenue" | "net_income" | "eps" | "operating_cash_flow";

const METRIC_CONFIG: Record<FinancialHistoryMetric, { tags: string[]; units: string[] }> = {
  revenue: { tags: ["Revenues", "SalesRevenueNet"], units: ["USD"] },
  net_income: { tags: ["NetIncomeLoss"], units: ["USD"] },
  eps: { tags: ["EarningsPerShareDiluted"], units: ["USD/shares"] },
  operating_cash_flow: { tags: ["NetCashProvidedByUsedInOperatingActivities"], units: ["USD"] }
};

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);

function parseCompanyFacts(payload: CompanyFactsPayload): FinancialHistoryPoint[] {
  const factRoot = payload?.facts ?? {};
  const metricSeries = Object.fromEntries(
    Object.entries(METRIC_CONFIG).map(([metric, config]) => [
      metric,
      pickMetricSeries(factRoot, config.tags, config.units)
    ])
  ) as Record<FinancialHistoryMetric, Map<number, number>>;

  const years = Array.from(
    new Set(Object.values(metricSeries).flatMap((series) => Array.from(series.keys())))
  ).sort((a, b) => a - b);

  if (!years.length) {
    return [];
  }

  const maxYear = years[years.length - 1];
  const startYear = maxYear - 9;
  const normalizedYears = Array.from({ length: 10 }, (_, index) => startYear + index);

  return normalizedYears.map((year) => ({
    year,
    revenue: metricSeries.revenue.get(year) ?? null,
    net_income: metricSeries.net_income.get(year) ?? null,
    eps: metricSeries.eps.get(year) ?? null,
    operating_cash_flow: metricSeries.operating_cash_flow.get(year) ?? null
  }));
}

function pickMetricSeries(
  factRoot: NonNullable<CompanyFactsPayload["facts"]>,
  tags: string[],
  allowedUnits: string[]
): Map<number, number> {
  const unitSet = new Set(allowedUnits);
  for (const taxonomy of Object.values(factRoot)) {
    if (!taxonomy || typeof taxonomy !== "object") {
      continue;
    }
    for (const tag of tags) {
      const metric = taxonomy[tag];
      if (!metric || typeof metric !== "object") {
        continue;
      }
      const units = metric.units ?? {};
      const series = new Map<number, number>();
      const seriesPriority = new Map<number, number>();
      for (const [unit, entries] of Object.entries(units)) {
        if (!unitSet.has(unit) || !Array.isArray(entries)) {
          continue;
        }
        for (const entry of entries) {
          if (!entry || typeof entry !== "object") {
            continue;
          }
          const record = entry as {
            fy?: number;
            val?: number;
            form?: string;
            fp?: string;
            filed?: string;
            end?: string;
          };
          const fy = Number(record.fy);
          if (!Number.isFinite(fy)) {
            continue;
          }
          const form = normalizeForm(record.form ? String(record.form) : "");
          if (!ANNUAL_FORMS.has(form)) {
            continue;
          }
          const fp = record.fp ? String(record.fp) : "";
          if (fp && fp !== "FY") {
            continue;
          }
          const value = Number(record.val);
          if (!Number.isFinite(value)) {
            continue;
          }
          const priority = Math.max(parseFactDate(record.filed), parseFactDate(record.end));
          const existingPriority = seriesPriority.get(fy) ?? -1;
          if (!series.has(fy) || priority >= existingPriority) {
            series.set(fy, value);
            seriesPriority.set(fy, priority);
          }
        }
      }
      if (series.size) {
        return series;
      }
    }
  }

  return new Map();
}

function normalizeForm(form: string): string {
  const normalized = form.trim().toUpperCase();
  if (normalized.endsWith("/A")) {
    return normalized.slice(0, -2);
  }
  if (normalized.endsWith("-A")) {
    return normalized.slice(0, -2);
  }
  return normalized;
}

function parseFactDate(value: unknown): number {
  if (typeof value !== "string") {
    return 0;
  }
  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp) ? 0 : timestamp;
}





