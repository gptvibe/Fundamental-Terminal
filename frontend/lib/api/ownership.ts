import type {
  CompanyBeneficialOwnershipResponse,
  CompanyBeneficialOwnershipSummaryResponse,
  CompanyForm144Response,
  CompanyInsiderTradesResponse,
  CompanyInstitutionalHoldingsResponse,
  CompanyInstitutionalHoldingsSummaryResponse,
} from "@/lib/types";
import { fetchJson } from "./client";

export function getCompanyInsiderTrades(
  ticker: string,
  options?: { signal?: AbortSignal }
): Promise<CompanyInsiderTradesResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/insider-trades`, { signal: options?.signal });
}

export function getCompanyBeneficialOwnership(ticker: string): Promise<CompanyBeneficialOwnershipResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/beneficial-ownership`);
}

export function getCompanyBeneficialOwnershipSummary(ticker: string): Promise<CompanyBeneficialOwnershipSummaryResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/beneficial-ownership/summary`);
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

export function getCompanyForm144Filings(ticker: string): Promise<CompanyForm144Response> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/form-144-filings`);
}
