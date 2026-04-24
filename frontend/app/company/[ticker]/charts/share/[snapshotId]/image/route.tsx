import { ImageResponse } from "next/og";

import { ChartShareCard } from "@/components/company/chart-share-card";
import { CHART_SHARE_LAYOUTS, normalizeChartShareLayout } from "@/lib/chart-share";
import { loadCompanyChartsShareSnapshot } from "@/lib/chart-share-server";

export const runtime = "edge";

export async function GET(
  request: Request,
  context: { params: Promise<{ ticker: string; snapshotId: string }> }
) {
  const { ticker, snapshotId } = await context.params;
  const layout = normalizeChartShareLayout(new URL(request.url).searchParams.get("layout"));
  const record = await loadCompanyChartsShareSnapshot(ticker, snapshotId, { baseUrl: new URL(request.url).origin });

  if (!record) {
    return new Response("Snapshot not found", { status: 404 });
  }

  const dimensions = CHART_SHARE_LAYOUTS[layout];

  return new ImageResponse(<ChartShareCard snapshot={record.payload} layout={layout} />, {
    width: dimensions.width,
    height: dimensions.height,
  });
}
