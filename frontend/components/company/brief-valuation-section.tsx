"use client";

import dynamic from "next/dynamic";

import { EvidenceCard, ResearchBriefSection, ResearchBriefStateBlock } from "@/components/company/brief-primitives";
import type { AsyncState, ResearchBriefCue, SectionLink } from "@/components/company/brief-primitives";
import { formatCompactNumber, formatPercent } from "@/lib/format";
import type { CompanyModelsResponse, CompanyPeersResponse, FinancialPayload, PriceHistoryPoint } from "@/lib/types";

const InvestmentSummaryPanel = dynamic(
  () => import("@/components/models/investment-summary-panel").then((module) => module.InvestmentSummaryPanel),
  { ssr: false, loading: () => <div className="text-muted">Loading valuation summary...</div> }
);

export function BriefValuationSection({
  ticker,
  modelsState,
  peersState,
  financials,
  priceHistory,
  strictOfficialMode,
  narrative,
  links,
  expanded,
  onToggle,
}: {
  ticker: string;
  modelsState: AsyncState<CompanyModelsResponse>;
  peersState: AsyncState<CompanyPeersResponse>;
  financials: FinancialPayload[];
  priceHistory: PriceHistoryPoint[];
  strictOfficialMode: boolean;
  narrative: string;
  links: SectionLink[];
  expanded: boolean;
  onToggle: () => void;
}) {
  const cues: ResearchBriefCue[] = [
    {
      label: "Valuation models",
      asOf: modelsState.data?.as_of,
      lastRefreshedAt: modelsState.data?.last_refreshed_at,
      provenance: modelsState.data?.provenance,
      sourceMix: modelsState.data?.source_mix,
      confidenceFlags: modelsState.data?.confidence_flags,
    },
    {
      label: "Peer comparison",
      asOf: peersState.data?.as_of,
      lastRefreshedAt: peersState.data?.last_refreshed_at,
      provenance: peersState.data?.provenance,
      sourceMix: peersState.data?.source_mix,
      confidenceFlags: peersState.data?.confidence_flags,
    },
  ];

  return (
    <ResearchBriefSection
      id="valuation"
      title="Valuation"
      question="How does the current price compare with peers and cached model ranges?"
      summary={narrative}
      cues={cues}
      links={links}
      expanded={expanded}
      onToggle={onToggle}
    >
      <EvidenceCard
        title="Valuation summary"
        copy="Use the default brief to see the cached underwriting conclusion, then jump into the full Models workspace when you need the full assumption tree."
        className="is-wide"
      >
        {modelsState.error && !modelsState.data ? (
          <ResearchBriefStateBlock kind="error" kicker="Valuation" title="Unable to load valuation summary" message={modelsState.error} />
        ) : modelsState.loading && !modelsState.data ? (
          <ResearchBriefStateBlock
            kind="loading"
            kicker="Valuation"
            title="Loading valuation summary"
            message="Preparing the cached DCF, residual income, and diagnostic model outputs for the brief."
          />
        ) : modelsState.data?.models.length ? (
          <InvestmentSummaryPanel
            ticker={ticker}
            models={modelsState.data.models}
            financials={financials}
            priceHistory={priceHistory}
            strictOfficialMode={strictOfficialMode}
          />
        ) : (
          <ResearchBriefStateBlock
            kind="empty"
            kicker="Valuation"
            title="No cached model outputs yet"
            message="Refresh the company to backfill persisted model outputs before using the brief as a valuation read."
          />
        )}
      </EvidenceCard>

      <EvidenceCard title="Peer comparison snapshot" copy="A compact relative view so the brief can answer whether current multiples look rich, cheap, or roughly in line before deeper peer work.">
        {peersState.error && !peersState.data ? (
          <ResearchBriefStateBlock kind="error" kicker="Valuation" title="Unable to load peer snapshot" message={peersState.error} />
        ) : peersState.loading && !peersState.data ? (
          <ResearchBriefStateBlock
            kind="loading"
            kicker="Valuation"
            title="Loading peer snapshot"
            message="Preparing the persisted peer universe and comparison metrics for the brief."
          />
        ) : peersState.data?.peers.length ? (
          <PeerComparisonSnapshot response={peersState.data} />
        ) : (
          <ResearchBriefStateBlock
            kind="empty"
            kicker="Valuation"
            title="No peer snapshot yet"
            message="Peer comparison will appear after more cached companies are available in the comparison universe."
          />
        )}
      </EvidenceCard>
    </ResearchBriefSection>
  );
}

function PeerComparisonSnapshot({ response }: { response: CompanyPeersResponse }) {
  const rows = response.peers.slice(0, 4);

  return (
    <div className="research-brief-table-stack">
      <div className="company-data-table-shell">
        <table className="company-data-table company-data-table-compact">
          <thead>
            <tr>
              <th>Company</th>
              <th className="is-numeric">Price</th>
              <th className="is-numeric">P/E</th>
              <th className="is-numeric">EV / EBIT</th>
              <th className="is-numeric">Revenue Growth</th>
              <th className="is-numeric">ROIC</th>
              <th className="is-numeric">Fair Value Gap</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((peer) => (
              <tr key={peer.ticker} className={peer.is_focus ? "research-brief-table-row-focus" : undefined}>
                <td>
                  <div className="research-brief-peer-cell">
                    <strong>{peer.ticker}</strong>
                    <span className="text-muted">{peer.name}</span>
                  </div>
                </td>
                <td className="is-numeric">{formatCompactCurrency(peer.latest_price)}</td>
                <td className="is-numeric">{formatMultiple(peer.pe)}</td>
                <td className="is-numeric">{formatMultiple(peer.ev_to_ebit)}</td>
                <td className="is-numeric">{formatPercent(peer.revenue_growth)}</td>
                <td className="is-numeric">{formatPercent(peer.roic)}</td>
                <td className="is-numeric">{formatPercent(peer.fair_value_gap)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {response.notes.fair_value_gap ? <div className="text-muted workspace-note-line">{response.notes.fair_value_gap}</div> : null}
      {response.notes.ev_to_ebit ? <div className="text-muted workspace-note-line">{response.notes.ev_to_ebit}</div> : null}
    </div>
  );
}

function formatCompactCurrency(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  return `$${formatCompactNumber(value)}`;
}

function formatMultiple(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  return `${value.toFixed(1)}x`;
}
