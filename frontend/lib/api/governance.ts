import type {
  CompanyExecutiveCompensationResponse,
  CompanyGovernanceResponse,
  CompanyGovernanceSummaryResponse,
} from "@/lib/types";
import { fetchJson } from "./client";

export function getCompanyGovernance(ticker: string): Promise<CompanyGovernanceResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/governance`);
}

export function getCompanyGovernanceSummary(ticker: string): Promise<CompanyGovernanceSummaryResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/governance/summary`);
}

export function getCompanyExecutiveCompensation(ticker: string): Promise<CompanyExecutiveCompensationResponse> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/executive-compensation`);
}
