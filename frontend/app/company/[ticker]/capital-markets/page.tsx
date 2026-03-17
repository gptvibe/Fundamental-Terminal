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
import { getCompanyCapitalRaises, getCompanyEvents } from "@/lib/api";
import { formatCompactNumber, formatDate } from "@/lib/format";
import type { CompanyCapitalRaisesResponse, CompanyEventsResponse } from "@/lib/types";

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
  const [capitalRaisesData, setCapitalRaisesData] = useState<CompanyCapitalRaisesResponse | null>(null);
  const [capitalRaisesLoading, setCapitalRaisesLoading] = useState(true);
  const [capitalRaisesError, setCapitalRaisesError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setEventsLoading(true);
        setCapitalRaisesLoading(true);
        setEventsError(null);
        setCapitalRaisesError(null);
        const [eventsResponse, capitalRaisesResponse] = await Promise.all([
          getCompanyEvents(ticker),
          getCompanyCapitalRaises(ticker)
        ]);
        if (!cancelled) {
          setEventsData(eventsResponse);
          setCapitalRaisesData(capitalRaisesResponse);
        }
      } catch (nextError) {
        if (!cancelled) {
          setEventsError(nextError instanceof Error ? nextError.message : "Unable to load capital-markets events");
          setCapitalRaisesError(nextError instanceof Error ? nextError.message : "Unable to load capital-raise filings");
        }
      } finally {
        if (!cancelled) {
          setEventsLoading(false);
          setCapitalRaisesLoading(false);
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
  const capitalRaises = useMemo(() => capitalRaisesData?.filings ?? [], [capitalRaisesData?.filings]);
  const latestCapitalRaiseDate = capitalRaises[0]?.filing_date ?? capitalRaises[0]?.report_date ?? null;
  const latestFinancial = financials[0] ?? null;
  const effectiveRefreshState = capitalRaisesData?.refresh ?? eventsData?.refresh ?? refreshState;

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
            `Capital raise filings: ${capitalRaises.length.toLocaleString()}`
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
          <Metric label="Capital Raises" value={capitalRaises.length.toLocaleString()} />
        </div>
      </Panel>

      <Panel title="Financing Signal Tracker" subtitle="Debt-change history from filings overlaid with financing and capital-markets current reports by year">
        <CapitalMarketsSignalChart financials={financials} events={capitalMarketsEvents} />
      </Panel>

      <Panel title="Share Dilution Tracker" subtitle="Shares outstanding trend with period-over-period dilution rates from reported filings">
        <ShareDilutionTrackerChart financials={financials} />
      </Panel>

      <Panel title="Capital Raise Filings" subtitle="Registration filings (S-1/S-3/F-1 and related amendments) with direct SEC links">
        {capitalRaisesError || capitalRaisesData?.error ? (
          <div className="text-muted">{capitalRaisesError ?? capitalRaisesData?.error}</div>
        ) : capitalRaisesLoading || workspaceLoading ? (
          <div className="text-muted">Loading capital-raise filings...</div>
        ) : capitalRaises.length ? (
          <div style={{ display: "grid", gap: 12 }}>
            {capitalRaises.map((filing) => (
              <a
                key={filing.accession_number ?? `${filing.form}-${filing.filing_date ?? filing.report_date ?? filing.source_url}`}
                href={filing.source_url}
                target="_blank"
                rel="noreferrer"
                className="filing-link-card"
                style={{ display: "grid", gap: 8, textDecoration: "none" }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                    <span className="pill">{filing.form}</span>
                    <span className="pill">Registration</span>
                  </div>
                  <div className="text-muted">{formatDate(filing.filing_date ?? filing.report_date)}</div>
                </div>
                <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text)" }}>{filing.summary}</div>
                <div className="text-muted" style={{ fontSize: 13 }}>
                  {filing.accession_number ?? "Accession pending"}
                  {filing.primary_document ? ` · ${filing.primary_document}` : ""}
                </div>
              </a>
            ))}
          </div>
        ) : (
          <div className="grid-empty-state" style={{ minHeight: 220 }}>
            <div className="grid-empty-kicker">Capital raises</div>
            <div className="grid-empty-title">No registration filings yet</div>
            <div className="grid-empty-copy">This section populates when SEC submissions include capital-raise registration forms for this company.</div>
          </div>
        )}
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