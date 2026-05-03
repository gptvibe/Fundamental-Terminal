import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ChartShareCard } from "@/components/company/chart-share-card";
import { CHART_SHARE_LAYOUTS, buildCompanyChartsShareImagePath } from "@/lib/chart-share";
import { buildCompanyChartsShareMetadata, loadCompanyChartsShareSnapshot, resolveChartShareServerBaseUrl } from "@/lib/chart-share-server";

import styles from "./page.module.css";

type CompanyChartsSharePageProps = {
  params: Promise<{ ticker: string; snapshotId: string }>;
};

export async function generateMetadata({ params }: CompanyChartsSharePageProps): Promise<Metadata> {
  const { ticker, snapshotId } = await params;
  const baseUrl = resolveChartShareServerBaseUrl();
  const record = await loadCompanyChartsShareSnapshot(ticker, snapshotId);
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
  const record = await loadCompanyChartsShareSnapshot(ticker, snapshotId);

  if (!record) {
    notFound();
  }

  return (
    <main className={styles.page}>
      <div className={styles.shell}>
        <div className={styles.header}>
          <div>
            <div className={styles.eyebrow}>Charts Share Snapshot</div>
            <h1 className={styles.title}>{record.payload.company_name ?? record.ticker}</h1>
            <p className={styles.subtitle}>{record.payload.title}</p>
          </div>
          <Link href={record.payload.source_path} className={styles.liveLink}>
            Open live charts
          </Link>
        </div>

        <div className={styles.cardFrame}>
          <ChartShareCard snapshot={record.payload} layout="landscape" />
        </div>

        <div className={styles.downloadLinks}>
          {Object.entries(CHART_SHARE_LAYOUTS).map(([layoutKey, config]) => (
            <a
              key={layoutKey}
              href={buildCompanyChartsShareImagePath(record.share_path, layoutKey as keyof typeof CHART_SHARE_LAYOUTS)}
              className={styles.downloadLink}
            >
              {config.label} PNG
            </a>
          ))}
        </div>
      </div>
    </main>
  );
}
