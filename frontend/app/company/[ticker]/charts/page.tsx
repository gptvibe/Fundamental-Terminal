"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";

import { CompanyChartsDashboard } from "@/components/company/charts-dashboard";
import { ProjectionStudio } from "@/components/company/projection-studio";
import { getCompanyCharts } from "@/lib/api";
import type { CompanyChartsDashboardResponse } from "@/lib/types";

type DashboardMode = "outlook" | "studio";

function resolveDashboardMode(rawMode: string | null, hasProjectionStudio: boolean): DashboardMode {
  if (rawMode === "studio" && hasProjectionStudio) {
    return "studio";
  }
  return "outlook";
}

export default function CompanyChartsPage() {
  const params = useParams<{ ticker: string }>();
  const searchParams = useSearchParams();
  const ticker = decodeURIComponent(params.ticker).toUpperCase();
  const [data, setData] = useState<CompanyChartsDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Determine requested mode from URL; default to outlook
  const requestedMode = searchParams?.get("mode") ?? null;
  const mode = resolveDashboardMode(requestedMode, Boolean(data?.projection_studio));

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        const payload = await getCompanyCharts(ticker);
        if (!cancelled) {
          setData(payload);
        }
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError instanceof Error ? nextError.message : "Unable to load charts");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  if (loading && !data) {
    return (
      <div className="charts-page-shell charts-page-shell-loading" aria-label="Charts loading state">
        <div className="charts-loading-hero" />
        <div className="charts-loading-dashboard-grid">
          <div className="charts-loading-panel charts-loading-summary-panel" />
          {Array.from({ length: 6 }, (_, index) => (
            <div key={index} className="charts-loading-card charts-loading-card-compact" />
          ))}
        </div>
        <div className="charts-loading-card-grid">
          {Array.from({ length: 3 }, (_, index) => (
            <div key={index} className="charts-loading-card" />
          ))}
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="charts-page-shell">
        <section className="charts-error-state">
          <div className="charts-page-chip">Charts</div>
          <h1 className="charts-page-title">Growth Outlook</h1>
          <p className="charts-summary-thesis">{error}</p>
        </section>
      </div>
    );
  }

  if (!data) {
    return null;
  }

  return (
    <>
      {mode === "studio" && data.projection_studio ? (
        <ProjectionStudio payload={data} studio={data.projection_studio} />
      ) : (
        <CompanyChartsDashboard payload={data} activeMode={mode} studioEnabled={Boolean(data.projection_studio)} />
      )}
    </>
  );
}
