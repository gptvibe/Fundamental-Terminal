"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { CapitalMarketsSignalChart } from "@/components/charts/capital-markets-signal-chart";
import { ShareDilutionTrackerChart } from "@/components/charts/share-dilution-tracker-chart";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { Panel } from "@/components/ui/panel";
import { StatusPill } from "@/components/ui/status-pill";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { getCompanyEvents } from "@/lib/api";
import { formatCompactNumber, formatDate } from "@/lib/format";
import type { CompanyEventsResponse } from "@/lib/types";

export default function CompanyCapitalMarketsPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(params.ticker).toUpperCase();
  const {
    company,
    financials,
    loading: workspaceLoading,
    refreshing,
    refreshState,
    consoleEntries,
    connectionState,
    queueRefresh,
    reloadKey
  } = useCompanyWorkspace(ticker);
  const [eventsData, setEventsData] = useState<CompanyEventsResponse | null>(null);
  const [eventsLoading, setEventsLoading] = useState(true);
  const [eventsError, setEventsError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setEventsLoading(true);
        setEventsError(null);
        const response = await getCompanyEvents(ticker);
        if (!cancelled) {
          setEventsData(response);
        }
      } catch (nextError) {
        if (!cancelled) {
          setEventsError(nextError instanceof Error ? nextError.message : "Unable to load capital-markets events");
        }
      } finally {
        if (!cancelled) {
          setEventsLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [reloadKey, ticker]);

  const events = useMemo(() => eventsData?.events ?? [], [eventsData?.events]);
  const capitalMarketsEvents = useMemo(
    () => events.filter((event) => event.category === "Financing" || event.category === "Capital Markets"),
    [events]
  );
  const latestEventDate = capitalMarketsEvents[0]?.filing_date ?? capitalMarketsEvents[0]?.report_date ?? null;
  const latestFinancial = financials[0] ?? null;
  const effectiveRefreshState = eventsData?.refresh ?? refreshState;

  return (
    <CompanyWorkspaceShell
      rail={
        <CompanyUtilityRail
          ticker={ticker}
          companyName={company?.name ?? eventsData?.company?.name ?? null}
          sector={company?.sector ?? eventsData?.company?.sector ?? null}
          refreshState={effectiveRefreshState}
          refreshing={refreshing}
          onRefresh={() => queueRefresh()}
          actionTitle="Next Steps"
          actionSubtitle="Refresh financing signals or move into the events workspace for the full current-report feed."
          primaryActionLabel="Refresh Capital Signals"
          primaryActionDescription="Queues a company refresh so dilution, debt changes, and financing-related current reports stay current."
          secondaryActionHref={`/company/${encodeURIComponent(ticker)}/events`}
          secondaryActionLabel="Open Event Feed"
          secondaryActionDescription="Review the full 8-K stream with earnings, leadership, deal, and financing categories."
          statusLines={[
            `Financing events: ${capitalMarketsEvents.length.toLocaleString()}`,
            `Latest financing event: ${latestEventDate ? formatDate(latestEventDate) : "Pending"}`,
            `Latest debt changes: ${formatCompactNumber(latestFinancial?.debt_changes ?? null)}`
          ]}
          consoleEntries={consoleEntries}
          connectionState={connectionState}
        />
      }
      mainClassName="company-page-grid"
    >
      <Panel title="Capital Markets" subtitle={company?.name ?? ticker} aside={effectiveRefreshState ? <StatusPill state={effectiveRefreshState} /> : undefined}>
        <div className="metric-grid">
          <Metric label="Ticker" value={ticker} />
          <Metric label="Financing Events" value={capitalMarketsEvents.length.toLocaleString()} />
          <Metric label="Latest Event" value={latestEventDate ? formatDate(latestEventDate) : "Pending"} />
          <Metric label="Debt Changes" value={formatCompactNumber(latestFinancial?.debt_changes ?? null)} />
        </div>
      </Panel>

      <Panel title="Financing Signal Tracker" subtitle="Debt-change history from filings overlaid with financing and capital-markets current reports by year">
        <CapitalMarketsSignalChart financials={financials} events={capitalMarketsEvents} />
      </Panel>

      <Panel title="Share Dilution Tracker" subtitle="Shares outstanding trend with period-over-period dilution rates from reported filings">
        <ShareDilutionTrackerChart financials={financials} />
      </Panel>

      <Panel title="Recent Financing Events" subtitle="Filtered current reports that look most relevant for debt, equity, and capital-structure monitoring">
        {eventsError || eventsData?.error ? (
          <div className="text-muted">{eventsError ?? eventsData?.error}</div>
        ) : eventsLoading || workspaceLoading ? (
          <div className="text-muted">Loading financing events...</div>
        ) : capitalMarketsEvents.length ? (
          <div style={{ display: "grid", gap: 12 }}>
            {capitalMarketsEvents.map((event) => (
              <a
                key={event.accession_number ?? `${event.form}-${event.filing_date ?? event.report_date ?? event.source_url}`}
                href={event.source_url}
                target="_blank"
                rel="noreferrer"
                className="filing-link-card"
                style={{ display: "grid", gap: 8, textDecoration: "none" }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                    <span className="pill">{event.form}</span>
                    <span className="pill">{event.category}</span>
                    {event.items ? <span className="pill">Items {event.items}</span> : null}
                  </div>
                  <div className="text-muted">{formatDate(event.filing_date ?? event.report_date)}</div>
                </div>
                <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text)" }}>{event.summary}</div>
                <div className="text-muted" style={{ fontSize: 13 }}>
                  {event.accession_number ?? "Accession pending"}
                  {event.primary_document ? ` · ${event.primary_document}` : ""}
                </div>
              </a>
            ))}
          </div>
        ) : (
          <div className="grid-empty-state" style={{ minHeight: 220 }}>
            <div className="grid-empty-kicker">Capital markets</div>
            <div className="grid-empty-title">No financing events yet</div>
            <div className="grid-empty-copy">This page fills in once filings include financing-related current reports or debt-change history.</div>
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