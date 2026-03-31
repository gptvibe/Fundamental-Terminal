"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { CompanyResearchHeader } from "@/components/layout/company-research-header";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { Panel } from "@/components/ui/panel";
import { SourceFreshnessSummary } from "@/components/ui/source-freshness-summary";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { getCompanyActivityOverview } from "@/lib/api";
import { toneForAlertLevel, toneForAlertSource, toneForEntryBadge, toneForEntryCard, toneForEntryType } from "@/lib/activity-feed-tone";
import { formatDate } from "@/lib/format";
import type { CompanyActivityOverviewResponse } from "@/lib/types";

type AlertLevelFilter = "all" | "high" | "medium" | "low";

export default function CompanySecFeedPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(params.ticker).toUpperCase();
  const {
    company,
    loading: workspaceLoading,
    refreshing,
    refreshState,
    consoleEntries,
    connectionState,
    queueRefresh,
    reloadKey
  } = useCompanyWorkspace(ticker);
  const [activityData, setActivityData] = useState<CompanyActivityOverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [alertLevelFilter, setAlertLevelFilter] = useState<AlertLevelFilter>("all");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        const activity = await getCompanyActivityOverview(ticker);
        if (!cancelled) {
          setActivityData(activity);
        }
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError instanceof Error ? nextError.message : "Unable to load SEC feed");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [reloadKey, ticker]);

  const feed = useMemo(() => activityData?.entries ?? [], [activityData?.entries]);
  const filteredAlerts = useMemo(
    () => (activityData?.alerts ?? []).filter((alert) => alertLevelFilter === "all" || alert.level === alertLevelFilter),
    [alertLevelFilter, activityData?.alerts]
  );
  const topAlerts = useMemo(() => filteredAlerts.slice(0, 3), [filteredAlerts]);

  const effectiveRefreshState = activityData?.refresh ?? refreshState;
  const latestDate = feed[0]?.date ?? null;

  return (
    <CompanyWorkspaceShell
      rail={
        <CompanyUtilityRail
          ticker={ticker}
          companyName={company?.name ?? activityData?.company?.name ?? null}
          sector={company?.sector ?? activityData?.company?.sector ?? null}
          refreshState={effectiveRefreshState}
          refreshing={refreshing}
          onRefresh={() => queueRefresh()}
          actionTitle="Next Steps"
          actionSubtitle="Refresh the SEC feed or pivot into the specialized workflows for events, governance, ownership, or insiders."
          primaryActionLabel="Refresh SEC Feed"
          primaryActionDescription="Queues a company refresh so the unified SEC activity stream reflects the latest filings and ownership updates."
          secondaryActionHref={`/company/${encodeURIComponent(ticker)}/events`}
          secondaryActionLabel="Open Event Feed"
          secondaryActionDescription="Jump into the current-report workflow for a focused 8-K event view."
          statusLines={[
            `Feed entries: ${feed.length.toLocaleString()}`,
            `Latest SEC activity: ${latestDate ? formatDate(latestDate) : "Pending"}`,
            `Sources unified: filings, events, governance, ownership, insider trades, Form 144 planned sales, and 13F activity`
          ]}
          consoleEntries={consoleEntries}
          connectionState={connectionState}
        />
      }
      mainClassName="company-page-grid"
    >
      <CompanyResearchHeader
        ticker={ticker}
        title="SEC Feed"
        companyName={company?.name ?? activityData?.company?.name ?? ticker}
        sector={company?.sector ?? activityData?.company?.sector ?? null}
        description="Unified SEC signal stream across filings, events, governance, insider activity, Form 144 planned sales, and ownership updates."
        freshness={{
          cacheState: company?.cache_state ?? activityData?.company?.cache_state ?? null,
          refreshState: effectiveRefreshState,
          loading: loading || workspaceLoading,
          hasData: Boolean(company || activityData?.company || feed.length || filteredAlerts.length),
          lastChecked: company?.last_checked ?? activityData?.company?.last_checked ?? null,
          errors: [error],
          detailLines: [
            `Feed entries: ${feed.length.toLocaleString()}`,
            `Latest SEC activity: ${latestDate ? formatDate(latestDate) : "Pending"}`,
            "Sources unified: filings, events, governance, ownership, insiders, Form 144, and 13F",
          ],
        }}
        freshnessPlacement="subtitle"
        factsLoading={(loading || workspaceLoading) && !company && !activityData?.company && !feed.length}
        summariesLoading={(loading || workspaceLoading) && !company && !activityData?.company && !feed.length && !filteredAlerts.length}
        facts={[
          { label: "Ticker", value: ticker },
          { label: "Feed Entries", value: feed.length.toLocaleString() },
          { label: "Latest Activity", value: latestDate ? formatDate(latestDate) : "Pending" },
          { label: "Last Checked", value: company?.last_checked ? formatDate(company.last_checked) : null },
        ]}
        ribbonItems={[
          { label: "Sources", value: "SEC filings + ownership + insider + Form 144 + 13F", tone: "green" },
          { label: "Refresh", value: effectiveRefreshState?.job_id ? "Queued" : "Background-first", tone: effectiveRefreshState?.job_id ? "cyan" : "green" },
          { label: "Latest Feed", value: latestDate ? formatDate(latestDate) : "Pending", tone: "cyan" },
        ]}
        summaries={[
          { label: "Total Alerts", value: (activityData?.summary.total ?? 0).toLocaleString(), accent: "cyan" },
          { label: "High Alerts", value: (activityData?.summary.high ?? 0).toLocaleString(), accent: "red" },
          { label: "Medium Alerts", value: (activityData?.summary.medium ?? 0).toLocaleString(), accent: "gold" },
          { label: "Low Alerts", value: (activityData?.summary.low ?? 0).toLocaleString(), accent: "green" },
        ]}
      />

      <Panel title="Source & Freshness" subtitle="Registry-backed provenance for the unified SEC activity stream and supporting macro status">
        <SourceFreshnessSummary
          provenance={activityData?.provenance}
          asOf={activityData?.as_of}
          lastRefreshedAt={activityData?.last_refreshed_at}
          sourceMix={activityData?.source_mix}
          confidenceFlags={activityData?.confidence_flags}
        />
      </Panel>

      <Panel title="Priority Alerts" subtitle="Most important filing-driven signals from recent SEC activity">
        {error ? (
          <div className="text-muted">{error}</div>
        ) : loading || workspaceLoading ? (
          <div className="text-muted">Loading alerts...</div>
        ) : (
          <div className="workspace-card-stack">
            <div className="workspace-filter-row">
              {([
                ["all", `All (${activityData?.summary.total ?? 0})`],
                ["high", `High (${activityData?.summary.high ?? 0})`],
                ["medium", `Medium (${activityData?.summary.medium ?? 0})`],
                ["low", `Low (${activityData?.summary.low ?? 0})`],
              ] as const).map(([level, label]) => {
                const tone = level === "all" ? "cyan" : toneForAlertLevel(level);

                return (
                  <button
                    key={level}
                    type="button"
                    className={`pill workspace-filter-pill tone-${tone}`}
                    onClick={() => setAlertLevelFilter(level)}
                    aria-pressed={alertLevelFilter === level}
                  >
                    {label}
                  </button>
                );
              })}
            </div>

            {topAlerts.length ? topAlerts.map((alert) => {
                const levelTone = toneForAlertLevel(alert.level);
                const sourceTone = toneForAlertSource(alert.source);
                const content = (
                  <>
                    <div className="workspace-card-row">
                      <div className="workspace-pill-row">
                        <span className={`pill tone-${levelTone}`}>{alert.level}</span>
                        <span className={`pill tone-${sourceTone}`}>{alert.source}</span>
                      </div>
                      <div className="text-muted">{formatDate(alert.date)}</div>
                    </div>
                    <div className="workspace-card-title">{alert.title}</div>
                    <div className="text-muted workspace-card-copy">{alert.detail}</div>
                  </>
                );

                if (alert.href) {
                  return (
                    <a
                      key={alert.id}
                      href={alert.href}
                      target="_blank"
                      rel="noreferrer"
                      className={`filing-link-card workspace-card-link tone-${levelTone}`}
                    >
                      {content}
                    </a>
                  );
                }

                return (
                  <div
                    key={alert.id}
                    className={`filing-link-card workspace-card-link tone-${levelTone}`}
                  >
                    {content}
                  </div>
                );
              }) : <div className="text-muted">No alerts in this severity filter.</div>}
          </div>
        )}
      </Panel>

      <Panel title="Chronological SEC Stream" subtitle="Events, proxy filings, stake disclosures, insider trades, Form 144 planned sales, and 13F updates in one timeline">
        {error ? (
          <div className="text-muted">{error}</div>
        ) : loading || workspaceLoading ? (
          <div className="text-muted">Loading SEC feed...</div>
        ) : feed.length ? (
          <div className="workspace-card-stack">
            {feed.map((entry) => {
              const typeTone = toneForEntryType(entry.type);
              const badgeTone = toneForEntryBadge(entry.type, entry.badge);
              const cardTone = toneForEntryCard(entry);
              const content = (
                <>
                  <div className="workspace-card-row">
                    <div className="workspace-pill-row">
                      <span className={`pill tone-${typeTone}`}>{formatFeedEntryType(entry.type)}</span>
                      <span className={`pill tone-${badgeTone}`}>{entry.badge}</span>
                    </div>
                    <div className="text-muted">{formatDate(entry.date)}</div>
                  </div>
                  <div className="workspace-card-title">{entry.title}</div>
                  <div className="text-muted workspace-card-copy">{entry.detail}</div>
                </>
              );

              if (entry.href) {
                return (
                  <a key={entry.id} href={entry.href} target="_blank" rel="noreferrer" className={`filing-link-card workspace-card-link tone-${cardTone}`}>
                    {content}
                  </a>
                );
              }

              return (
                <div key={entry.id} className={`filing-link-card workspace-card-link tone-${cardTone}`}>
                  {content}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="grid-empty-state" style={{ minHeight: 220 }}>
            <div className="grid-empty-kicker">SEC feed</div>
            <div className="grid-empty-title">No activity yet</div>
            <div className="grid-empty-copy">This page fills in once the cache has SEC filings, insider trades, or institutional holdings for the selected company.</div>
          </div>
        )}
      </Panel>
    </CompanyWorkspaceShell>
  );
}

function formatFeedEntryType(type: string): string {
  if (type === "form144") {
    return "planned-sale";
  }
  return type;
}
