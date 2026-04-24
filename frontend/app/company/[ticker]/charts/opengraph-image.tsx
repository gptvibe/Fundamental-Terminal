import { ImageResponse } from "next/og";

import { ChartShareCard } from "@/components/company/chart-share-card";
import { buildOutlookChartShareSnapshot } from "@/lib/chart-share";

import { loadCompanyChartsRouteData, normalizeTicker } from "./charts-route-data";

export const runtime = "edge";
export const alt = "Company growth outlook";
export const size = {
  width: 1200,
  height: 675,
};
export const contentType = "image/png";

type CompanyChartsOpenGraphImageProps = {
  params: Promise<{ ticker: string }>;
};

export default async function CompanyChartsOpenGraphImage({ params }: CompanyChartsOpenGraphImageProps) {
  const { ticker: rawTicker } = await params;
  const ticker = normalizeTicker(rawTicker);
  const chartsResult = await loadCompanyChartsRouteData(ticker, null);

  if (!chartsResult.ok) {
    return new Response("Charts are unavailable or still warming up.", { status: 404 });
  }

  return new ImageResponse(<ChartShareCard snapshot={buildOutlookChartShareSnapshot(chartsResult.data)} layout="landscape" />, size);
}