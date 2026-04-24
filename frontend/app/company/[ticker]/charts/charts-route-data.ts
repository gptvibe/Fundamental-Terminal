import type { Metadata } from "next";
import { headers } from "next/headers";

import { buildChartsSourcePath } from "@/lib/chart-share";
import type { CompanyChartsDashboardResponse } from "@/lib/types";

export type DashboardMode = "outlook" | "studio";
export type ChartsLoadFailure = "not_found" | "service_error" | "temporary_error";
export type QueryParamValue = string | string[] | undefined;

export const CHARTS_ROUTE_REVALIDATE_SECONDS = 20;

export type ChartsRouteQuery = {
  asOf: string | null;
  requestedMode: string | null;
  requestedScenarioId: string | null;
};

export function normalizeTicker(rawTicker: string): string {
  try {
    return decodeURIComponent(rawTicker).trim().toUpperCase();
  } catch {
    return rawTicker.trim().toUpperCase();
  }
}

export function readQueryParam(value: QueryParamValue): string | null {
  if (Array.isArray(value)) {
    return value[0] ?? null;
  }
  return value ?? null;
}

export function resolveDashboardMode(rawMode: string | null, hasProjectionStudio: boolean, requestedScenarioId: string | null): DashboardMode {
  if ((rawMode === "studio" || requestedScenarioId) && hasProjectionStudio) {
    return "studio";
  }
  return "outlook";
}

export async function loadCompanyCharts(
  baseUrl: string,
  ticker: string,
  asOf: string | null
): Promise<{ ok: true; data: CompanyChartsDashboardResponse } | { ok: false; failure: ChartsLoadFailure }> {
  const params = new URLSearchParams();
  if (asOf?.trim()) {
    params.set("as_of", asOf.trim());
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";

  try {
    const response = await fetch(`${baseUrl}/backend/api/companies/${encodeURIComponent(ticker)}/charts${suffix}`, {
      headers: {
        Accept: "application/json",
      },
      next: {
        revalidate: CHARTS_ROUTE_REVALIDATE_SECONDS,
        tags: buildChartsCacheTags(ticker, asOf),
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

export async function loadCompanyChartsRouteData(
  ticker: string,
  asOf: string | null
): Promise<{ ok: true; data: CompanyChartsDashboardResponse } | { ok: false; failure: ChartsLoadFailure }> {
  return loadCompanyCharts(resolveServerBaseUrl(), ticker, asOf);
}

export function resolveServerBaseUrl(): string {
  const headerStore = headers();
  const host = headerStore.get("x-forwarded-host") ?? headerStore.get("host");
  const protocol = headerStore.get("x-forwarded-proto") ?? "http";

  if (!host) {
    throw new Error("Missing host header while loading charts route");
  }

  return `${protocol}://${host}`;
}

export function buildCompanyChartsMetadata(
  ticker: string,
  query: ChartsRouteQuery,
  payload: CompanyChartsDashboardResponse,
  baseUrl: string
): Metadata {
  const mode = resolveDashboardMode(query.requestedMode, Boolean(payload.projection_studio), query.requestedScenarioId);
  const companyLabel = payload.company?.name ?? ticker;
  const routeLabel = mode === "studio" && payload.projection_studio ? "Projection Studio" : payload.title;
  const freshness = payload.summary.freshness_badges[0] ?? null;
  const source = payload.summary.source_badges[0] ?? "Official filings";
  const descriptionParts = [
    mode === "studio" && payload.projection_studio
      ? payload.chart_spec?.studio?.summary ?? "Interactive projection studio on top of the SEC-derived base forecast."
      : payload.summary.thesis ?? payload.summary.headline,
    payload.forecast_methodology.confidence_label ?? null,
    freshness,
    source,
  ].filter((value): value is string => Boolean(value));
  const description = descriptionParts.join(" · ");
  const canonicalUrl = new URL(buildCompanyChartsCanonicalPath(ticker, query), baseUrl).toString();
  const imageUrl = new URL(buildCompanyChartsOpenGraphImagePath(ticker, query.asOf), baseUrl).toString();

  return {
    title: `${companyLabel} ${routeLabel}`,
    description,
    alternates: { canonical: canonicalUrl },
    openGraph: {
      title: `${companyLabel} ${routeLabel}`,
      description,
      url: canonicalUrl,
      images: [imageUrl],
    },
    twitter: {
      card: "summary_large_image",
      title: `${companyLabel} ${routeLabel}`,
      description,
      images: [imageUrl],
    },
  };
}

export function buildCompanyChartsCanonicalPath(ticker: string, query: ChartsRouteQuery): string {
  const params = new URLSearchParams();
  if (query.asOf?.trim()) {
    params.set("as_of", query.asOf.trim());
  }
  if (query.requestedScenarioId?.trim()) {
    params.set("mode", "studio");
    params.set("scenario", query.requestedScenarioId.trim());
  } else if (query.requestedMode === "studio") {
    params.set("mode", "studio");
  }

  const suffix = params.toString() ? `?${params.toString()}` : "";
  return `${buildChartsSourcePath(ticker, "outlook").replace(/\?mode=outlook$/, "")}${suffix}`;
}

export function buildCompanyChartsOpenGraphImagePath(ticker: string, asOf: string | null): string {
  const params = new URLSearchParams();
  if (asOf?.trim()) {
    params.set("as_of", asOf.trim());
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return `/company/${encodeURIComponent(ticker)}/charts/opengraph-image${suffix}`;
}

function buildChartsCacheTags(ticker: string, asOf: string | null): string[] {
  const baseTag = `company-charts:${ticker}`;
  return asOf?.trim() ? [baseTag, `${baseTag}:as-of:${asOf.trim()}`] : [baseTag, `${baseTag}:latest`];
}