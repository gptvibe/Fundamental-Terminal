"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { CapitalMarketsSignalChart } from "@/components/charts/capital-markets-signal-chart";
import { ShareDilutionTrackerChart } from "@/components/charts/share-dilution-tracker-chart";
import { CompanyResearchHeader } from "@/components/layout/company-research-header";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { Panel } from "@/components/ui/panel";
import { StatusPill } from "@/components/ui/status-pill";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { getCompanyCapitalMarkets, getCompanyCapitalMarketsSummary, getCompanyFilingEvents } from "@/lib/api";
import { formatCompactNumber, formatDate } from "@/lib/format";
import type { CompanyCapitalMarketsSummaryResponse, CompanyCapitalRaisesResponse, CompanyEventsResponse } from "@/lib/types";

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
  const [capitalSummaryData, setCapitalSummaryData] = useState<CompanyCapitalMarketsSummaryResponse | null>(null);
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
        const [eventsResponse, capitalRaisesResponse, capitalSummary] = await Promise.all([
          getCompanyFilingEvents(ticker),
          getCompanyCapitalMarkets(ticker),
          getCompanyCapitalMarketsSummary(ticker)
        ]);
        if (!cancelled) {
          setEventsData(eventsResponse);
          setCapitalRaisesData(capitalRaisesResponse);
          setCapitalSummaryData(capitalSummary);
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
  const capitalSummary = capitalSummaryData?.summary ?? null;
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
            `Capital raise filings: ${(capitalSummary?.total_filings ?? capitalRaises.length).toLocaleString()}`
          ]}
          consoleEntries={consoleEntries}
          connectionState={connectionState}
        />
      }
      mainClassName="company-page-grid"
    >
      <CompanyResearchHeader
        ticker={ticker}
        title="Capital Markets"
        companyName={company?.name ?? eventsData?.company?.name ?? ticker}
        sector={company?.sector ?? eventsData?.company?.sector ?? null}
        cacheState={company?.cache_state ?? eventsData?.company?.cache_state ?? null}
        description="SEC-first financing workspace covering registration activity, dilution, debt changes, and financing-related current reports."
        aside={effectiveRefreshState ? <StatusPill state={effectiveRefreshState} /> : undefined}
        facts={[
          { label: "Ticker", value: ticker },
          { label: "Latest Event", value: latestEventDate ? formatDate(latestEventDate) : "Pending" },
          { label: "Capital Raises", value: (capitalSummary?.total_filings ?? capitalRaises.length).toLocaleString() },
          { label: "Late Filer Notices", value: (capitalSummary?.late_filer_notices ?? 0).toLocaleString() },
        ]}
        ribbonItems={[
          { label: "Capital Raises", value: latestCapitalRaiseDate ? formatDate(latestCapitalRaiseDate) : "Pending", tone: "gold" },
          { label: "Financing Events", value: latestEventDate ? formatDate(latestEventDate) : "Pending", tone: "cyan" },
          { label: "Sources", value: "SEC registration filings + 8-K current reports", tone: "green" },
          { label: "Refresh", value: effectiveRefreshState?.job_id ? "Queued" : "Background-first", tone: effectiveRefreshState?.job_id ? "cyan" : "green" },
        ]}
        summaries={[
          { label: "Financing Events", value: capitalMarketsEvents.length.toLocaleString(), accent: "cyan" },
          { label: "Capital Raises", value: (capitalSummary?.total_filings ?? capitalRaises.length).toLocaleString(), accent: "gold" },
          {
            label: "Largest Offering",
            value: capitalSummary?.max_offering_amount != null ? `$${Math.round(capitalSummary.max_offering_amount).toLocaleString()}` : "?",
            accent: "gold",
          },
          { label: "Debt Change", value: formatCompactNumber(latestFinancial?.debt_changes), accent: "red" },
        ]}
      />

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
          <div className="workspace-card-stack">
            {capitalRaises.map((filing) => (
              <a
                key={filing.accession_number ?? `${filing.form}-${filing.filing_date ?? filing.report_date ?? filing.source_url}`}
                href={filing.source_url}
                target="_blank"
                rel="noreferrer"
                className="filing-link-card workspace-card-link"
              >
                <div className="workspace-card-row">
                  <div className="workspace-pill-row">
                    <span className="pill">{filing.form}</span>
                    <span className="pill">Registration</span>
                  </div>
                  <div className="text-muted">{formatDate(filing.filing_date ?? filing.report_date)}</div>
                </div>
                <div className="workspace-card-title">{filing.summary}</div>
                <div className="text-muted workspace-card-copy">
                  {filing.event_type ? `Type: ${filing.event_type}` : "Type: pending"}
                  {filing.security_type ? ` · Security: ${filing.security_type}` : ""}
                  {filing.offering_amount != null ? ` · Amount: $${Math.round(filing.offering_amount).toLocaleString()}` : ""}
                  {filing.shelf_size != null ? ` · Shelf: $${Math.round(filing.shelf_size).toLocaleString()}` : ""}
                  {filing.is_late_filer ? " · Late filer notice" : ""}
                </div>
                <div className="text-muted workspace-card-copy">
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
          <div className="workspace-card-stack">
            {capitalMarketsEvents.map((event) => (
              <a
                key={event.accession_number ?? `${event.form}-${event.filing_date ?? event.report_date ?? event.source_url}`}
                href={event.source_url}
                target="_blank"
                rel="noreferrer"
                className="filing-link-card workspace-card-link"
              >
                <div className="workspace-card-row">
                  <div className="workspace-pill-row">
                    <span className="pill">{event.form}</span>
                    <span className="pill">{event.category}</span>
                    {event.item_code && event.item_code !== "UNSPECIFIED" ? <span className="pill">Item {event.item_code}</span> : null}
                    {event.items ? <span className="pill">Items {event.items}</span> : null}
                  </div>
                  <div className="text-muted">{formatDate(event.filing_date ?? event.report_date)}</div>
                </div>
                <div className="workspace-card-title">{event.summary}</div>
                {event.key_amounts.length ? (
                  <div className="text-muted workspace-card-copy">
                    Key amounts: {event.key_amounts.slice(0, 2).map((amount) => `$${Math.round(amount).toLocaleString()}`).join(" · ")}
                  </div>
                ) : null}
                <div className="text-muted workspace-card-copy">
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