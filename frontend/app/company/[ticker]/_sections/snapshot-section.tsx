"use client";

import { memo } from "react";
import dynamic from "next/dynamic";

import { EvidenceCard, PanelErrorBoundary, ResearchBriefSection, ResearchBriefStateBlock } from "@/components/company/brief-primitives";
import type { SectionLink } from "@/components/company/brief-primitives";
import { CompanyMetricGrid } from "@/components/layout/company-research-header";
import { formatPercent } from "@/lib/format";
import type { FinancialPayload, FundamentalsTrendPoint, PriceHistoryPoint, SegmentAnalysisPayload } from "@/lib/types";

import { formatCompactCurrency } from "../_lib/research-brief-utils";

const PriceFundamentalsModule = dynamic(
  () => import("@/components/charts/price-fundamentals-module").then((module) => module.PriceFundamentalsModule),
  {
    ssr: false,
    loading: () => (
      <div className="research-brief-state research-brief-state-loading">
        <div className="grid-empty-kicker">Snapshot</div>
        <div className="grid-empty-title">Loading price and fundamentals</div>
        <div className="grid-empty-copy">Preparing the persisted price-versus-fundamentals comparison.</div>
      </div>
    ),
  }
);

const BusinessSegmentBreakdown = dynamic(
  () => import("@/components/charts/business-segment-breakdown").then((module) => module.BusinessSegmentBreakdown),
  {
    ssr: false,
    loading: () => (
      <div className="research-brief-state research-brief-state-loading">
        <div className="grid-empty-kicker">Snapshot</div>
        <div className="grid-empty-title">Loading segment breakdown</div>
        <div className="grid-empty-copy">Reading the latest persisted segment and geography disclosures.</div>
      </div>
    ),
  }
);

type SnapshotSectionProps = {
  loading: boolean;
  priceHistory: PriceHistoryPoint[];
  fundamentalsTrendData: FundamentalsTrendPoint[];
  latestFinancial: FinancialPayload | null;
  financials: FinancialPayload[];
  topSegment: FinancialPayload["segment_breakdown"][number] | null;
  latestAlertCount: number;
  segmentAnalysis: SegmentAnalysisPayload | null | undefined;
  narrative: string;
  links: SectionLink[];
  expanded: boolean;
  onToggle: () => void;
};

export const SnapshotSection = memo(function SnapshotSection({
  loading,
  priceHistory,
  fundamentalsTrendData,
  latestFinancial,
  financials,
  topSegment,
  latestAlertCount,
  segmentAnalysis,
  narrative,
  links,
  expanded,
  onToggle,
}: SnapshotSectionProps) {
  return (
    <ResearchBriefSection
      id="snapshot"
      title="Snapshot"
      question="What matters before I read further?"
      summary={null}
      cues={[]}
      links={links}
      expanded={expanded}
      onToggle={onToggle}
    >
      <EvidenceCard
        title="Price vs operating momentum"
        copy="Operating history stays SEC-first; market context remains explicitly labeled when a commercial fallback is involved."
        className="is-wide"
      >
        {loading && !priceHistory.length && !fundamentalsTrendData.length ? (
          <ResearchBriefStateBlock
            kind="loading"
            kicker="Snapshot"
            title="Loading momentum view"
            message="Preparing the persisted price-versus-fundamentals comparison used at the top of the brief."
          />
        ) : priceHistory.length || fundamentalsTrendData.length ? (
          <PanelErrorBoundary kicker="Snapshot" title="Unable to render momentum view">
            <PriceFundamentalsModule
              priceData={priceHistory}
              fundamentalsData={fundamentalsTrendData}
              title="Price and operating momentum"
              subtitle="Start with price action, revenue growth, EPS trend, and free-cash-flow direction before diving into specialist evidence."
            />
          </PanelErrorBoundary>
        ) : (
          <ResearchBriefStateBlock
            kind="empty"
            kicker="Snapshot"
            title="No momentum history yet"
            message="This visual appears once cached price history or annual filing trends are available for the company."
          />
        )}
      </EvidenceCard>

      <EvidenceCard title="Business context" copy="The minimum operating context needed before opening specialist views.">
        {loading && !latestFinancial ? (
          <ResearchBriefStateBlock
            kind="loading"
            kicker="Snapshot"
            title="Loading company context"
            message="Reading the latest cached filing, segment mix, and alert count for the default brief."
          />
        ) : latestFinancial || topSegment ? (
          <CompanyMetricGrid
            items={[
              { label: "Reported Revenue", value: latestFinancial ? formatCompactCurrency(latestFinancial.revenue) : null },
              { label: "Free Cash Flow", value: latestFinancial ? formatCompactCurrency(latestFinancial.free_cash_flow) : null },
              {
                label: "Top Segment",
                value:
                  topSegment && topSegment.share_of_revenue != null
                    ? `${topSegment.segment_name} · ${formatPercent(topSegment.share_of_revenue)}`
                    : topSegment?.segment_name ?? null,
              },
              { label: "Current Alerts", value: latestAlertCount.toLocaleString() },
            ]}
          />
        ) : (
          <ResearchBriefStateBlock
            kind="empty"
            kicker="Snapshot"
            title="No persisted filing context yet"
            message="Queue a refresh to populate the default brief from cached company financials, segments, and activity summaries."
          />
        )}
      </EvidenceCard>

      <EvidenceCard
        title="Reported segment mix"
        copy="Segment and geography mix orient the read before deeper statement or filing work."
        className="is-wide"
      >
        {loading && !financials.length ? (
          <ResearchBriefStateBlock
            kind="loading"
            kicker="Snapshot"
            title="Loading segment disclosures"
            message="Reading the latest persisted segment and geography disclosures from cached filings."
          />
        ) : financials.length ? (
          <PanelErrorBoundary kicker="Snapshot" title="Unable to render segment breakdown">
            <BusinessSegmentBreakdown financials={financials} segmentAnalysis={segmentAnalysis ?? null} />
          </PanelErrorBoundary>
        ) : (
          <ResearchBriefStateBlock
            kind="empty"
            kicker="Snapshot"
            title="No reported segment breakdown yet"
            message="This section fills in once cached filings include segment or geographic disclosure detail."
          />
        )}
      </EvidenceCard>
    </ResearchBriefSection>
  );
});
