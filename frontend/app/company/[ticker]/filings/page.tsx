"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { clsx } from "clsx";

import { FilingEventCategoryChart } from "@/components/charts/filing-event-category-chart";
import { ChangesSinceLastFilingCard } from "@/components/company/changes-since-last-filing-card";
import { FilingDocumentViewer } from "@/components/filings/filing-document-viewer";
import { FilingParserInsights } from "@/components/filings/filing-parser-insights";
import { FilingRiskSignalsPanel } from "@/components/filings/filing-risk-signals-panel";
import { CompanyFilingsTimeline } from "@/components/filings/company-filings-timeline";
import { CompanyResearchHeader } from "@/components/layout/company-research-header";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { DataQualityDiagnostics } from "@/components/ui/data-quality-diagnostics";
import { Panel } from "@/components/ui/panel";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { getCompanyChangesSinceLastFiling, getCompanyFilingEvents, getCompanyFilingInsights, getCompanyFilingRiskSignals, getCompanyFilings } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { CompanyChangesSinceLastFilingResponse, CompanyEventsResponse, CompanyFilingInsightsResponse, CompanyFilingRiskSignalsResponse, CompanyFilingsResponse } from "@/lib/types";

export default function CompanyFilingsPage() {
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
  const [data, setData] = useState<CompanyFilingsResponse | null>(null);
  const [insightsData, setInsightsData] = useState<CompanyFilingInsightsResponse | null>(null);
  const [insightsLoading, setInsightsLoading] = useState(true);
  const [insightsError, setInsightsError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedSourceUrl, setSelectedSourceUrl] = useState<string | null>(null);
  const [eventsData, setEventsData] = useState<CompanyEventsResponse | null>(null);
  const [eventsLoading, setEventsLoading] = useState(true);
  const [eventsError, setEventsError] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [changesData, setChangesData] = useState<CompanyChangesSinceLastFilingResponse | null>(null);
  const [changesLoading, setChangesLoading] = useState(true);
  const [changesError, setChangesError] = useState<string | null>(null);
  const [filingRiskSignalsData, setFilingRiskSignalsData] = useState<CompanyFilingRiskSignalsResponse | null>(null);
  const [filingRiskSignalsLoading, setFilingRiskSignalsLoading] = useState(true);
  const [filingRiskSignalsError, setFilingRiskSignalsError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        setData(null);
        const response = await getCompanyFilings(ticker);
        if (cancelled) {
          return;
        }
        setData(response);
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError instanceof Error ? nextError.message : "Unable to load filings");
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

  useEffect(() => {
    let cancelled = false;

    async function loadFilingRiskSignals() {
      try {
        setFilingRiskSignalsLoading(true);
        setFilingRiskSignalsError(null);
        setFilingRiskSignalsData(null);
        const response = await getCompanyFilingRiskSignals(ticker);
        if (!cancelled) {
          setFilingRiskSignalsData(response);
        }
      } catch (nextError) {
        if (!cancelled) {
          setFilingRiskSignalsError(nextError instanceof Error ? nextError.message : "Unable to load filing risk signals");
        }
      } finally {
        if (!cancelled) {
          setFilingRiskSignalsLoading(false);
        }
      }
    }

    void loadFilingRiskSignals();
    return () => {
      cancelled = true;
    };
  }, [reloadKey, ticker]);

  useEffect(() => {
    let cancelled = false;

    async function loadChanges() {
      try {
        setChangesLoading(true);
        setChangesError(null);
        const response = await getCompanyChangesSinceLastFiling(ticker);
        if (!cancelled) {
          setChangesData(response);
        }
      } catch (nextError) {
        if (!cancelled) {
          setChangesError(nextError instanceof Error ? nextError.message : "Unable to load filing changes");
        }
      } finally {
        if (!cancelled) {
          setChangesLoading(false);
        }
      }
    }

    void loadChanges();
    return () => {
      cancelled = true;
    };
  }, [reloadKey, ticker]);

  useEffect(() => {
    let cancelled = false;

    async function loadInsights() {
      try {
        setInsightsLoading(true);
        setInsightsError(null);
        setInsightsData(null);
        const response = await getCompanyFilingInsights(ticker);
        if (cancelled) {
          return;
        }
        setInsightsData(response);
      } catch (nextError) {
        if (!cancelled) {
          setInsightsError(nextError instanceof Error ? nextError.message : "Unable to load filing insights");
        }
      } finally {
        if (!cancelled) {
          setInsightsLoading(false);
        }
      }
    }

    void loadInsights();
    return () => {
      cancelled = true;
    };
  }, [reloadKey, ticker]);

  useEffect(() => {
    let cancelled = false;

    async function loadEvents() {
      try {
        setEventsLoading(true);
        setEventsError(null);
        const response = await getCompanyFilingEvents(ticker);
        if (!cancelled) {
          setEventsData(response);
        }
      } catch (nextError) {
        if (!cancelled) {
          setEventsError(nextError instanceof Error ? nextError.message : "Unable to load filing events");
        }
      } finally {
        if (!cancelled) {
          setEventsLoading(false);
        }
      }
    }

    void loadEvents();
    return () => {
      cancelled = true;
    };
  }, [reloadKey, ticker]);

  const insights = useMemo(() => (insightsData?.insights == null ? [] : insightsData.insights), [insightsData?.insights]);
  const pageCompany = company ?? data?.company ?? null;
  const filings = useMemo(() => data?.filings ?? [], [data?.filings]);
  const latestFilingDate = useMemo(
    () => filings.reduce<string | null>((latest, filing) => {
      const nextDate = filing.filing_date ?? filing.report_date;
      if (!nextDate) {
        return latest;
      }
      return !latest || nextDate > latest ? nextDate : latest;
    }, null),
    [filings]
  );
  const formCounts = useMemo(() => {
    const counts = new Map<string, number>();
    filings.forEach((filing) => counts.set(filing.form, (counts.get(filing.form) ?? 0) + 1));
    return Array.from(counts.entries())
      .map(([form, count]) => ({ form, count }))
      .sort((left, right) => right.count - left.count || left.form.localeCompare(right.form));
  }, [filings]);
  const allEvents = useMemo(() => eventsData?.events ?? [], [eventsData?.events]);
  const eventCategories = useMemo(() => {
    const seen = new Set<string>();
    for (const event of allEvents) seen.add(event.category);
    return [...seen].sort();
  }, [allEvents]);
  const filteredEvents = useMemo(
    () => (activeCategory ? allEvents.filter((e) => e.category === activeCategory) : allEvents),
    [allEvents, activeCategory]
  );
  const effectiveRefreshState = data?.refresh ?? refreshState;
  const sourceLabel = data?.timeline_source === "cached_financials" ? "Cached annual and quarterly filings" : "SEC submissions";
  const selectedFiling = useMemo(
    () => filings.find((filing) => filing.source_url === selectedSourceUrl) ?? filings[0] ?? null,
    [filings, selectedSourceUrl]
  );

  useEffect(() => {
    if (!filings.length) {
      setSelectedSourceUrl(null);
      return;
    }
    if (!selectedSourceUrl || !filings.some((filing) => filing.source_url === selectedSourceUrl)) {
      setSelectedSourceUrl(filings[0].source_url);
    }
  }, [filings, selectedSourceUrl]);

  return (
    <CompanyWorkspaceShell
      rail={
        <CompanyUtilityRail
          ticker={ticker}
          companyName={pageCompany?.name ?? null}
          sector={pageCompany?.sector ?? null}
          refreshState={effectiveRefreshState}
          refreshing={refreshing}
          onRefresh={() => queueRefresh()}
          actionTitle="Next Steps"
          actionSubtitle="Refresh recent filings or jump back into the financial statements workspace."
          primaryActionLabel="Refresh Filing Data"
          primaryActionDescription="Queues a company refresh so the SEC-first filing timeline and linked report history stay current."
          secondaryActionHref={`/company/${encodeURIComponent(ticker)}/financials`}
          secondaryActionLabel="Open Financials"
          secondaryActionDescription="Move from the filing timeline into statement tables, balance-sheet charts, and cash-flow history."
          statusLines={[
            `Recent filings available: ${filings.length.toLocaleString()}`,
            `Latest filing date: ${latestFilingDate ? formatDate(latestFilingDate) : "Pending"}`,
            `Timeline source: ${sourceLabel}`
          ]}
          consoleEntries={consoleEntries}
          connectionState={connectionState}
        />
      }
      mainClassName="company-page-grid"
    >
      <CompanyResearchHeader
        ticker={ticker}
        title="Filings"
        companyName={pageCompany?.name ?? ticker}
        sector={pageCompany?.sector}
        description="SEC-first filing workflow keeps the recent timeline, parser snapshot, and document viewer available from cache while background refresh jobs backfill newer submissions."
        freshness={{
          cacheState: pageCompany?.cache_state ?? null,
          refreshState: effectiveRefreshState,
          loading: loading || workspaceLoading || insightsLoading || eventsLoading,
          hasData: Boolean(pageCompany || filings.length || insightsData || allEvents.length),
          lastChecked: pageCompany?.last_checked ?? null,
          errors: [error, insightsError, eventsError],
          detailLines: [
            `Recent filings: ${filings.length.toLocaleString()}`,
            `Timeline source: ${sourceLabel}`,
            `Classified 8-K events: ${allEvents.length.toLocaleString()}`,
          ],
        }}
        freshnessPlacement="subtitle"
        factsLoading={(loading || workspaceLoading) && !pageCompany && !filings.length && !allEvents.length}
        summariesLoading={(loading || workspaceLoading) && !pageCompany && !filings.length && !allEvents.length}
        facts={[
          { label: "Ticker", value: ticker },
          { label: "Recent Filings", value: filings.length.toLocaleString() },
          { label: "Latest Filing", value: latestFilingDate ? formatDate(latestFilingDate) : "Pending" },
          { label: "Last Checked", value: pageCompany?.last_checked ? formatDate(pageCompany.last_checked) : null }
        ]}
        ribbonItems={[
          { label: "Timeline Source", value: sourceLabel, tone: data?.timeline_source === "cached_financials" ? "gold" : "green" },
          { label: "Primary Inputs", value: "SEC submissions", tone: "green" },
          { label: "8-K Event Feed", value: allEvents.length ? `${allEvents.length.toLocaleString()} classified` : "Pending", tone: "cyan" },
          { label: "Refresh", value: effectiveRefreshState?.job_id ? "Queued" : "Background-first", tone: effectiveRefreshState?.job_id ? "cyan" : "green" }
        ]}
        summaries={[
          { label: "Tracked Forms", value: formCounts.length.toLocaleString(), accent: "cyan" },
          { label: "Event Categories", value: eventCategories.length.toLocaleString(), accent: "gold" },
          { label: "Selected Filing", value: selectedFiling?.form ?? "Pending", accent: "green" },
          { label: "Viewer Mode", value: "In-workspace SEC HTML", accent: "cyan" }
        ]}
      />

      <Panel title="Filing Diagnostics" subtitle="Timeline freshness and parser coverage for the SEC filing workspace">
        <DataQualityDiagnostics diagnostics={insightsData?.diagnostics ?? data?.diagnostics} />
      </Panel>

      <Panel title="Recent Filing Timeline" subtitle="SEC-first view of annual, quarterly, and current reports with direct source links">
        <CompanyFilingsTimeline
          filings={filings}
          loading={loading || workspaceLoading}
          error={error ?? data?.error ?? null}
          timelineSource={data?.timeline_source ?? null}
          selectedSourceUrl={selectedFiling?.source_url ?? null}
          onSelectFiling={(filing) => setSelectedSourceUrl(filing.source_url)}
        />
      </Panel>

      <Panel title="Filing Parser Snapshot" subtitle="Fast parse of recent 10-K/10-Q HTML filings">
        <FilingParserInsights
          insights={insights}
          loading={insightsLoading || workspaceLoading}
          error={insightsError}
          refresh={insightsData?.refresh == null ? refreshState : insightsData.refresh}
        />
      </Panel>

      <Panel title="Filing text signals" subtitle="Risk language extracted from cached 10-K, 10-Q, and 8-K filing text">
        <FilingRiskSignalsPanel payload={filingRiskSignalsData} loading={filingRiskSignalsLoading || workspaceLoading} error={filingRiskSignalsError} />
      </Panel>

      <Panel title="High-Signal Filing Changes" subtitle="Curated filing-text changes on the brief, full evidence and supporting deltas here in the drill-down">
        {changesError && !changesData ? (
          <div className="text-muted">{changesError}</div>
        ) : changesLoading && !changesData ? (
          <div className="text-muted">Loading enriched filing change intelligence...</div>
        ) : (
          <ChangesSinceLastFilingCard ticker={ticker} reloadKey={reloadKey} initialPayload={changesData} detailMode="full" />
        )}
      </Panel>

      <Panel title="Filing Viewer" subtitle="Open the selected SEC document inside the workspace without leaving the terminal">
        <FilingDocumentViewer ticker={ticker} filing={selectedFiling} />
      </Panel>

      <Panel title="Form Coverage" subtitle="See which report types are most active in the current filing window">
        <div className="filing-count-grid">
          {formCounts.length ? (
            formCounts.map((entry) => (
              <div key={entry.form} className="filing-count-card">
                <div className="filing-count-form">{entry.form}</div>
                <div className="filing-count-value">{entry.count.toLocaleString()}</div>
              </div>
            ))
          ) : (
            <div className="sparkline-note">Filing counts will appear here once recent SEC submissions are available.</div>
          )}
        </div>
      </Panel>

      <Panel title="8-K Event Activity" subtitle="Distribution of current reports by category so filing patterns are visible at a glance">
        <FilingEventCategoryChart events={allEvents} />
      </Panel>

      <Panel
        title="Material 8-K Events"
        subtitle="Categorized timeline of current reports — use the filters to narrow to a specific event type"
        aside={
          eventCategories.length ? (
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <button
                className={clsx("ticker-button", "filing-filter-button", activeCategory === null && "is-active")}
                onClick={() => setActiveCategory(null)}
              >
                All
              </button>
              {eventCategories.map((cat) => (
                <button
                  key={cat}
                  className={clsx("ticker-button", "filing-filter-button", activeCategory === cat && "is-active")}
                  onClick={() => setActiveCategory((prev) => (prev === cat ? null : cat))}
                >
                  {cat}
                </button>
              ))}
            </div>
          ) : undefined
        }
      >
        {eventsError ?? eventsData?.error ? (
          <div className="text-muted">{eventsError ?? eventsData?.error}</div>
        ) : eventsLoading ? (
          <div className="text-muted">Loading 8-K events...</div>
        ) : filteredEvents.length ? (
          <div style={{ display: "grid", gap: 12 }}>
            {filteredEvents.map((event) => (
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
                    {event.item_code && event.item_code !== "UNSPECIFIED" ? <span className="pill">Item {event.item_code}</span> : null}
                    {event.items ? <span className="pill">Items {event.items}</span> : null}
                  </div>
                  <div className="text-muted">{formatDate(event.filing_date ?? event.report_date)}</div>
                </div>
                <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text)" }}>{event.summary}</div>
                {event.key_amounts.length ? (
                  <div className="text-muted" style={{ fontSize: 13 }}>
                    Key amounts: {event.key_amounts.slice(0, 3).map((a) => `$${Math.round(a).toLocaleString()}`).join(" · ")}
                  </div>
                ) : null}
                <div className="text-muted" style={{ fontSize: 13 }}>
                  {event.accession_number ?? "Accession pending"}
                  {event.primary_document ? ` · ${event.primary_document}` : ""}
                </div>
              </a>
            ))}
          </div>
        ) : (
          <div className="grid-empty-state" style={{ minHeight: 220 }}>
            <div className="grid-empty-kicker">8-K event intelligence</div>
            <div className="grid-empty-title">{activeCategory ? `No ${activeCategory} events` : "No 8-K events yet"}</div>
            <div className="grid-empty-copy">
              {activeCategory
                ? `No current reports are classified under ${activeCategory}. Try a different category or clear the filter.`
                : "This panel fills in once SEC submissions include current reports for the selected company."}
            </div>
          </div>
        )}
      </Panel>
    </CompanyWorkspaceShell>
  );
}

