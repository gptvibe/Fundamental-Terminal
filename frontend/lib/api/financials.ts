import type {
  CompanyDerivedMetricsResponse,
  CompanyDerivedMetricsSummaryResponse,
  CompanyFinancialsResponse,
  CompanyCapitalStructureResponse,
  CompanyChangesSinceLastFilingResponse,
  CompanyFinancialRestatementsResponse,
  CompanyMetricsTimeseriesResponse,
  CompanyOilScenarioResponse,
  CompanySegmentHistoryResponse,
  FinancialHistoryPoint,
} from "@/lib/types";
import { appendAsOf, fetchJson } from "./client";

export type CompanyFactsPayload = {
  facts?: Record<string, Record<string, { units?: Record<string, Array<Record<string, unknown>>> }>>;
};

export function getCompanyFinancials(
  ticker: string,
  options?: {
    asOf?: string | null;
    view?: "full" | "core_segments" | "core";
    priceStartDate?: string | null;
    priceEndDate?: string | null;
    priceLatestN?: number;
    priceMaxPoints?: number;
    signal?: AbortSignal;
  }
): Promise<CompanyFinancialsResponse> {
  const params = new URLSearchParams();
  if (options?.view && options.view !== "full") {
    params.set("view", options.view);
  }
  if (options?.priceStartDate) {
    params.set("price_start_date", options.priceStartDate);
  }
  if (options?.priceEndDate) {
    params.set("price_end_date", options.priceEndDate);
  }
  if (options?.priceLatestN != null) {
    params.set("price_latest_n", String(options.priceLatestN));
  }
  if (options?.priceMaxPoints != null) {
    params.set("price_max_points", String(options.priceMaxPoints));
  }
  appendAsOf(params, options?.asOf);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/financials${suffix}`, { signal: options?.signal });
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
