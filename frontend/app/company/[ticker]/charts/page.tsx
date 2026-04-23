import { headers } from "next/headers";

import { CompanyChartsDashboard } from "@/components/company/charts-dashboard";
import { ProjectionStudio } from "@/components/company/projection-studio";
import type { CompanyChartsDashboardResponse } from "@/lib/types";

import { ChartsRetryButton } from "./charts-retry-button";

type DashboardMode = "outlook" | "studio";

type QueryParamValue = string | string[] | undefined;

type CompanyChartsPageProps = {
  params: { ticker: string } | Promise<{ ticker: string }>;
  searchParams?:
    | Record<string, QueryParamValue>
    | Promise<Record<string, QueryParamValue> | undefined>
    | undefined;
};

type ChartsLoadFailure = "not_found" | "service_error" | "temporary_error";

function resolveDashboardMode(rawMode: string | null, hasProjectionStudio: boolean): DashboardMode {
  if (rawMode === "studio" && hasProjectionStudio) {
    return "studio";
  }
  return "outlook";
}

export default async function CompanyChartsPage({ params, searchParams }: CompanyChartsPageProps) {
  const resolvedParams = await params;
  const resolvedSearchParams = (await searchParams) ?? {};
  const ticker = normalizeTicker(resolvedParams.ticker);
  const requestedAsOf = readQueryParam(resolvedSearchParams.as_of);
  const requestedMode = readQueryParam(resolvedSearchParams.mode);
  const chartsResult = await loadCompanyCharts(ticker, requestedAsOf);

  if (!chartsResult.ok) {
    return <ChartsErrorState failure={chartsResult.failure} />;
  }

  const data = chartsResult.data;
  const mode = resolveDashboardMode(requestedMode, Boolean(data.projection_studio));

  return (
    <>
      {mode === "studio" && data.projection_studio ? (
        <ProjectionStudio payload={data} studio={data.projection_studio} requestedAsOf={requestedAsOf} />
      ) : (
        <CompanyChartsDashboard payload={data} activeMode={mode} studioEnabled={Boolean(data.projection_studio)} requestedAsOf={requestedAsOf} />
      )}
    </>
  );
}

function normalizeTicker(rawTicker: string): string {
  try {
    return decodeURIComponent(rawTicker).trim().toUpperCase();
  } catch {
    return rawTicker.trim().toUpperCase();
  }
}

function readQueryParam(value: QueryParamValue): string | null {
  if (Array.isArray(value)) {
    return value[0] ?? null;
  }
  return value ?? null;
}

async function loadCompanyCharts(
  ticker: string,
  asOf: string | null
): Promise<{ ok: true; data: CompanyChartsDashboardResponse } | { ok: false; failure: ChartsLoadFailure }> {
  const params = new URLSearchParams();
  if (asOf?.trim()) {
    params.set("as_of", asOf.trim());
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const baseUrl = resolveServerBaseUrl();

  try {
    const response = await fetch(`${baseUrl}/backend/api/companies/${encodeURIComponent(ticker)}/charts${suffix}`, {
      cache: "no-store",
      headers: {
        Accept: "application/json",
      },
    });

    if (!response.ok) {
      if (response.status === 404) {
        return { ok: false, failure: "not_found" };
      }
      if (response.status >= 500) {
        return { ok: false, failure: "service_error" };
      }
      return { ok: false, failure: "temporary_error" };
    }

    const payload = (await response.json()) as CompanyChartsDashboardResponse;
    return { ok: true, data: payload };
  } catch {
    return { ok: false, failure: "temporary_error" };
  }
}

function resolveServerBaseUrl(): string {
  const headerStore = headers();
  const host = headerStore.get("x-forwarded-host") ?? headerStore.get("host");
  const protocol = headerStore.get("x-forwarded-proto") ?? "http";

  if (!host) {
    throw new Error("Missing host header while loading charts route");
  }

  return `${protocol}://${host}`;
}

function ChartsErrorState({ failure }: { failure: ChartsLoadFailure }) {
  const copy = getChartsErrorCopy(failure);

  return (
    <div className="charts-page-shell">
      <section className="charts-error-state" role="status" aria-live="polite">
        <div className="charts-page-chip">Charts</div>
        <h1 className="charts-page-title">Growth Outlook</h1>
        <p className="charts-summary-thesis">{copy.body}</p>
        <ChartsRetryButton />
      </section>
    </div>
  );
}

function getChartsErrorCopy(failure: ChartsLoadFailure): { body: string } {
  if (failure === "not_found") {
    return {
      body: "Charts for this company are unavailable or not yet prepared.",
    };
  }

  if (failure === "service_error") {
    return {
      body: "We are having a service problem loading charts. Please try again.",
    };
  }

  return {
    body: "We hit a temporary loading problem. Please try again.",
  };
}
