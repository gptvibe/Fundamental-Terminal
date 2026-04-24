import type { Metadata } from "next";

import { CompanyChartsDashboard } from "@/components/company/charts-dashboard";

import { ChartsRetryButton } from "./charts-retry-button";
import {
  buildCompanyChartsMetadata,
  type ChartsLoadFailure,
  type QueryParamValue,
  loadCompanyChartsRouteData,
  normalizeTicker,
  readQueryParam,
  resolveDashboardMode,
  resolveServerBaseUrl,
} from "./charts-route-data";
import { ProjectionStudioHydration } from "./projection-studio-hydration";

type CompanyChartsPageProps = {
  params: { ticker: string } | Promise<{ ticker: string }>;
  searchParams?:
    | Record<string, QueryParamValue>
    | Promise<Record<string, QueryParamValue> | undefined>
    | undefined;
};

export async function generateMetadata({ params, searchParams }: CompanyChartsPageProps): Promise<Metadata> {
  const resolvedParams = await params;
  const resolvedSearchParams = (await searchParams) ?? {};
  const ticker = normalizeTicker(resolvedParams.ticker);
  const query = {
    asOf: readQueryParam(resolvedSearchParams.as_of),
    requestedMode: readQueryParam(resolvedSearchParams.mode),
    requestedScenarioId: readQueryParam(resolvedSearchParams.scenario),
  };
  const chartsResult = await loadCompanyChartsRouteData(ticker, query.asOf);

  if (!chartsResult.ok) {
    return {
      title: `${ticker} Growth Outlook`,
      description: "Company charts and projection studio.",
    };
  }

  return buildCompanyChartsMetadata(ticker, query, chartsResult.data, resolveServerBaseUrl());
}

export default async function CompanyChartsPage({ params, searchParams }: CompanyChartsPageProps) {
  const resolvedParams = await params;
  const resolvedSearchParams = (await searchParams) ?? {};
  const ticker = normalizeTicker(resolvedParams.ticker);
  const requestedAsOf = readQueryParam(resolvedSearchParams.as_of);
  const requestedMode = readQueryParam(resolvedSearchParams.mode);
  const requestedScenarioId = readQueryParam(resolvedSearchParams.scenario);
  const chartsResult = await loadCompanyChartsRouteData(ticker, requestedAsOf);

  if (!chartsResult.ok) {
    return <ChartsErrorState failure={chartsResult.failure} />;
  }

  const data = chartsResult.data;
  const mode = resolveDashboardMode(requestedMode, Boolean(data.projection_studio), requestedScenarioId);

  return mode === "studio" && data.projection_studio ? (
    <ProjectionStudioHydration
      payload={data}
      studio={data.projection_studio}
      requestedAsOf={requestedAsOf}
      requestedScenarioId={requestedScenarioId}
    />
  ) : (
    <CompanyChartsDashboard
      payload={data}
      activeMode={mode}
      studioEnabled={Boolean(data.projection_studio)}
      requestedAsOf={requestedAsOf}
    />
  );
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