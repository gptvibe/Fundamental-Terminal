import {
  CompanyFinancialsResponse,
  CompanyFilingsResponse,
  CompanyInsiderTradesResponse,
  CompanyInstitutionalHoldingsResponse,
  CompanyModelsResponse,
  CompanyResolutionResponse,
  CompanyPeersResponse,
  CompanySearchResponse,
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

export function getCompanyInsiderTrades(ticker: string): Promise<CompanyInsiderTradesResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/insider-trades`);
}

export function getCompanyInstitutionalHoldings(ticker: string): Promise<CompanyInstitutionalHoldingsResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/institutional-holdings`);
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
