import {
  CompanyFinancialsResponse,
  CompanyInsiderTradesResponse,
  CompanyInstitutionalHoldingsResponse,
  CompanyModelsResponse,
  CompanyResolutionResponse,
  CompanyPeersResponse,
  CompanySearchResponse,
  RefreshQueuedResponse
} from "@/lib/types";

const API_PREFIX = "/backend/api";

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }

  return (await response.json()) as T;
}

export function searchCompanies(query: string, options?: { refresh?: boolean }): Promise<CompanySearchResponse> {
  const params = new URLSearchParams({ query });
  params.set("refresh", String(options?.refresh ?? true));
  return fetchJson(`/companies/search?${params.toString()}`);
}

export function resolveCompanyIdentifier(query: string): Promise<CompanyResolutionResponse> {
  return fetchJson(`/companies/resolve?query=${encodeURIComponent(query)}`);
}

export function getCompanyFinancials(ticker: string): Promise<CompanyFinancialsResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/financials`);
}

export function getCompanyInsiderTrades(ticker: string): Promise<CompanyInsiderTradesResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/insider-trades`);
}

export function getCompanyInstitutionalHoldings(ticker: string): Promise<CompanyInstitutionalHoldingsResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/institutional-holdings`);
}

export function getCompanyModels(ticker: string, modelNames?: string[]): Promise<CompanyModelsResponse> {
  const modelParam = modelNames?.length ? `?model=${encodeURIComponent(modelNames.join(","))}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/models${modelParam}`);
}

export function getCompanyPeers(ticker: string, peers?: string[]): Promise<CompanyPeersResponse> {
  const peerParam = peers?.length ? `?peers=${encodeURIComponent(peers.join(","))}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/peers${peerParam}`);
}

export function refreshCompany(ticker: string, force = false): Promise<RefreshQueuedResponse> {
  const suffix = force ? "?force=true" : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/refresh${suffix}`, { method: "POST" });
}
