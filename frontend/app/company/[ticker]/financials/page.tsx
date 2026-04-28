import { headers } from "next/headers";

import CompanyFinancialsClientPage from "./financials-client-page";
import { FINANCIALS_ROUTE_REVALIDATE_SECONDS } from "./financials-route-data";
import type { LoadCompanyWorkspaceDataResult } from "@/hooks/use-company-workspace";
import { buildCompanyFinancialsCacheTags } from "@/lib/company-workspace-cache-tags";
import type { CompanyWorkspaceBootstrapResponse } from "@/lib/types";

type FinancialsPageProps = {
  params: { ticker: string } | Promise<{ ticker: string }>;
};

export default async function CompanyFinancialsPage({ params }: FinancialsPageProps) {
  const resolvedParams = await params;
  const ticker = normalizeTicker(resolvedParams.ticker);
  const initialWorkspaceData = await loadInitialFinancialsWorkspaceData(ticker);

  return <CompanyFinancialsClientPage ticker={ticker} initialWorkspaceData={initialWorkspaceData} />;
}

async function loadInitialFinancialsWorkspaceData(ticker: string): Promise<LoadCompanyWorkspaceDataResult | null> {
  const baseUrl = resolveServerBaseUrl();

  try {
    const response = await fetch(
      `${baseUrl}/backend/api/companies/${encodeURIComponent(ticker)}/workspace-bootstrap?financials_view=core_segments&include_earnings_summary=true`,
      {
        headers: {
          Accept: "application/json",
        },
        next: {
          revalidate: FINANCIALS_ROUTE_REVALIDATE_SECONDS,
          tags: buildCompanyFinancialsCacheTags(ticker),
        },
      }
    );

    if (!response.ok) {
      return null;
    }

    const bootstrap = (await response.json()) as CompanyWorkspaceBootstrapResponse;
    return {
      financialData: bootstrap.financials,
      briefData: bootstrap.brief,
      earningsSummaryData: bootstrap.earnings_summary,
      insiderData: bootstrap.insider_trades,
      institutionalData: bootstrap.institutional_holdings,
      insiderError: bootstrap.errors.insider,
      institutionalError: bootstrap.errors.institutional,
      activeJobId:
        bootstrap.financials.refresh.job_id ??
        bootstrap.brief?.refresh.job_id ??
        bootstrap.institutional_holdings?.refresh.job_id ??
        bootstrap.insider_trades?.refresh.job_id ??
        bootstrap.earnings_summary?.refresh.job_id ??
        null,
    };
  } catch {
    return null;
  }
}

function resolveServerBaseUrl(): string {
  const headerStore = headers();
  const host = headerStore.get("x-forwarded-host") ?? headerStore.get("host");
  const protocol = headerStore.get("x-forwarded-proto") ?? "http";

  if (!host) {
    throw new Error("Missing host header while loading financials route");
  }

  return `${protocol}://${host}`;
}

function normalizeTicker(rawTicker: string): string {
  try {
    return decodeURIComponent(rawTicker).trim().toUpperCase();
  } catch {
    return rawTicker.trim().toUpperCase();
  }
}
