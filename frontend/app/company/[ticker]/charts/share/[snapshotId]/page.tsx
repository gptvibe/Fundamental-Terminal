import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ChartShareCard } from "@/components/company/chart-share-card";
import { CHART_SHARE_LAYOUTS, buildCompanyChartsShareImagePath } from "@/lib/chart-share";
import { buildCompanyChartsShareMetadata, loadCompanyChartsShareSnapshot, resolveChartShareServerBaseUrl } from "@/lib/chart-share-server";

type CompanyChartsSharePageProps = {
  params: Promise<{ ticker: string; snapshotId: string }>;
};

export async function generateMetadata({ params }: CompanyChartsSharePageProps): Promise<Metadata> {
  const { ticker, snapshotId } = await params;
  const baseUrl = resolveChartShareServerBaseUrl();
  const record = await loadCompanyChartsShareSnapshot(ticker, snapshotId, { baseUrl });
  if (!record) {
    return {
      title: "Charts Share Snapshot",
      description: "Shareable company chart snapshot.",
    };
  }
  return buildCompanyChartsShareMetadata(record, baseUrl);
}

export default async function CompanyChartsSharePage({ params }: CompanyChartsSharePageProps) {
  const { ticker, snapshotId } = await params;
  const baseUrl = resolveChartShareServerBaseUrl();
  const record = await loadCompanyChartsShareSnapshot(ticker, snapshotId, { baseUrl });

  if (!record) {
    notFound();
  }

  return (
    <main style={{ minHeight: "100vh", background: "#07111b", color: "#f7f4ed", padding: "32px 20px" }}>
      <div style={{ maxWidth: 1180, margin: "0 auto", display: "flex", flexDirection: "column", gap: 22 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 20, flexWrap: "wrap", alignItems: "center" }}>
          <div>
            <div style={{ fontSize: 14, textTransform: "uppercase", letterSpacing: 1.2, color: "#8ea5b7" }}>Charts Share Snapshot</div>
            <h1 style={{ margin: "8px 0 6px", fontSize: 36, lineHeight: 1.05 }}>{record.payload.company_name ?? record.ticker}</h1>
            <p style={{ margin: 0, color: "#cad7e3" }}>{record.payload.title}</p>
          </div>
          <Link href={record.payload.source_path} style={{ color: "#8fe5b4", textDecoration: "none", fontWeight: 600 }}>
            Open live charts
          </Link>
        </div>

        <div style={{ borderRadius: 28, overflow: "hidden", border: "1px solid rgba(255,255,255,0.08)" }}>
          <ChartShareCard snapshot={record.payload} layout="landscape" />
        </div>

        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
          {Object.entries(CHART_SHARE_LAYOUTS).map(([layoutKey, config]) => (
            <a
              key={layoutKey}
              href={buildCompanyChartsShareImagePath(record.share_path, layoutKey as keyof typeof CHART_SHARE_LAYOUTS)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                padding: "10px 14px",
                borderRadius: 999,
                color: "#f7f4ed",
                textDecoration: "none",
                background: "rgba(255,255,255,0.07)",
                border: "1px solid rgba(255,255,255,0.1)",
              }}
            >
              {config.label} PNG
            </a>
          ))}
        </div>
      </div>
    </main>
  );
}
