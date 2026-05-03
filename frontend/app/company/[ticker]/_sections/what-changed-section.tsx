"use client";

import { memo, useMemo } from "react";
import dynamic from "next/dynamic";

import { AlertOrEntryCard, EvidenceCard, PanelErrorBoundary, ResearchBriefSection, ResearchBriefStateBlock } from "@/components/company/brief-primitives";
import type { SectionLink } from "@/components/company/brief-primitives";
import { CompanyMetricGrid } from "@/components/layout/company-research-header";
import {
  toneForAlertLevel,
  toneForAlertSource,
  toneForEntryBadge,
  toneForEntryCard,
  toneForEntryType,
} from "@/lib/activity-feed-tone";
import { formatDate } from "@/lib/format";
import type {
  CompanyActivityOverviewResponse,
  CompanyBeneficialOwnershipSummaryResponse,
  CompanyChangesSinceLastFilingResponse,
  CompanyEarningsSummaryResponse,
  CompanyGovernanceSummaryResponse,
  CompanyModelsResponse,
} from "@/lib/types";
import type { AsyncState } from "@/components/company/brief-primitives";

import { WhatChangedHighlights } from "../_components/what-changed-highlights";
import { buildWhatChangedHighlights } from "../_lib/what-changed-summary";
import { formatFeedEntryType } from "../_lib/research-brief-utils";

const ChangesSinceLastFilingCard = dynamic(
  () => import("@/components/company/changes-since-last-filing-card").then((module) => module.ChangesSinceLastFilingCard),
  {
    ssr: false,
    loading: () => (
      <div className="research-brief-state research-brief-state-loading">
        <div className="grid-empty-kicker">What changed</div>
        <div className="grid-empty-title">Loading filing comparison</div>
        <div className="grid-empty-copy">Preparing the highest-signal filing changes from the latest cached comparison.</div>
      </div>
    ),
  }
);

type WhatChangedSectionProps = {
  changesState: AsyncState<CompanyChangesSinceLastFilingResponse>;
  earningsSummaryState: AsyncState<CompanyEarningsSummaryResponse>;
  activityOverviewState: AsyncState<CompanyActivityOverviewResponse>;
  modelsState: AsyncState<CompanyModelsResponse>;
  ownershipSummaryState: AsyncState<CompanyBeneficialOwnershipSummaryResponse>;
  governanceSummaryState: AsyncState<CompanyGovernanceSummaryResponse>;
  topAlerts: CompanyActivityOverviewResponse["alerts"];
  latestEntries: CompanyActivityOverviewResponse["entries"];
  briefLoading: boolean;
  ticker: string;
  reloadKey: string;
  narrative: string;
  links: SectionLink[];
  expanded: boolean;
  onToggle: () => void;
};

export const WhatChangedSection = memo(function WhatChangedSection({
  changesState,
  earningsSummaryState,
  activityOverviewState,
  modelsState,
  ownershipSummaryState,
  governanceSummaryState,
  topAlerts,
  latestEntries,
  briefLoading,
  ticker,
  reloadKey,
  narrative,
  links,
  expanded,
  onToggle,
}: WhatChangedSectionProps) {
  const highlights = useMemo(
    () =>
      buildWhatChangedHighlights({
        changes: changesState.data,
        earningsSummary: earningsSummaryState.data,
        activityOverview: activityOverviewState.data,
        models: modelsState.data,
        ownershipSummary: ownershipSummaryState.data,
        governanceSummary: governanceSummaryState.data,
      }),
    [
      activityOverviewState.data,
      changesState.data,
      earningsSummaryState.data,
      governanceSummaryState.data,
      modelsState.data,
      ownershipSummaryState.data,
    ]
  );

  const highlightsLoading =
    (changesState.loading && !changesState.data) ||
    (earningsSummaryState.loading && !earningsSummaryState.data) ||
    (activityOverviewState.loading && !activityOverviewState.data);

  return (
    <ResearchBriefSection
      id="what-changed"
      title="What changed"
      question="What is new since the last filing or review?"
      summary={narrative}
      cues={[
        {
          label: "Filing comparison",
          asOf: changesState.data?.as_of,
          lastRefreshedAt: changesState.data?.last_refreshed_at,
          provenance: changesState.data?.provenance,
          sourceMix: changesState.data?.source_mix,
          confidenceFlags: changesState.data?.confidence_flags,
        },
        {
          label: "Activity overview",
          asOf: activityOverviewState.data?.as_of,
          lastRefreshedAt: activityOverviewState.data?.last_refreshed_at,
          provenance: activityOverviewState.data?.provenance,
          sourceMix: activityOverviewState.data?.source_mix,
          confidenceFlags: activityOverviewState.data?.confidence_flags,
        },
      ]}
      links={links}
      expanded={expanded}
      onToggle={onToggle}
    >
      <EvidenceCard
        title="What changed now"
        copy="Deterministic highlights ranked by recency first, then severity, with source provenance on every line."
      >
        <WhatChangedHighlights items={highlights} loading={highlightsLoading} />
      </EvidenceCard>

      <EvidenceCard title="Update scoreboard" copy="The shortest possible read on filing deltas, earnings capture, and alert volume.">
        {changesState.error && !changesState.data && earningsSummaryState.error && !earningsSummaryState.data ? (
          <ResearchBriefStateBlock
            kind="error"
            kicker="What changed"
            title="Unable to load change summaries"
            message={changesState.error ?? earningsSummaryState.error ?? "Change summaries are temporarily unavailable."}
          />
        ) : changesState.loading && !changesState.data && earningsSummaryState.loading && !earningsSummaryState.data ? (
          <ResearchBriefStateBlock
            kind="loading"
            kicker="What changed"
            title="Loading latest deltas"
            message="Comparing the most recent filing, recent earnings payloads, and the cached activity overview."
          />
        ) : changesState.data || earningsSummaryState.data || activityOverviewState.data ? (
          <CompanyMetricGrid
            items={[
              {
                label: "High-Signal Changes",
                value: changesState.data ? String(changesState.data.summary.high_signal_change_count) : null,
              },
              {
                label: "Comment Letters",
                value: changesState.data ? String(changesState.data.summary.comment_letter_count) : null,
              },
              {
                label: "Latest EPS",
                value:
                  earningsSummaryState.data?.summary.latest_diluted_eps != null
                    ? earningsSummaryState.data.summary.latest_diluted_eps.toFixed(2)
                    : null,
              },
              {
                label: "High Alerts",
                value: activityOverviewState.data ? String(activityOverviewState.data.summary.high) : null,
              },
            ]}
          />
        ) : (
          <ResearchBriefStateBlock
            kind="empty"
            kicker="What changed"
            title="No recent change summary yet"
            message="This section fills in after the latest filing comparison, earnings summary, or activity overview is cached."
          />
        )}
      </EvidenceCard>

      <EvidenceCard
        title="Latest filing comparison"
        copy="Only the highest-signal filing changes surface here by default; the filings drill-down keeps the broader metric and evidence detail."
        className="is-wide"
      >
        <PanelErrorBoundary kicker="What changed" title="Unable to render filing comparison">
          <ChangesSinceLastFilingCard
            ticker={ticker}
            reloadKey={reloadKey}
            initialPayload={changesState.data}
            detailMode="brief"
            deferFetch={briefLoading}
          />
        </PanelErrorBoundary>
      </EvidenceCard>

      <EvidenceCard
        title="Recent SEC activity"
        copy="Top alerts and the latest timeline entries keep the default brief anchored to dated evidence instead of generic commentary."
        className="is-wide"
      >
        {activityOverviewState.error && !activityOverviewState.data ? (
          <ResearchBriefStateBlock
            kind="error"
            kicker="What changed"
            title="Unable to load recent activity"
            message={activityOverviewState.error}
          />
        ) : activityOverviewState.loading && !activityOverviewState.data ? (
          <ResearchBriefStateBlock
            kind="loading"
            kicker="What changed"
            title="Loading recent activity"
            message="Preparing the latest persisted alerts and SEC timeline entries for the default brief."
          />
        ) : topAlerts.length || latestEntries.length ? (
          <div className="company-pulse-columns research-brief-pulse-columns">
            <div className="company-pulse-list">
              <div className="company-pulse-heading">Top alerts</div>
              {topAlerts.length ? (
                topAlerts.map((alert) => {
                  const levelTone = toneForAlertLevel(alert.level);
                  const sourceTone = toneForAlertSource(alert.source);

                  return (
                    <AlertOrEntryCard
                      key={alert.id}
                      href={alert.href}
                      tone={levelTone}
                      topLeft={
                        <>
                          <span className={`pill tone-${levelTone}`}>{alert.level}</span>
                          <span className={`pill tone-${sourceTone}`}>{alert.source}</span>
                        </>
                      }
                      topRight={formatDate(alert.date)}
                      title={alert.title}
                      detail={alert.detail}
                    />
                  );
                })
              ) : (
                <ResearchBriefStateBlock
                  kind="empty"
                  kicker="What changed"
                  title="No current alerts"
                  message="No alert thresholds are currently triggered in the persisted activity overview."
                  minHeight={180}
                />
              )}
            </div>

            <div className="company-pulse-list">
              <div className="company-pulse-heading">Latest timeline</div>
              {latestEntries.length ? (
                latestEntries.map((entry) => {
                  const typeTone = toneForEntryType(entry.type);
                  const badgeTone = toneForEntryBadge(entry.type, entry.badge);
                  const cardTone = toneForEntryCard(entry);

                  return (
                    <AlertOrEntryCard
                      key={entry.id}
                      href={entry.href}
                      tone={cardTone}
                      topLeft={
                        <>
                          <span className={`pill tone-${typeTone}`}>{formatFeedEntryType(entry.type)}</span>
                          <span className={`pill tone-${badgeTone}`}>{entry.badge}</span>
                        </>
                      }
                      topRight={formatDate(entry.date)}
                      title={entry.title}
                      detail={entry.detail}
                    />
                  );
                })
              ) : (
                <ResearchBriefStateBlock
                  kind="empty"
                  kicker="What changed"
                  title="No recent timeline entries"
                  message="The cached activity stream will list the latest filing, governance, ownership, and insider events here once available."
                  minHeight={180}
                />
              )}
            </div>
          </div>
        ) : (
          <ResearchBriefStateBlock
            kind="empty"
            kicker="What changed"
            title="No recent activity yet"
            message="This section fills in once the cached activity overview has alerts or dated SEC entries for the selected company."
          />
        )}
      </EvidenceCard>
    </ResearchBriefSection>
  );
});
