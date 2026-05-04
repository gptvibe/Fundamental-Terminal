"use client";

import type { ReactNode } from "react";

import { SourceFreshnessTimeline } from "@/components/company/source-freshness-timeline";
import { Panel } from "@/components/ui/panel";
import { formatDate } from "@/lib/format";
import type {
  CacheState,
  CompanyFinancialsResponse,
  CompanyPayload,
  FilingTimelineItemPayload,
  ProvenanceEntryPayload,
  RefreshState,
  SourceMixPayload,
} from "@/lib/types";

type CompanyOverviewStatusStripProps = {
  asOf?: string | null;
  lastRefreshedAt?: string | null;
  sourceMix?: SourceMixPayload | null;
  provenance?: ProvenanceEntryPayload[] | null;
  refreshState?: RefreshState | null;
  cacheState?: CacheState | null;
  hasWarnings?: boolean;
};

type CompanyOverviewDataQualitySourcesSectionProps = {
  ticker: string;
  company?: CompanyPayload | null;
  refreshState?: RefreshState | null;
  activeJobId?: string | null;
  financialsResponse?: CompanyFinancialsResponse | null;
  filingTimeline?: FilingTimelineItemPayload[] | null;
  provenance?: ProvenanceEntryPayload[] | null;
  sourceMix?: SourceMixPayload | null;
  asOf?: string | null;
  lastRefreshedAt?: string | null;
  fallbackLabels?: string[];
  warmupPanel: ReactNode;
  partialErrors?: ReactNode;
  helpAppendix?: ReactNode;
};

export function CompanyOverviewStatusStrip({
  asOf,
  lastRefreshedAt,
  sourceMix,
  provenance,
  refreshState,
  cacheState,
  hasWarnings = false,
}: CompanyOverviewStatusStripProps) {
  const primarySources = sourceMix?.primary_source_ids?.length ?? 0;
  const fallbackSources = sourceMix?.fallback_source_ids?.length ?? 0;
  const provenanceCount = provenance?.length ?? 0;
  const refreshLabel = refreshState?.job_id ? "Refresh queued" : "No active refresh";

  return (
    <section className="company-overview-status-strip" aria-label="Top provenance and freshness strip">
      <div className="company-source-ribbon" aria-label="Compact provenance and freshness">
        <div className="company-source-chip tone-cyan">
          <span className="company-source-chip-label">As of</span>
          <span className="company-source-chip-value">{asOf ? formatDate(asOf) : "Pending"}</span>
        </div>
        <div className="company-source-chip tone-cyan">
          <span className="company-source-chip-label">Last refresh</span>
          <span className="company-source-chip-value">{lastRefreshedAt ? formatDate(lastRefreshedAt) : "Pending"}</span>
        </div>
        <div className="company-source-chip tone-green">
          <span className="company-source-chip-label">Source mix</span>
          <span className="company-source-chip-value">
            {primarySources.toLocaleString()} primary · {fallbackSources.toLocaleString()} fallback
          </span>
        </div>
        <div className="company-source-chip tone-gold">
          <span className="company-source-chip-label">Provenance rows</span>
          <span className="company-source-chip-value">{provenanceCount.toLocaleString()}</span>
        </div>
        <div className="company-source-chip tone-cyan">
          <span className="company-source-chip-label">Status</span>
          <span className="company-source-chip-value">{refreshLabel}</span>
        </div>
        {cacheState ? (
          <div className={`company-source-chip tone-${cacheState === "stale" || cacheState === "missing" ? "red" : "green"}`}>
            <span className="company-source-chip-label">Cache</span>
            <span className="company-source-chip-value">{cacheState}</span>
          </div>
        ) : null}
        {hasWarnings ? (
          <div className="company-source-chip tone-red" role="status" aria-live="polite">
            <span className="company-source-chip-label">Warning</span>
            <span className="company-source-chip-value">Review stale or partial inputs below</span>
          </div>
        ) : null}
      </div>
    </section>
  );
}

export function CompanyOverviewDataQualitySourcesSection({
  ticker,
  company,
  refreshState,
  activeJobId,
  financialsResponse,
  filingTimeline,
  provenance,
  sourceMix,
  asOf,
  lastRefreshedAt,
  fallbackLabels = [],
  warmupPanel,
  partialErrors,
  helpAppendix,
}: CompanyOverviewDataQualitySourcesSectionProps) {
  return (
    <section className="company-overview-data-quality" aria-label="Data quality and sources">
      <Panel
        title="Data quality & sources"
        subtitle="Verbose provenance, cache/build diagnostics, and fallback notes live here so the primary viewport stays focused on decisions."
        variant="subtle"
      >
        <div className="company-overview-data-quality-stack">
          <details className="subtle-details">
            <summary>Source freshness timeline</summary>
            <div className="subtle-details-body company-overview-data-quality-body">
              <SourceFreshnessTimeline
                ticker={ticker}
                company={company}
                refreshState={refreshState}
                activeJobId={activeJobId}
                financialsResponse={financialsResponse}
                filingTimeline={filingTimeline}
                asOf={asOf}
                lastRefreshedAt={lastRefreshedAt}
                provenance={provenance}
                sourceMix={sourceMix}
              />
            </div>
          </details>

          {warmupPanel ? (
            <details className="subtle-details" open>
              <summary>Brief build and cache diagnostics</summary>
              <div className="subtle-details-body company-overview-data-quality-body">{warmupPanel}</div>
            </details>
          ) : null}

          {partialErrors ? (
            <details className="subtle-details">
              <summary>Partial data and fallback warnings</summary>
              <div className="subtle-details-body company-overview-data-quality-body">{partialErrors}</div>
            </details>
          ) : null}

          <details className="subtle-details">
            <summary>Methodology and source policy</summary>
            <div className="subtle-details-body company-overview-data-quality-body">
              <p className="text-muted">
                Core fundamentals remain official-source-first. Fallback inputs are explicitly labeled and constrained to supporting context.
                Severe stale or missing data warnings remain attached to the relevant chart or table section.
              </p>
              {fallbackLabels.length ? (
                <div className="research-brief-partial-errors">
                  {fallbackLabels.map((label) => (
                    <span key={label} className="pill">
                      {label}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-muted">No commercial fallback labels are active for this company snapshot.</p>
              )}
            </div>
          </details>

          {helpAppendix ? (
            <details className="subtle-details">
              <summary>Help and metric glossary</summary>
              <div className="subtle-details-body company-overview-data-quality-body">{helpAppendix}</div>
            </details>
          ) : null}
        </div>
      </Panel>
    </section>
  );
}
