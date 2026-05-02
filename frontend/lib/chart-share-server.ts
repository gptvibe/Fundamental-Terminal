import type { Metadata } from "next";
import { headers } from "next/headers";

import { buildCompanyChartsShareImageUrl } from "@/lib/chart-share";
import type { CompanyChartsShareSnapshotRecordPayload } from "@/lib/types";

export async function loadCompanyChartsShareSnapshot(
  ticker: string,
  snapshotId: string,
  options?: { backendApiBaseUrl?: string }
): Promise<CompanyChartsShareSnapshotRecordPayload | null> {
  const backendApiBaseUrl = options?.backendApiBaseUrl ?? resolveBackendApiBaseUrl();
  const response = await fetch(
    `${backendApiBaseUrl}/api/companies/${encodeURIComponent(ticker)}/charts/share-snapshots/${encodeURIComponent(snapshotId)}`,
    {
      cache: "no-store",
      headers: {
        Accept: "application/json",
      },
    }
  );

  if (!response.ok) {
    return null;
  }

  return (await response.json()) as CompanyChartsShareSnapshotRecordPayload;
}

export function resolveChartShareServerBaseUrl(): string {
  const headerStore = headers();
  const host = headerStore.get("x-forwarded-host") ?? headerStore.get("host");
  const protocol = headerStore.get("x-forwarded-proto") ?? "http";

  if (!host) {
    throw new Error("Missing host header while resolving chart share base URL");
  }

  return `${protocol}://${host}`;
}

function resolveBackendApiBaseUrl(): string {
  return process.env.BACKEND_API_BASE_URL ?? "http://127.0.0.1:8000";
}

export function buildCompanyChartsShareMetadata(
  record: CompanyChartsShareSnapshotRecordPayload,
  baseUrl: string
): Metadata {
  const companyLabel = record.payload.company_name ?? record.ticker;
  const title = `${companyLabel} ${record.payload.title}`;
  const description =
    record.mode === "studio"
      ? `${record.payload.trust_label ?? "Projection Studio snapshot"} · ${record.payload.source_badge}`
      : `${record.payload.trust_label ?? "Growth outlook snapshot"} · ${record.payload.source_badge}`;
  const imageUrl = buildCompanyChartsShareImageUrl(record.share_path, "landscape", baseUrl);
  const canonicalUrl = new URL(record.share_path, baseUrl).toString();

  return {
    title,
    description,
    alternates: { canonical: canonicalUrl },
    openGraph: {
      title,
      description,
      url: canonicalUrl,
      images: [imageUrl],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [imageUrl],
    },
  };
}
