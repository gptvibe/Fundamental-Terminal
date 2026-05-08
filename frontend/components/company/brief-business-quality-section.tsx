"use client";

import { memo, useMemo } from "react";
import dynamic from "next/dynamic";

import {
  EvidenceCard,
  ResearchBriefSection,
  ResearchBriefSectionStateBanner,
  ResearchBriefStateBlock,
  type ResearchBriefSectionStateKind,
} from "@/components/company/brief-primitives";
import type { ResearchBriefCue, SectionLink } from "@/components/company/brief-primitives";
import type {
  DataQualityDiagnosticsPayload,
  FinancialPayload,
  ProvenanceEntryPayload,
  SourceMixPayload,
} from "@/lib/types";

const FinancialQualitySummary = dynamic(
  () => import("@/components/company/financial-quality-summary").then((module) => module.FinancialQualitySummary),
  { ssr: false, loading: () => <div className="text-muted">Loading quality summary...</div> }
);
const MarginTrendChart = dynamic(
  () => import("@/components/charts/margin-trend-chart").then((module) => module.MarginTrendChart),
  { ssr: false, loading: () => <div className="text-muted">Loading margin trends...</div> }
);
const CashFlowWaterfallChart = dynamic(
  () => import("@/components/charts/cash-flow-waterfall-chart").then((module) => module.CashFlowWaterfallChart),
  { ssr: false, loading: () => <div className="text-muted">Loading cash flow bridge...</div> }
);

export const BriefBusinessQualitySection = memo(function BriefBusinessQualitySection({
  financials,
  loading,
  error,
  narrative,
  asOf,
  lastRefreshedAt,
  lastCheckedFinancials,
  provenance,
  sourceMix,
  confidenceFlags,
  diagnostics,
  strictOfficialMode,
  links,
  expanded,
  onToggle,
  onRetry,
}: {
  financials: FinancialPayload[];
  loading: boolean;
  error: string | null;
  narrative: string;
  asOf: string | null | undefined;
  lastRefreshedAt: string | null | undefined;
  lastCheckedFinancials: string | null | undefined;
  provenance: ProvenanceEntryPayload[] | null | undefined;
  sourceMix: SourceMixPayload | null | undefined;
  confidenceFlags: string[] | null | undefined;
  diagnostics: DataQualityDiagnosticsPayload | null | undefined;
  strictOfficialMode: boolean;
  links: SectionLink[];
  expanded: boolean;
  onToggle: () => void;
  onRetry?: (() => void) | null;
}) {
  const metricEvidence = useMemo(() => buildFinancialMetricEvidence(financials), [financials]);

  const cues: ResearchBriefCue[] = [
    {
      label: "Financial quality inputs",
      asOf,
      lastRefreshedAt,
      lastChecked: lastCheckedFinancials,
      provenance,
      sourceMix,
      confidenceFlags,
      diagnostics,
      strictOfficialMode,
      metricEvidence,
    },
  ];
  const hasQualityData = financials.length > 0;
  const sectionState: ResearchBriefSectionStateKind = loading && !hasQualityData
    ? "loading"
    : error && !hasQualityData
      ? "error"
      : error && hasQualityData
        ? "partial"
        : hasQualityData
          ? "ready"
          : "empty";

  return (
    <ResearchBriefSection
      id="business-quality"
      title="Business quality"
      question="Is the business getting stronger, weaker, or just noisier?"
      summary={narrative}
      cues={cues}
      links={links}
      expanded={expanded}
      onToggle={onToggle}
    >
      <ResearchBriefSectionStateBanner
        section="Business quality"
        state={sectionState}
        message={
          sectionState === "loading"
            ? "Loading annual profitability, margin, and cash-generation history from persisted filings."
            : sectionState === "error"
              ? error ?? "Business quality data is temporarily unavailable."
              : sectionState === "partial"
                ? `Some business-quality inputs are unavailable: ${error}. Use Full Financials and Earnings Detail routes for complete context.`
                : sectionState === "empty"
                  ? "Annual statement history is missing for this section. Open Full Financials and Earnings Detail to inspect filing coverage."
                  : "Business quality section is ready from persisted data."
        }
        links={links}
        onRetry={onRetry}
      />

      <EvidenceCard title="Quality summary" copy="A compact read on margins, profitability, leverage, growth, and share-count direction.">
        {error && !financials.length ? (
          <ResearchBriefStateBlock kind="error" kicker="Business quality" title="Unable to load quality summary" message={error} />
        ) : loading && !financials.length ? (
          <ResearchBriefStateBlock
            kind="loading"
            kicker="Business quality"
            title="Loading annual quality read"
            message="Preparing the latest persisted profitability, leverage, and growth view from annual filings."
          />
        ) : financials.length ? (
          <FinancialQualitySummary financials={financials} />
        ) : (
          <ResearchBriefStateBlock
            kind="empty"
            kicker="Business quality"
            title="No annual quality history yet"
            message="This summary appears after the cache includes enough annual filings to compare profitability and growth cleanly."
          />
        )}
      </EvidenceCard>

      <EvidenceCard title="Margin trends" copy="Gross, operating, net, and free-cash-flow margin direction from cached filings." className="is-wide">
        {error && !financials.length ? (
          <ResearchBriefStateBlock kind="error" kicker="Business quality" title="Unable to load margin trends" message={error} />
        ) : loading && !financials.length ? (
          <ResearchBriefStateBlock
            kind="loading"
            kicker="Business quality"
            title="Loading margin trends"
            message="Building the persisted margin history used to judge whether operating quality is improving or degrading."
          />
        ) : financials.length ? (
          <MarginTrendChart financials={financials} />
        ) : (
          <ResearchBriefStateBlock
            kind="empty"
            kicker="Business quality"
            title="No margin history yet"
            message="Margin trend charts appear once multiple comparable filing periods are cached for the company."
          />
        )}
      </EvidenceCard>

      <EvidenceCard title="Cash flow bridge" copy="How operating cash flow turns into free cash flow and how much room capital allocation still has." className="is-wide">
        {error && !financials.length ? (
          <ResearchBriefStateBlock kind="error" kicker="Business quality" title="Unable to load cash flow bridge" message={error} />
        ) : loading && !financials.length ? (
          <ResearchBriefStateBlock
            kind="loading"
            kicker="Business quality"
            title="Loading cash flow bridge"
            message="Preparing the persisted cash flow waterfall used to separate accounting noise from cash-generation strength."
          />
        ) : financials.length ? (
          <CashFlowWaterfallChart financials={financials} />
        ) : (
          <ResearchBriefStateBlock
            kind="empty"
            kicker="Business quality"
            title="No cash flow bridge yet"
            message="The bridge populates when cached filings include operating cash flow, capex, and capital allocation inputs."
          />
        )}
      </EvidenceCard>
    </ResearchBriefSection>
  );
});

function buildFinancialMetricEvidence(financials: FinancialPayload[]) {
  const latest = [...financials]
    .filter((row) => Boolean(row.period_end))
    .sort((left, right) => (left.period_end < right.period_end ? 1 : -1))[0];

  if (!latest?.reconciliation?.comparisons?.length) {
    return [];
  }

  const preferredMetricKeys = ["revenue", "operating_income", "net_income", "free_cash_flow"];
  const byKey = new Map(latest.reconciliation.comparisons.map((comparison) => [comparison.metric_key, comparison]));
  const selectedComparisons = preferredMetricKeys
    .map((key) => byKey.get(key))
    .filter((comparison): comparison is NonNullable<typeof comparison> => Boolean(comparison));
  const comparisons = selectedComparisons.length ? selectedComparisons : latest.reconciliation.comparisons.slice(0, 4);

  return comparisons.map((comparison) => {
    const fact = comparison.companyfacts_fact ?? comparison.filing_parser_fact;
    return {
      label: humanizeMetricKey(comparison.metric_key),
      source_id: fact?.source ?? null,
      as_of: latest.period_end,
      accession_number: fact?.accession_number ?? latest.reconciliation?.matched_accession_number ?? null,
      taxonomy: fact?.taxonomy ?? null,
      tag: fact?.tag ?? null,
      confidence_flags:
        comparison.confidence_penalty != null && comparison.confidence_penalty > 0 ? ["reconciliation_penalty"] : [],
      diagnostics: comparison.status,
      formula_note:
        comparison.status === "match"
          ? "Companyfacts and parser values match for this metric."
          : `Reconciliation status: ${comparison.status}`,
    };
  });
}

function humanizeMetricKey(value: string): string {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
}
