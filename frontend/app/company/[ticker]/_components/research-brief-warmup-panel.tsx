"use client";

import { Panel } from "@/components/ui/panel";
import { formatDate, titleCase } from "@/lib/format";
import type {
  FilingTimelineItemPayload,
  RefreshState,
  ResearchBriefBuildState,
  ResearchBriefSectionStatusPayload,
  ResearchBriefSummaryCardPayload,
} from "@/lib/types";

import { formatResearchBriefBuildState } from "../_lib/research-brief-utils";

export function ResearchBriefWarmupPanel({
  buildState,
  buildStatus,
  sectionStatuses,
  summaryCards,
  filingTimeline,
  refreshState,
}: {
  buildState: ResearchBriefBuildState;
  buildStatus: string | null;
  sectionStatuses: ResearchBriefSectionStatusPayload[];
  summaryCards: ResearchBriefSummaryCardPayload[];
  filingTimeline: FilingTimelineItemPayload[];
  refreshState: RefreshState | null;
}) {
  if (buildState === "ready" && !summaryCards.length && !filingTimeline.length) {
    return null;
  }

  return (
    <Panel
      title={buildState === "ready" ? "Brief status" : buildState === "partial" ? "Brief warming" : "Cold start bootstrap"}
      subtitle={buildStatus ?? "Preparing the first meaningful screen while the full brief continues to hydrate."}
      variant="subtle"
      className={`research-brief-warmup-panel research-brief-warmup-panel-${buildState}`}
    >
      <div className="research-brief-warmup-stack">
        <div className="research-brief-warmup-topline">
          <span className={`pill research-brief-build-pill research-brief-build-pill-${buildState}`}>{formatResearchBriefBuildState(buildState)}</span>
          {refreshState?.job_id ? <span className="pill">Refresh queued</span> : null}
          {refreshState?.reason ? <span className="pill">{titleCase(refreshState.reason)}</span> : null}
        </div>

        {summaryCards.length ? (
          <div className="research-brief-summary-card-grid">
            {summaryCards.map((card) => (
              <div key={card.key} className="research-brief-summary-card">
                <div className="research-brief-summary-card-title">{card.title}</div>
                <div className="research-brief-summary-card-value">{card.value}</div>
                {card.detail ? <div className="research-brief-summary-card-detail">{card.detail}</div> : null}
              </div>
            ))}
          </div>
        ) : null}

        <div className="research-brief-warmup-grid">
          <div className="research-brief-warmup-section-list">
            <div className="research-brief-warmup-heading">Section build order</div>
            <div className="research-brief-warmup-status-grid">
              {sectionStatuses.map((statusItem) => (
                <div key={statusItem.id} className={`research-brief-warmup-status-card state-${statusItem.state}`}>
                  <div className="research-brief-warmup-status-topline">
                    <span className="research-brief-warmup-status-title">{statusItem.title}</span>
                    <span className={`pill research-brief-status-pill state-${statusItem.state}`}>{formatResearchBriefBuildState(statusItem.state)}</span>
                  </div>
                  {statusItem.detail ? <div className="research-brief-warmup-status-detail">{statusItem.detail}</div> : null}
                </div>
              ))}
            </div>
          </div>

          <div className="research-brief-warmup-section-list">
            <div className="research-brief-warmup-heading">Latest filing timeline</div>
            {filingTimeline.length ? (
              <div className="research-brief-warmup-timeline">
                {filingTimeline.slice(0, 5).map((item) => (
                  <div key={`${item.accession ?? item.form}-${item.date ?? "pending"}`} className="research-brief-warmup-timeline-item">
                    <div className="research-brief-warmup-timeline-topline">
                      <span className="research-brief-warmup-timeline-form">{item.form}</span>
                      <span className="text-muted">{item.date ? formatDate(item.date) : "Pending"}</span>
                    </div>
                    <div className="research-brief-warmup-timeline-detail">{item.description}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="research-brief-warmup-empty">Recent filings will appear here once the first SEC timeline is resolved.</div>
            )}
          </div>
        </div>
      </div>
    </Panel>
  );
}
