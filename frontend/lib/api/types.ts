export type ReadCachePolicy = {
  ttlMs: number;
  staleMs: number;
};

export type ApiReadCacheState = "missing" | "fresh" | "stale";

export type CacheEntry = {
  data: unknown;
  updatedAt: number;
  approxSizeBytes: number;
  lastAccessedAt: number;
};

export type PersistedCacheEntry = {
  cacheKey: string;
  data: unknown;
  updatedAt: number;
  approxSizeBytes: number;
  lastAccessedAt: number;
};

export type ApiAuthHeadersProvider = () => HeadersInit | null | undefined;
