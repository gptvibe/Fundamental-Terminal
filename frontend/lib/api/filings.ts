import type {
  CompanyEarningsResponse,
  CompanyEarningsSummaryResponse,
  CompanyEarningsWorkspaceResponse,
  CompanyExhibitsResponse,
  CompanyFilingEventsSummaryResponse,
  CompanyFilingInsightsResponse,
  CompanyFilingRiskSignalsResponse,
  CompanyFilingsResponse,
  CompanyEventsResponse,
} from "@/lib/types";
import { fetchJson } from "./client";

export function getCompanyFilings(ticker: string): Promise<CompanyFilingsResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/filings`);
}

export function getCompanyExhibits(
  ticker: string,
  options?: { exhibitType?: string; filingType?: string; limit?: number }
): Promise<CompanyExhibitsResponse> {
  const params = new URLSearchParams();
  if (options?.exhibitType) params.set("exhibit_type", options.exhibitType);
  if (options?.filingType) params.set("filing_type", options.filingType);
  if (options?.limit !== undefined) params.set("limit", String(options.limit));
  const query = params.toString();
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/exhibits${query ? `?${query}` : ""}`);
}

export function getCompanyFilingEvents(ticker: string): Promise<CompanyEventsResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/filing-events`);
}

export function getCompanyFilingEventsSummary(ticker: string): Promise<CompanyFilingEventsSummaryResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/filing-events/summary`);
}

export function getCompanyFilingInsights(ticker: string): Promise<CompanyFilingInsightsResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/filing-insights`);
}

export function getCompanyFilingRiskSignals(ticker: string): Promise<CompanyFilingRiskSignalsResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/filing-risk-signals`);
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
