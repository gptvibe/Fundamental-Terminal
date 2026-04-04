import {
  CompanyActivityFeedResponse,
  CompanyActivityOverviewResponse,
  CompanyAlertsResponse,
  CompanyCommentLettersResponse,
  CompanyCapitalRaisesResponse,
  CompanyCompareResponse,
  CompanyCapitalMarketsSummaryResponse,
  CompanyCapitalStructureResponse,
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
  CompanySectorContextResponse,
  CompanyMetricsTimeseriesResponse,
  CompanyResolutionResponse,
  CompanyPeersResponse,
  CompanySearchResponse,
  OfficialScreenerMetadataResponse,
  OfficialScreenerSearchRequest,
  OfficialScreenerSearchResponse,
  WatchlistSummaryResponse,
  FinancialHistoryPoint,
  RefreshQueuedResponse
} from "@/lib/types";

const API_PREFIX = "/backend/api";

type ReadCachePolicy = {
  ttlMs: number;
  staleMs: number;
};

type CacheEntry = {
  data: unknown;
  updatedAt: number;
};

const DEFAULT_READ_POLICY: ReadCachePolicy = {
  ttlMs: 45_000,
  staleMs: 180_000,
};

const READ_POLICY_BY_PATH: Array<{ pattern: RegExp; policy: ReadCachePolicy }> = [
  { pattern: /^\/companies\/search\?/, policy: { ttlMs: 20_000, staleMs: 90_000 } },
  { pattern: /^\/screener\/filters(?:\?|$)/, policy: { ttlMs: 300_000, staleMs: 900_000 } },
  { pattern: /^\/companies\/[^/]+\/financials(?:\?|$)/, policy: { ttlMs: 30_000, staleMs: 120_000 } },
  { pattern: /^\/companies\/[^/]+\/segment-history(?:\?|$)/, policy: { ttlMs: 30_000, staleMs: 120_000 } },
  { pattern: /^\/companies\/[^/]+\/capital-structure(?:\?|$)/, policy: { ttlMs: 45_000, staleMs: 180_000 } },
  { pattern: /^\/companies\/[^/]+\/models(?:\?|$)/, policy: { ttlMs: 45_000, staleMs: 180_000 } },
  { pattern: /^\/companies\/[^/]+\/oil-scenario(?:\?|$)/, policy: { ttlMs: 45_000, staleMs: 180_000 } },
  { pattern: /^\/companies\/[^/]+\/oil-scenario-overlay(?:\?|$)/, policy: { ttlMs: 45_000, staleMs: 180_000 } },
  { pattern: /^\/model-evaluations\/latest(?:\?|$)/, policy: { ttlMs: 60_000, staleMs: 240_000 } },
  { pattern: /^\/companies\/[^/]+\/peers(?:\?|$)/, policy: { ttlMs: 45_000, staleMs: 180_000 } },
  { pattern: /^\/companies\/[^/]+\/sector-context(?:\?|$)/, policy: { ttlMs: 45_000, staleMs: 180_000 } },
  { pattern: /^\/companies\/[^/]+\/metrics(?:\?|$)/, policy: { ttlMs: 60_000, staleMs: 180_000 } },
  { pattern: /^\/companies\/[^/]+\/metrics-timeseries(?:\?|$)/, policy: { ttlMs: 60_000, staleMs: 180_000 } },
  { pattern: /^\/market-context(?:\?|$)/, policy: { ttlMs: 300_000, staleMs: 900_000 } },
  { pattern: /^\/watchlist\/summary(?:\?|$)/, policy: { ttlMs: 30_000, staleMs: 120_000 } },
];

const CACHE_STORAGE_PREFIX = "ft:api-cache:v2:";
const CACHE_BROADCAST_CHANNEL = "ft:api-cache-events";

const readCache = new Map<string, CacheEntry>();
const inflightReads = new Map<string, Promise<unknown>>();
let cacheSyncInitialized = false;

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

function tryReadPersistentCache(cacheKey: string): CacheEntry | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    const raw = window.localStorage.getItem(cacheStorageKey(cacheKey));
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as CacheEntry;
    if (!parsed || typeof parsed.updatedAt !== "number") {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function writePersistentCache(cacheKey: string, entry: CacheEntry): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.setItem(cacheStorageKey(cacheKey), JSON.stringify(entry));
  } catch {
    // Ignore storage quota and serialization errors. Memory cache still works.
  }
}

function removePersistentCache(cacheKey: string): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.removeItem(cacheStorageKey(cacheKey));
  } catch {
    // Ignore storage errors.
  }
}

function setupCrossTabCacheSync(): void {
  if (cacheSyncInitialized || typeof window === "undefined") {
    return;
  }

  cacheSyncInitialized = true;
  window.addEventListener("storage", (event) => {
    if (!event.key?.startsWith(CACHE_STORAGE_PREFIX)) {
      return;
    }

    const cacheKey = event.key.slice(CACHE_STORAGE_PREFIX.length);
    if (event.newValue == null) {
      readCache.delete(cacheKey);
      return;
    }

    try {
      const parsed = JSON.parse(event.newValue) as CacheEntry;
      if (parsed && typeof parsed.updatedAt === "number") {
        readCache.set(cacheKey, parsed);
      }
    } catch {
      // Ignore malformed external cache writes.
    }
  });

  if (typeof BroadcastChannel !== "undefined") {
    const channel = new BroadcastChannel(CACHE_BROADCAST_CHANNEL);
    channel.onmessage = (event: MessageEvent<{ type: "invalidate"; prefix: string }>) => {
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

  if (typeof BroadcastChannel === "undefined") {
    return;
  }

  const channel = new BroadcastChannel(CACHE_BROADCAST_CHANNEL);
  channel.postMessage({ type: "invalidate", prefix });
  channel.close();
}

function readCachedValue<T>(cacheKey: string, path: string): { data: T; stale: boolean } | null {
  setupCrossTabCacheSync();
  const now = Date.now();
  const policy = resolveReadPolicy(path);
  const inMemory = readCache.get(cacheKey);
  const entry = inMemory ?? tryReadPersistentCache(cacheKey);
  if (!entry) {
    return null;
  }

  if (!inMemory) {
    readCache.set(cacheKey, entry);
  }

  if (now - entry.updatedAt > policy.staleMs) {
    readCache.delete(cacheKey);
    removePersistentCache(cacheKey);
    return null;
  }

  return {
    data: entry.data as T,
    stale: now - entry.updatedAt > policy.ttlMs,
  };
}

function cacheValue(cacheKey: string, data: unknown): void {
  const entry: CacheEntry = {
    data,
    updatedAt: Date.now(),
  };
  readCache.set(cacheKey, entry);
  writePersistentCache(cacheKey, entry);
}

function withApiPrefix(path: string): string {
  return `${API_PREFIX}${path}`;
}

async function fetchAndParse<T>(path: string, init?: RequestInit & { signal?: AbortSignal }): Promise<T> {
  const response = await fetch(withApiPrefix(path), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    cache: init?.cache,
    signal: init?.signal
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }

  return (await response.json()) as T;
}

async function fetchJson<T>(path: string, init?: RequestInit & { signal?: AbortSignal }): Promise<T> {
  const readRequest = isReadRequest(init);
  if (!readRequest) {
    return fetchAndParse<T>(path, { ...init, cache: "no-store" });
  }

  if (shouldBypassReadCache(path)) {
    return fetchAndParse<T>(path, { ...init, cache: "no-store" });
  }

  const cacheKey = path;
  const cached = readCachedValue<T>(cacheKey, path);
  if (cached && !cached.stale) {
    return cached.data;
  }

  const currentInflight = inflightReads.get(cacheKey) as Promise<T> | undefined;
  if (currentInflight) {
    return currentInflight;
  }

  if (cached?.stale) {
    void revalidateRead(path, cacheKey);
    return cached.data;
  }

  return revalidateRead(path, cacheKey, init);
}

async function revalidateRead<T>(path: string, cacheKey: string, init?: RequestInit & { signal?: AbortSignal }): Promise<T> {
  const request = fetchAndParse<T>(path, { ...init, cache: "no-store" })
    .then((payload) => {
      cacheValue(cacheKey, payload);
      return payload;
    })
    .finally(() => {
      inflightReads.delete(cacheKey);
    });

  inflightReads.set(cacheKey, request);
  return request;
}

export function invalidateApiReadCache(prefix = "", options?: { emitCrossTab?: boolean }): void {
  for (const key of [...readCache.keys()]) {
    if (!prefix || key.startsWith(prefix)) {
      readCache.delete(key);
      removePersistentCache(key);
    }
  }

  if (options?.emitCrossTab !== false) {
    emitInvalidation(prefix);
  }
}

export function invalidateApiReadCacheForTicker(ticker: string): void {
  const normalized = encodeURIComponent(ticker.trim().toUpperCase());
  invalidateApiReadCache(`/companies/${normalized}/`);
}

export function __resetApiClientCacheForTests(): void {
  invalidateApiReadCache("", { emitCrossTab: false });
  inflightReads.clear();
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
  options?: { asOf?: string | null; signal?: AbortSignal }
): Promise<CompanyFinancialsResponse> {
  const params = new URLSearchParams();
  appendAsOf(params, options?.asOf);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/financials${suffix}`, { signal: options?.signal });
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

export function getCompanyEarningsSummary(ticker: string): Promise<CompanyEarningsSummaryResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/earnings/summary`);
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

export function getCompanyInsiderTrades(ticker: string): Promise<CompanyInsiderTradesResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/insider-trades`);
}

export function getCompanyForm144Filings(ticker: string): Promise<CompanyForm144Response> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/form-144-filings`);
}

export function getCompanyInstitutionalHoldings(ticker: string): Promise<CompanyInstitutionalHoldingsResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/institutional-holdings`);
}

export function getCompanyInstitutionalHoldingsSummary(ticker: string): Promise<CompanyInstitutionalHoldingsSummaryResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/institutional-holdings/summary`);
}

export function getCompanyModels(
  ticker: string,
  modelNames?: string[],
  options?: { dupontMode?: "auto" | "annual" | "ttm"; asOf?: string | null }
): Promise<CompanyModelsResponse> {
  const params = new URLSearchParams();
  if (modelNames?.length) {
    params.set("model", modelNames.join(","));
  }
  if (options?.dupontMode) {
    params.set("dupont_mode", options.dupontMode);
  }
  appendAsOf(params, options?.asOf);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/models${suffix}`);
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

export function getLatestModelEvaluation(suiteKey?: string | null): Promise<ModelEvaluationResponse> {
  const params = new URLSearchParams();
  if (suiteKey) {
    params.set("suite_key", suiteKey);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/model-evaluations/latest${suffix}`);
}

export function getCompanyMarketContext(ticker: string): Promise<CompanyMarketContextResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/market-context`);
}

export function getCompanySectorContext(ticker: string): Promise<CompanySectorContextResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/sector-context`);
}

export function getGlobalMarketContext(): Promise<CompanyMarketContextResponse> {
  return fetchJson("/market-context");
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





