"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { Panel } from "@/components/ui/panel";
import { StatusPill } from "@/components/ui/status-pill";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { getCompanyActivityFeed, getCompanyAlerts } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { CompanyActivityFeedResponse, CompanyAlertsResponse } from "@/lib/types";

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
  const [activityData, setActivityData] = useState<CompanyActivityFeedResponse | null>(null);
  const [alertsData, setAlertsData] = useState<CompanyAlertsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [alertLevelFilter, setAlertLevelFilter] = useState<AlertLevelFilter>("all");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        const [activity, alerts] = await Promise.all([
          getCompanyActivityFeed(ticker),
          getCompanyAlerts(ticker),
        ]);
        if (!cancelled) {
          setActivityData(activity);
          setAlertsData(alerts);
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
    () => (alertsData?.alerts ?? []).filter((alert) => alertLevelFilter === "all" || alert.level === alertLevelFilter),
    [alertLevelFilter, alertsData?.alerts]
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
      <Panel title="SEC Feed" subtitle={company?.name ?? ticker} aside={effectiveRefreshState ? <StatusPill state={effectiveRefreshState} /> : undefined}>
        <div className="metric-grid">
          <Metric label="Ticker" value={ticker} />
          <Metric label="Feed Entries" value={feed.length.toLocaleString()} />
          <Metric label="Latest Activity" value={latestDate ? formatDate(latestDate) : "Pending"} />
          <Metric label="High Alerts" value={(alertsData?.summary.high ?? 0).toLocaleString()} />
          <Metric label="Last Checked" value={company?.last_checked ? formatDate(company.last_checked) : null} />
        </div>
      </Panel>

      <Panel title="Priority Alerts" subtitle="Most important filing-driven signals from recent SEC activity">
        {error ? (
          <div className="text-muted">{error}</div>
        ) : loading || workspaceLoading ? (
          <div className="text-muted">Loading alerts...</div>
        ) : (
          <div style={{ display: "grid", gap: 12 }}>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {([
                ["all", `All (${alertsData?.summary.total ?? 0})`],
                ["high", `High (${alertsData?.summary.high ?? 0})`],
                ["medium", `Medium (${alertsData?.summary.medium ?? 0})`],
                ["low", `Low (${alertsData?.summary.low ?? 0})`],
              ] as const).map(([level, label]) => (
                <button
                  key={level}
                  type="button"
                  className="pill"
                  onClick={() => setAlertLevelFilter(level)}
                  aria-pressed={alertLevelFilter === level}
                  style={{
                    cursor: "pointer",
                    borderColor: alertLevelFilter === level ? "var(--accent)" : undefined,
                    color: alertLevelFilter === level ? "var(--text)" : undefined,
                  }}
                >
                  {label}
                </button>
              ))}
            </div>

            {topAlerts.length ? topAlerts.map((alert) => {
                const content = (
                  <>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                        <span className="pill">{alert.level}</span>
                        <span className="pill">{alert.source}</span>
                      </div>
                      <div className="text-muted">{formatDate(alert.date)}</div>
                    </div>
                    <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text)" }}>{alert.title}</div>
                    <div className="text-muted" style={{ fontSize: 13 }}>{alert.detail}</div>
                  </>
                );

                if (alert.href) {
                  return (
                    <a
                      key={alert.id}
                      href={alert.href}
                      target="_blank"
                      rel="noreferrer"
                      className="filing-link-card"
                      style={{
                        display: "grid",
                        gap: 8,
                        textDecoration: "none",
                        borderColor: alert.level === "high" ? "rgba(255, 83, 83, 0.5)" : undefined,
                      }}
                    >
                      {content}
                    </a>
                  );
                }

                return (
                  <div
                    key={alert.id}
                    className="filing-link-card"
                    style={{ display: "grid", gap: 8, borderColor: alert.level === "high" ? "rgba(255, 83, 83, 0.5)" : undefined }}
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
          <div style={{ display: "grid", gap: 12 }}>
            {feed.map((entry) => {
              const content = (
                <>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                      <span className="pill">{formatFeedEntryType(entry.type)}</span>
                      <span className="pill">{entry.badge}</span>
                    </div>
                    <div className="text-muted">{formatDate(entry.date)}</div>
                  </div>
                  <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text)" }}>{entry.title}</div>
                  <div className="text-muted" style={{ fontSize: 13 }}>{entry.detail}</div>
                </>
              );

              if (entry.href) {
                return (
                  <a key={entry.id} href={entry.href} target="_blank" rel="noreferrer" className="filing-link-card" style={{ display: "grid", gap: 8, textDecoration: "none" }}>
                    {content}
                  </a>
                );
              }

              return (
                <div key={entry.id} className="filing-link-card" style={{ display: "grid", gap: 8 }}>
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

function Metric({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value ?? "?"}</div>
    </div>
  );
}

function formatFeedEntryType(type: string): string {
  if (type === "form144") {
    return "planned-sale";
  }
  return type;
}