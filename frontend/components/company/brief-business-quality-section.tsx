"use client";

import dynamic from "next/dynamic";

import { EvidenceCard, ResearchBriefSection, ResearchBriefStateBlock } from "@/components/company/brief-primitives";
import type { ResearchBriefCue, SectionLink } from "@/components/company/brief-primitives";
import type { FinancialPayload, SourceMixPayload, ProvenanceEntryPayload } from "@/lib/types";

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

export function BriefBusinessQualitySection({
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
  links,
  expanded,
  onToggle,
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
  links: SectionLink[];
  expanded: boolean;
  onToggle: () => void;
}) {
  const cues: ResearchBriefCue[] = [
    {
      label: "Financial quality inputs",
      asOf,
      lastRefreshedAt,
      lastChecked: lastCheckedFinancials,
      provenance,
      sourceMix,
      confidenceFlags,
    },
  ];

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

      <EvidenceCard title="Margin trends" copy="Gross, operating, net, and free-cash-flow margin direction from cached filings.">
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

      <EvidenceCard title="Cash flow bridge" copy="How operating cash flow turns into free cash flow and how much room capital allocation still has.">
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
}
