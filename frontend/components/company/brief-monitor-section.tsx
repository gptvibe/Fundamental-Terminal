"use client";

import { AlertOrEntryCard, EvidenceCard, ResearchBriefSection, ResearchBriefStateBlock } from "@/components/company/brief-primitives";
import type { AsyncState, MonitorChecklistItem, ResearchBriefCue, SectionLink } from "@/components/company/brief-primitives";
import {
  toneForAlertLevel,
  toneForAlertSource,
  toneForEntryBadge,
  toneForEntryCard,
  toneForEntryType,
} from "@/lib/activity-feed-tone";
import { formatDate } from "@/lib/format";
import type { ActivityFeedEntryPayload, AlertPayload, CompanyActivityOverviewResponse } from "@/lib/types";

export function BriefMonitorSection({
  activityOverviewState,
  topAlerts,
  latestEntries,
  monitorChecklist,
  narrative,
  lastChecked,
  links,
  expanded,
  onToggle,
}: {
  activityOverviewState: AsyncState<CompanyActivityOverviewResponse>;
  topAlerts: AlertPayload[];
  latestEntries: ActivityFeedEntryPayload[];
  monitorChecklist: MonitorChecklistItem[];
  narrative: string;
  lastChecked: string | null | undefined;
  links: SectionLink[];
  expanded: boolean;
  onToggle: () => void;
}) {
  const cues: ResearchBriefCue[] = [
    {
      label: "Monitoring feed",
      asOf: activityOverviewState.data?.as_of,
      lastRefreshedAt: activityOverviewState.data?.last_refreshed_at,
      lastChecked,
      provenance: activityOverviewState.data?.provenance,
      sourceMix: activityOverviewState.data?.source_mix,
      confidenceFlags: activityOverviewState.data?.confidence_flags,
    },
  ];

  return (
    <ResearchBriefSection
      id="monitor"
      title="Monitor"
      question="What should I keep watching after I leave this page?"
      summary={narrative}
      cues={cues}
      links={links}
      expanded={expanded}
      onToggle={onToggle}
    >
      <EvidenceCard title="Priority alerts" copy="The monitor starts with the highest-signal items the user is likely to revisit first.">
        {activityOverviewState.error && !activityOverviewState.data ? (
          <ResearchBriefStateBlock kind="error" kicker="Monitor" title="Unable to load alerts" message={activityOverviewState.error} />
        ) : activityOverviewState.loading && !activityOverviewState.data ? (
          <ResearchBriefStateBlock
            kind="loading"
            kicker="Monitor"
            title="Loading alert watchlist"
            message="Preparing the cached alert feed that powers the brief's monitor section."
          />
        ) : topAlerts.length ? (
          <div className="workspace-card-stack">
            {topAlerts.map((alert) => {
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
            })}
          </div>
        ) : (
          <ResearchBriefStateBlock
            kind="empty"
            kicker="Monitor"
            title="No active alerts"
            message="The monitor will list high-priority cached alerts here when thresholds are triggered."
          />
        )}
      </EvidenceCard>

      <EvidenceCard title="Latest timeline" copy="Chronological recent activity keeps the monitor grounded in dated SEC evidence instead of a generic task list.">
        {activityOverviewState.error && !activityOverviewState.data ? (
          <ResearchBriefStateBlock kind="error" kicker="Monitor" title="Unable to load timeline" message={activityOverviewState.error} />
        ) : activityOverviewState.loading && !activityOverviewState.data ? (
          <ResearchBriefStateBlock
            kind="loading"
            kicker="Monitor"
            title="Loading SEC timeline"
            message="Preparing recent filing, governance, ownership, and insider events for the watchlist-style closeout."
          />
        ) : latestEntries.length ? (
          <div className="workspace-card-stack">
            {latestEntries.map((entry) => {
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
            })}
          </div>
        ) : (
          <ResearchBriefStateBlock
            kind="empty"
            kicker="Monitor"
            title="No timeline entries yet"
            message="Recent filing and ownership activity will populate here once the monitoring feed has dated SEC events to show."
          />
        )}
      </EvidenceCard>

      <EvidenceCard title="Monitor checklist" copy="The last step in the brief is explicit: what to re-check next, and why.">
        {monitorChecklist.length ? (
          <div className="research-brief-checklist-grid">
            {monitorChecklist.map((item) => (
              <div key={item.title} className={`research-brief-checklist-card tone-${item.tone}`}>
                <div className="research-brief-checklist-title">{item.title}</div>
                <div className="research-brief-checklist-detail">{item.detail}</div>
              </div>
            ))}
          </div>
        ) : (
          <ResearchBriefStateBlock
            kind="empty"
            kicker="Monitor"
            title="No next-step checklist yet"
            message="The monitor checklist appears once the brief has enough cached activity and freshness data to recommend the next review points."
          />
        )}
      </EvidenceCard>
    </ResearchBriefSection>
  );
}

function formatFeedEntryType(type: string): string {
  if (type === "form144") {
    return "planned-sale";
  }
  return type;
}
