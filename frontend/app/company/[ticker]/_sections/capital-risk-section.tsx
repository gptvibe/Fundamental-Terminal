"use client";

import { memo } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";

import { EvidenceCard, PanelErrorBoundary, ResearchBriefSection, ResearchBriefStateBlock } from "@/components/company/brief-primitives";
import type { SectionLink } from "@/components/company/brief-primitives";
import { formatDate, formatPercent, titleCase } from "@/lib/format";
import type {
  AsyncState,
} from "@/components/company/brief-primitives";
import type {
  CompanyCapitalMarketsSummaryResponse,
  CompanyCapitalStructureResponse,
  CompanyGovernanceSummaryResponse,
  CompanyBeneficialOwnershipSummaryResponse,
  CompanyResearchBriefCapitalAndRiskSection,
  EquityClaimRiskSummaryPayload,
  FinancialPayload,
} from "@/lib/types";

import { formatCompactCurrency, toneForRiskLevel } from "../_lib/research-brief-utils";

const ShareDilutionTrackerChart = dynamic(
  () => import("@/components/charts/share-dilution-tracker-chart").then((module) => module.ShareDilutionTrackerChart),
  {
    ssr: false,
    loading: () => (
      <div className="research-brief-state research-brief-state-loading">
        <div className="grid-empty-kicker">Capital &amp; risk</div>
        <div className="grid-empty-title">Loading dilution tracker</div>
        <div className="grid-empty-copy">Reading cached share-count history to determine dilution direction.</div>
      </div>
    ),
  }
);

const CapitalStructureIntelligencePanel = dynamic(
  () => import("@/components/company/capital-structure-intelligence-panel").then((module) => module.CapitalStructureIntelligencePanel),
  {
    ssr: false,
    loading: () => (
      <div className="research-brief-state research-brief-state-loading">
        <div className="grid-empty-kicker">Capital &amp; risk</div>
        <div className="grid-empty-title">Loading capital structure intelligence</div>
        <div className="grid-empty-copy">Preparing the persisted debt, lease, payout, and dilution intelligence.</div>
      </div>
    ),
  }
);

type CapitalRiskSectionProps = {
  ticker: string;
  reloadKey: string;
  capitalStructureState: AsyncState<CompanyCapitalStructureResponse>;
  capitalMarketsSummaryState: AsyncState<CompanyCapitalMarketsSummaryResponse>;
  governanceSummaryState: AsyncState<CompanyGovernanceSummaryResponse>;
  ownershipSummaryState: AsyncState<CompanyBeneficialOwnershipSummaryResponse>;
  briefLoading: boolean;
  briefCapitalRiskCue: CompanyResearchBriefCapitalAndRiskSection | undefined;
  equityClaimRiskSummary: EquityClaimRiskSummaryPayload | null;
  capitalSignalRows: Array<{ signal: string; currentRead: string; latestEvidence: string }>;
  foreignIssuerStyleFiling: boolean;
  financials: FinancialPayload[];
  loading: boolean;
  error: string | null;
  narrative: string;
  links: SectionLink[];
  expanded: boolean;
  onToggle: () => void;
  lastCheckedFilings: string | null | undefined;
};

export const CapitalRiskSection = memo(function CapitalRiskSection({
  ticker,
  reloadKey,
  capitalStructureState,
  capitalMarketsSummaryState,
  governanceSummaryState,
  ownershipSummaryState,
  briefLoading,
  briefCapitalRiskCue,
  equityClaimRiskSummary,
  capitalSignalRows,
  foreignIssuerStyleFiling,
  financials,
  loading,
  error,
  narrative,
  links,
  expanded,
  onToggle,
  lastCheckedFilings,
}: CapitalRiskSectionProps) {
  return (
    <ResearchBriefSection
      id="capital-risk"
      title="Capital & risk"
      question="Is the equity claim being protected, diluted, or put at risk?"
      summary={narrative}
      cues={[
        ...(briefCapitalRiskCue
          ? [
              {
                label: "Equity claim risk pack",
                asOf: briefCapitalRiskCue.as_of,
                lastRefreshedAt: briefCapitalRiskCue.last_refreshed_at,
                provenance: briefCapitalRiskCue.provenance,
                sourceMix: briefCapitalRiskCue.source_mix,
                confidenceFlags: briefCapitalRiskCue.confidence_flags,
              },
            ]
          : []),
        {
          label: "Capital structure",
          asOf: capitalStructureState.data?.as_of,
          lastRefreshedAt: capitalStructureState.data?.last_refreshed_at,
          provenance: capitalStructureState.data?.provenance,
          sourceMix: capitalStructureState.data?.source_mix,
          confidenceFlags: capitalStructureState.data?.confidence_flags,
        },
        {
          label: "Governance and stake signals",
          lastChecked: lastCheckedFilings,
        },
      ]}
      links={links}
      expanded={expanded}
      onToggle={onToggle}
    >
      <EvidenceCard
        title="Equity claim risk pack summary"
        copy="A compact underwriting read on dilution, financing dependency, debt pressure, and reporting-control risk pulled from SEC-derived evidence."
      >
        {equityClaimRiskSummary ? (
          <div className="workspace-card-stack">
            <div className="workspace-card-row">
              <div className="workspace-pill-row">
                <span className={`pill tone-${toneForRiskLevel(equityClaimRiskSummary.overall_risk_level)}`}>
                  Overall {titleCase(equityClaimRiskSummary.overall_risk_level)}
                </span>
                <span className={`pill tone-${toneForRiskLevel(equityClaimRiskSummary.dilution_risk_level)}`}>
                  Dilution {titleCase(equityClaimRiskSummary.dilution_risk_level)}
                </span>
                <span className={`pill tone-${toneForRiskLevel(equityClaimRiskSummary.financing_risk_level)}`}>
                  Financing {titleCase(equityClaimRiskSummary.financing_risk_level)}
                </span>
                <span className={`pill tone-${toneForRiskLevel(equityClaimRiskSummary.reporting_risk_level)}`}>
                  Reporting {titleCase(equityClaimRiskSummary.reporting_risk_level)}
                </span>
              </div>
              <div className="text-muted">
                {equityClaimRiskSummary.latest_period_end ? formatDate(equityClaimRiskSummary.latest_period_end) : "Latest period pending"}
              </div>
            </div>
            <div className="workspace-card-title">{equityClaimRiskSummary.headline || "Risk summary is available once the capital-and-risk pack finishes building."}</div>
            <div className="text-muted workspace-card-copy">
              Net dilution {formatPercent(equityClaimRiskSummary.net_dilution_ratio)} · SBC / revenue {formatPercent(equityClaimRiskSummary.sbc_to_revenue)} · Shelf remaining {formatCompactCurrency(equityClaimRiskSummary.shelf_capacity_remaining)} · Debt due in 24 months {formatCompactCurrency(equityClaimRiskSummary.debt_due_next_twenty_four_months)}
            </div>
            {equityClaimRiskSummary.key_points.length ? (
              <div className="workspace-card-stack">
                {equityClaimRiskSummary.key_points.slice(0, 4).map((point) => (
                  <div key={point} className="text-muted workspace-card-copy">
                    {point}
                  </div>
                ))}
              </div>
            ) : null}
            <div>
              <Link href={`/company/${encodeURIComponent(ticker)}/capital-markets`} className="workspace-card-link">
                Open the full Equity Claim Risk Pack
              </Link>
            </div>
          </div>
        ) : (
          <ResearchBriefStateBlock
            kind={briefLoading ? "loading" : "empty"}
            kicker="Capital & risk"
            title={briefLoading ? "Loading equity claim risk summary" : "No equity claim risk summary yet"}
            message={
              briefLoading
                ? "Preparing the compact underwriting summary from share-count, financing, debt, and reporting-control signals."
                : "This summary appears once the derived Equity Claim Risk Pack is available for the selected company."
            }
          />
        )}
      </EvidenceCard>

      <EvidenceCard
        title="Capital structure intelligence"
        copy="Debt ladders, lease schedules, payout mix, and dilution bridges pulled from persisted SEC extraction rather than route-time recomputation."
        className="is-wide"
      >
        {capitalStructureState.error && !capitalStructureState.data ? (
          <ResearchBriefStateBlock
            kind="error"
            kicker="Capital & risk"
            title="Unable to load capital structure"
            message={capitalStructureState.error}
          />
        ) : capitalStructureState.loading && !capitalStructureState.data ? (
          <ResearchBriefStateBlock
            kind="loading"
            kicker="Capital & risk"
            title="Loading capital structure"
            message="Preparing the persisted debt, lease, payout, and dilution intelligence for the brief."
          />
        ) : capitalStructureState.data?.latest ? (
          <PanelErrorBoundary kicker="Capital & risk" title="Unable to render capital structure intelligence">
            <CapitalStructureIntelligencePanel
              ticker={ticker}
              reloadKey={reloadKey}
              initialPayload={capitalStructureState.data}
            />
          </PanelErrorBoundary>
        ) : (
          <ResearchBriefStateBlock
            kind="empty"
            kicker="Capital & risk"
            title="No capital structure snapshot yet"
            message="This section fills in once persisted capital structure extraction is available for the selected company."
          />
        )}
      </EvidenceCard>

      <EvidenceCard title="Share dilution" copy="Share-count direction keeps the equity-claim read grounded in persisted filing history.">
        {error && !financials.length ? (
          <ResearchBriefStateBlock kind="error" kicker="Capital & risk" title="Unable to load dilution history" message={error} />
        ) : loading && !financials.length ? (
          <ResearchBriefStateBlock
            kind="loading"
            kicker="Capital & risk"
            title="Loading dilution history"
            message="Reading cached share-count history to determine whether the equity claim is being diluted or defended."
          />
        ) : financials.length ? (
          <PanelErrorBoundary kicker="Capital & risk" title="Unable to render dilution tracker">
            <ShareDilutionTrackerChart financials={financials} />
          </PanelErrorBoundary>
        ) : (
          <ResearchBriefStateBlock
            kind="empty"
            kicker="Capital & risk"
            title="No dilution history yet"
            message="This chart appears once cached filings include enough share-count history to calculate dilution over time."
          />
        )}
      </EvidenceCard>

      <EvidenceCard title="Control and ownership signals" copy="Governance, major-holder, insider, and institutional cues that can change the thesis even when the statements still look clean.">
        {capitalMarketsSummaryState.error &&
        !capitalMarketsSummaryState.data &&
        governanceSummaryState.error &&
        !governanceSummaryState.data &&
        ownershipSummaryState.error &&
        !ownershipSummaryState.data ? (
          <ResearchBriefStateBlock
            kind="error"
            kicker="Capital & risk"
            title="Unable to load control signals"
            message={
              capitalMarketsSummaryState.error ??
              governanceSummaryState.error ??
              ownershipSummaryState.error ??
              "Control and ownership signals are temporarily unavailable."
            }
          />
        ) : capitalMarketsSummaryState.loading &&
          !capitalMarketsSummaryState.data &&
          governanceSummaryState.loading &&
          !governanceSummaryState.data &&
          ownershipSummaryState.loading &&
          !ownershipSummaryState.data ? (
          <ResearchBriefStateBlock
            kind="loading"
            kicker="Capital & risk"
            title="Loading control signals"
            message="Bringing together persisted financing, proxy, and ownership-change context."
          />
        ) : capitalSignalRows.length ? (
          <div className="company-data-table-shell">
            <table className="company-data-table company-data-table-compact">
              <thead>
                <tr>
                  <th>Signal</th>
                  <th>Current Read</th>
                  <th>Latest Dated Evidence</th>
                </tr>
              </thead>
              <tbody>
                {capitalSignalRows.map((row) => (
                  <tr key={row.signal}>
                    <td>{row.signal}</td>
                    <td>{row.currentRead}</td>
                    <td>{row.latestEvidence}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <ResearchBriefStateBlock
            kind="empty"
            kicker="Capital & risk"
            title="No control signals yet"
            message={
              foreignIssuerStyleFiling
                ? "This table fills in as capital markets and ownership-change signals are cached. U.S. proxy coverage can remain limited for many 20-F and 40-F issuers."
                : "This table fills in after capital markets, governance, or ownership-change signals are cached for the company."
            }
          />
        )}
      </EvidenceCard>
    </ResearchBriefSection>
  );
});
