import {
  beginPerformanceAuditNetworkRequest,
  endPerformanceAuditNetworkRequest,
  getCurrentPerformanceAuditContext,
  isPerformanceAuditEnabled,
  recordPerformanceAuditRequest,
  type PerformanceAuditContext,
  type PerformanceAuditCacheDisposition,
  type PerformanceAuditResponseSource,
} from "@/lib/performance-audit";

import type { ApiAuthHeadersProvider, ReadCachePolicy } from "./types";
import { isReadRequest, resolveReadPolicy, shouldBypassReadCache } from "./cachePolicy";
import { inflightRequests, INFLIGHT_REQUEST_TIMEOUT_MS } from "./inflight";
import { getDemoFixtureResponse, isDemoModeEnabled } from "./demo-fixtures";
import {
  cacheValue,
  invalidateApiReadCache,
  readCachedValue,
  removePersistentCacheByPrefix,
} from "./cacheStore";

export { invalidateApiReadCache };

const API_PREFIX = "/backend/api";
const AUDIT_RECORDED_ERROR = Symbol("auditRecordedError");
const PROJECTION_STUDIO_VIEWER_STORAGE_KEY = "ft:projection-studio:viewer";

let apiAuthHeadersProvider: ApiAuthHeadersProvider | null = null;

export function setApiAuthHeadersProvider(provider: ApiAuthHeadersProvider | null): void {
  apiAuthHeadersProvider = provider;
}

export function buildApiAuthHeaders(): Record<string, string> {
  if (!apiAuthHeadersProvider) {
    return {};
  }

  return normalizeHeaders(apiAuthHeadersProvider() ?? undefined);
}

export function normalizeHeaders(headers: HeadersInit | undefined): Record<string, string> {
  if (!headers) {
    return {};
  }

  const normalized = new Headers(headers);
  const entries: Record<string, string> = {};
  normalized.forEach((value, key) => {
    entries[key.toLowerCase()] = value;
  });
  return entries;
}

export function buildProjectionStudioViewerHeader(): Record<string, string> {
  if (typeof window === "undefined") {
    return {};
  }

  try {
    const existing = window.localStorage.getItem(PROJECTION_STUDIO_VIEWER_STORAGE_KEY)?.trim();
    const viewerKey = existing || buildProjectionStudioViewerKey();
    if (!existing) {
      window.localStorage.setItem(PROJECTION_STUDIO_VIEWER_STORAGE_KEY, viewerKey);
    }
    return { "X-FT-Projection-Viewer": viewerKey };
  } catch {
    return {};
  }
}

function buildProjectionStudioViewerKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }

  return `viewer-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function withApiPrefix(path: string): string {
  return `${API_PREFIX}${path}`;
}

function requestKeyForPath(path: string): string {
  return withApiPrefix(path);
}

export function currentAsOfParam(): string | undefined {
  if (typeof window === "undefined") {
    return undefined;
  }
  const value = new URLSearchParams(window.location.search).get("as_of")?.trim();
  return value || undefined;
}

export function appendAsOf(params: URLSearchParams, asOf?: string | null): void {
  const value = asOf?.trim() || currentAsOfParam();
  if (value) {
    params.set("as_of", value);
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

async function fetchWithTimeout(input: string, init: RequestInit & { signal?: AbortSignal }): Promise<Response> {
  const timeoutController = new AbortController();
  const { signal, cleanup } = composeAbortSignals(init.signal, timeoutController.signal);
  let timeoutId: ReturnType<typeof globalThis.setTimeout> | null = null;
  let timedOut = false;
  const fetchPromise = fetch(input, {
    ...init,
    signal,
  });

  try {
    return await Promise.race([
      fetchPromise,
      new Promise<Response>((_resolve, reject) => {
        timeoutId = globalThis.setTimeout(() => {
          timedOut = true;
          timeoutController.abort();
          reject(new Error(`API request timed out after ${INFLIGHT_REQUEST_TIMEOUT_MS} ms`));
        }, INFLIGHT_REQUEST_TIMEOUT_MS);
      }),
    ]);
  } catch (error) {
    if (timedOut) {
      throw new Error(`API request timed out after ${INFLIGHT_REQUEST_TIMEOUT_MS} ms`);
    }

    throw error;
  } finally {
    cleanup();
    if (timeoutId != null) {
      globalThis.clearTimeout(timeoutId);
    }
  }
}

function composeAbortSignals(...signals: Array<AbortSignal | undefined>): {
  signal: AbortSignal | undefined;
  cleanup: () => void;
} {
  const activeSignals = signals.filter((signal): signal is AbortSignal => Boolean(signal));
  if (activeSignals.length <= 1) {
    return {
      signal: activeSignals[0],
      cleanup: () => {},
    };
  }

  const controller = new AbortController();
  const listeners = new Map<AbortSignal, () => void>();

  const abortFrom = (source: AbortSignal) => {
    if (controller.signal.aborted) {
      return;
    }

    if ("reason" in source) {
      controller.abort(source.reason);
      return;
    }

    controller.abort();
  };

  for (const signal of activeSignals) {
    if (signal.aborted) {
      abortFrom(signal);
      return {
        signal: controller.signal,
        cleanup: () => {},
      };
    }

    const listener = () => abortFrom(signal);
    listeners.set(signal, listener);
    signal.addEventListener("abort", listener, { once: true });
  }

  return {
    signal: controller.signal,
    cleanup: () => {
      for (const [signal, listener] of listeners.entries()) {
        signal.removeEventListener("abort", listener);
      }
    },
  };
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
  responseSource: PerformanceAuditResponseSource,
  context: PerformanceAuditContext | null,
  metadata?: {
    cacheKey?: string | null;
    cachePolicyTtlMs?: number | null;
    cachePolicyStaleMs?: number | null;
    payloadBytes?: number | null;
  }
): void {
  if (!isPerformanceAuditEnabled()) {
    return;
  }

  recordPerformanceAuditRequest({
    context,
    method,
    path,
    cacheDisposition,
    cacheKey: metadata?.cacheKey ?? null,
    cachePolicyTtlMs: metadata?.cachePolicyTtlMs ?? null,
    cachePolicyStaleMs: metadata?.cachePolicyStaleMs ?? null,
    responseSource,
    networkRequest: false,
    backgroundRevalidate: false,
    statusCode: null,
    payloadBytes: metadata?.payloadBytes ?? null,
    durationMs: 0,
    responseBytes: metadata?.payloadBytes ?? null,
    error: null,
  });
}

export async function fetchAndParseWithAudit<T>(
  path: string,
  init: (RequestInit & { signal?: AbortSignal }) | undefined,
  audit:
    | {
        cacheDisposition: PerformanceAuditCacheDisposition;
        responseSource: PerformanceAuditResponseSource;
        backgroundRevalidate: boolean;
        context: PerformanceAuditContext | null;
        cacheKey?: string | null;
        cachePolicyTtlMs?: number | null;
        cachePolicyStaleMs?: number | null;
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
      const response = await fetchWithTimeout(withApiPrefix(path), {
        ...init,
        headers: {
          ...buildApiAuthHeaders(),
          "content-type": "application/json",
          ...normalizeHeaders(init?.headers)
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
          cacheKey: audit?.cacheKey ?? null,
          cachePolicyTtlMs: audit?.cachePolicyTtlMs ?? null,
          cachePolicyStaleMs: audit?.cachePolicyStaleMs ?? null,
          responseSource: audit?.responseSource ?? "network",
          networkRequest: true,
          backgroundRevalidate: audit?.backgroundRevalidate ?? false,
          statusCode: response.status,
          durationMs,
          payloadBytes: responseBytes,
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
          cacheKey: audit?.cacheKey ?? null,
          cachePolicyTtlMs: audit?.cachePolicyTtlMs ?? null,
          cachePolicyStaleMs: audit?.cachePolicyStaleMs ?? null,
          responseSource: audit?.responseSource ?? "network",
          networkRequest: true,
          backgroundRevalidate: audit?.backgroundRevalidate ?? false,
          statusCode: response.status,
          durationMs,
          payloadBytes: responseBytes,
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
          cacheKey: audit?.cacheKey ?? null,
          cachePolicyTtlMs: audit?.cachePolicyTtlMs ?? null,
          cachePolicyStaleMs: audit?.cachePolicyStaleMs ?? null,
          responseSource: audit?.responseSource ?? "network",
          networkRequest: true,
          backgroundRevalidate: audit?.backgroundRevalidate ?? false,
          statusCode: null,
          durationMs: performance.now() - startedPerf,
          payloadBytes: null,
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

export async function fetchAndParse<T>(path: string, init?: RequestInit & { signal?: AbortSignal }): Promise<T> {
  return fetchAndParseWithAudit(path, init, {
    cacheDisposition: "network",
    responseSource: "network",
    backgroundRevalidate: false,
    context: getCurrentPerformanceAuditContext(),
  });
}

async function revalidateRead<T>(
  path: string,
  cacheKey: string,
  init?: RequestInit & { signal?: AbortSignal },
  audit?: {
    cacheDisposition: PerformanceAuditCacheDisposition;
    responseSource: PerformanceAuditResponseSource;
    backgroundRevalidate: boolean;
    context: PerformanceAuditContext | null;
    cacheKey?: string | null;
    cachePolicyTtlMs?: number | null;
    cachePolicyStaleMs?: number | null;
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

  inflightRequests.set(requestKeyForPath(path), { promise: request, startedAt: Date.now() });
  return request;
}

export async function fetchJson<T>(path: string, init?: RequestInit & { signal?: AbortSignal; cachePolicy?: ReadCachePolicy }): Promise<T> {
  if (isDemoModeEnabled()) {
    const demoPayload = getDemoFixtureResponse(path, init);
    if (demoPayload !== null) {
      return demoPayload as T;
    }
  }

  const { cachePolicy: policyOverride, ...fetchInit } = init ?? {};
  const readRequest = isReadRequest(fetchInit);
  const auditContext = getCurrentPerformanceAuditContext();
  const cacheKey = readRequest ? path : null;
  const cachePolicy = readRequest ? (policyOverride ?? resolveReadPolicy(path)) : null;
  const cachePolicyTtlMs = cachePolicy?.ttlMs ?? null;
  const cachePolicyStaleMs = cachePolicy?.staleMs ?? null;
  if (!readRequest) {
    return fetchAndParseWithAudit<T>(path, { ...fetchInit, cache: "no-store" }, {
      cacheDisposition: "cache-bypass",
      responseSource: "cache-bypass",
      backgroundRevalidate: false,
      context: auditContext,
      cacheKey,
      cachePolicyTtlMs,
      cachePolicyStaleMs,
    });
  }

  if (shouldBypassReadCache(path)) {
    return fetchAndParseWithAudit<T>(path, { ...fetchInit, cache: "no-store" }, {
      cacheDisposition: "cache-bypass",
      responseSource: "cache-bypass",
      backgroundRevalidate: false,
      context: auditContext,
      cacheKey,
      cachePolicyTtlMs,
      cachePolicyStaleMs,
    });
  }

  const cacheKeyValue = path;
  const requestKey = requestKeyForPath(path);
  const cached = await readCachedValue<T>(cacheKeyValue, path, policyOverride);
  if (cached && !cached.stale) {
    recordCachedAudit(path, "GET", "fresh-cache-hit", cached.cacheSource, auditContext, {
      cacheKey: cacheKeyValue,
      cachePolicyTtlMs: cached.policy.ttlMs,
      cachePolicyStaleMs: cached.policy.staleMs,
      payloadBytes: cached.payloadBytes,
    });
    return cached.data;
  }

  const currentInflight = inflightRequests.get(requestKey) as { promise: Promise<T>; startedAt: number } | undefined;
  if (currentInflight) {
    if (Date.now() - currentInflight.startedAt < INFLIGHT_REQUEST_TIMEOUT_MS) {
      recordCachedAudit(path, "GET", "inflight-dedupe", "inflight-dedupe", auditContext, {
        cacheKey: cacheKeyValue,
        cachePolicyTtlMs,
        cachePolicyStaleMs,
      });
      return currentInflight.promise;
    }

    inflightRequests.delete(requestKey);
  }

  if (cached?.stale) {
    recordCachedAudit(path, "GET", "stale-cache-hit", "stale-cache", auditContext, {
      cacheKey: cacheKeyValue,
      cachePolicyTtlMs: cached.policy.ttlMs,
      cachePolicyStaleMs: cached.policy.staleMs,
      payloadBytes: cached.payloadBytes,
    });
    void revalidateRead(path, cacheKeyValue, fetchInit, {
      cacheDisposition: "network",
      responseSource: "network",
      backgroundRevalidate: true,
      context: auditContext,
      cacheKey: cacheKeyValue,
      cachePolicyTtlMs: cached.policy.ttlMs,
      cachePolicyStaleMs: cached.policy.staleMs,
    }).catch(() => {
      // Preserve stale serving behavior; background failures should not escape as unhandled rejections.
    });
    return cached.data;
  }

  return revalidateRead(path, cacheKeyValue, fetchInit, {
    cacheDisposition: "network",
    responseSource: "network",
    backgroundRevalidate: false,
    context: auditContext,
    cacheKey: cacheKeyValue,
    cachePolicyTtlMs,
    cachePolicyStaleMs,
  });
}

export async function __resetApiClientCacheForTests(): Promise<void> {
  invalidateApiReadCache("", { emitCrossTab: false });
  inflightRequests.clear();
  apiAuthHeadersProvider = null;
  await removePersistentCacheByPrefix("");
}
