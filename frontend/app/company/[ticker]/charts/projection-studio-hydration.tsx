"use client";

import { useEffect, useState, type ComponentType } from "react";

import type { CompanyChartsDashboardResponse } from "@/lib/types";

type ProjectionStudioProps = {
  payload: CompanyChartsDashboardResponse;
  studio: NonNullable<CompanyChartsDashboardResponse["projection_studio"]>;
  requestedAsOf?: string | null;
  requestedScenarioId?: string | null;
};

type ProjectionStudioComponent = ComponentType<ProjectionStudioProps>;

export function ProjectionStudioHydration({ payload, studio, requestedAsOf = null, requestedScenarioId = null }: ProjectionStudioProps) {
  const [LoadedComponent, setLoadedComponent] = useState<ProjectionStudioComponent | null>(null);

  useEffect(() => {
    let cancelled = false;

    void import("@/components/company/projection-studio").then((module) => {
      if (!cancelled) {
        setLoadedComponent(() => module.ProjectionStudio);
      }
    });

    return () => {
      cancelled = true;
    };
  }, []);

  if (LoadedComponent) {
    return <LoadedComponent payload={payload} studio={studio} requestedAsOf={requestedAsOf} requestedScenarioId={requestedScenarioId} />;
  }

  return <ProjectionStudioLoadingShell payload={payload} />;
}

function ProjectionStudioLoadingShell({ payload }: { payload: CompanyChartsDashboardResponse }) {
  const companyLabel = payload.company?.name ?? payload.company?.ticker ?? "Projection Studio";
  const trustLabel = payload.forecast_methodology.confidence_label ?? "Forecast trust is still warming up.";
  const freshness = payload.summary.freshness_badges.join(" · ") || "Freshness indicators will appear once the interactive shell loads.";
  const sources = payload.summary.source_badges.join(" · ") || "Official filings";

  return (
    <div className="charts-page-shell">
      <section className="charts-page-hero charts-page-hero-loading" aria-label="Projection Studio loading shell">
        <div className="charts-page-hero-copy">
          <div className="charts-page-kicker-row">
            <span className="charts-page-chip">Charts</span>
            <span className="charts-page-chip charts-page-chip-subtle">Projection Studio</span>
          </div>
          <h1 className="charts-page-title">{companyLabel}</h1>
          <p className="charts-summary-thesis">
            Interactive Projection Studio is loading. The base forecast, freshness, and source indicators are already available from the cached server snapshot.
          </p>
        </div>
        <div className="charts-page-hero-side charts-page-hero-summary-card">
          <div className="charts-page-hero-label">Projection Studio</div>
          <p className="charts-page-hero-status">{payload.build_status}</p>
          <div className="charts-summary-data-lines">
            <div className="charts-summary-data-line">
              <span className="charts-summary-data-line-label">Trust</span>
              <span className="charts-summary-data-line-value">{trustLabel}</span>
            </div>
            <div className="charts-summary-data-line">
              <span className="charts-summary-data-line-label">Freshness</span>
              <span className="charts-summary-data-line-value">{freshness}</span>
            </div>
            <div className="charts-summary-data-line">
              <span className="charts-summary-data-line-label">Sources</span>
              <span className="charts-summary-data-line-value">{sources}</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}