import {
  CompanyCapitalRaisesResponse,
  CompanyCapitalMarketsSummaryResponse,
  CompanyFinancialsResponse,
  CompanyBeneficialOwnershipResponse,
  CompanyBeneficialOwnershipSummaryResponse,
  CompanyEventsResponse,
  CompanyFilingEventsSummaryResponse,
  CompanyFilingsResponse,
  CompanyFilingInsightsResponse,
  CompanyGovernanceResponse,
  CompanyGovernanceSummaryResponse,
  CompanyInsiderTradesResponse,
  CompanyInstitutionalHoldingsResponse,
  CompanyInstitutionalHoldingsSummaryResponse,
  CompanyModelsResponse,
  CompanyResolutionResponse,
  CompanyPeersResponse,
  CompanySearchResponse,
  FinancialHistoryPoint,
  RefreshQueuedResponse
} from "@/lib/types";

const API_PREFIX = "/backend/api";

async function fetchJson<T>(path: string, init?: RequestInit & { signal?: AbortSignal }): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    cache: "no-store",
    signal: init?.signal
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }

  return (await response.json()) as T;
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

export function getCompanyFinancials(ticker: string): Promise<CompanyFinancialsResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/financials`);
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



export function getCompanyFilingInsights(ticker: string): Promise<CompanyFilingInsightsResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/filing-insights`);
}

export function getCompanyInsiderTrades(ticker: string): Promise<CompanyInsiderTradesResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/insider-trades`);
}

export function getCompanyInstitutionalHoldings(ticker: string): Promise<CompanyInstitutionalHoldingsResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/institutional-holdings`);
}

export function getCompanyInstitutionalHoldingsSummary(ticker: string): Promise<CompanyInstitutionalHoldingsSummaryResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/institutional-holdings/summary`);
}

export function getCompanyModels(ticker: string, modelNames?: string[], options?: { dupontMode?: "auto" | "annual" | "ttm" }): Promise<CompanyModelsResponse> {
  const params = new URLSearchParams();
  if (modelNames?.length) {
    params.set("model", modelNames.join(","));
  }
  if (options?.dupontMode) {
    params.set("dupont_mode", options.dupontMode);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/models${suffix}`);
}

export function getCompanyPeers(ticker: string, peers?: string[]): Promise<CompanyPeersResponse> {
  const peerParam = peers?.length ? `?peers=${encodeURIComponent(peers.join(","))}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/peers${peerParam}`);
}

export function refreshCompany(ticker: string, force = false): Promise<RefreshQueuedResponse> {
  const suffix = force ? "?force=true" : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/refresh${suffix}`, { method: "POST" });
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





