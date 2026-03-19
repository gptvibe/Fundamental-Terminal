"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { FilingEventCategoryChart } from "@/components/charts/filing-event-category-chart";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { Panel } from "@/components/ui/panel";
import { StatusPill } from "@/components/ui/status-pill";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { getCompanyFilingEvents, getCompanyFilingEventsSummary } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { CompanyEventsResponse, CompanyFilingEventsSummaryResponse } from "@/lib/types";

export default function CompanyEventsPage() {
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
  const [data, setData] = useState<CompanyEventsResponse | null>(null);
  const [summaryData, setSummaryData] = useState<CompanyFilingEventsSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        const [response, summary] = await Promise.all([
          getCompanyFilingEvents(ticker),
          getCompanyFilingEventsSummary(ticker)
        ]);
        if (!cancelled) {
          setData(response);
          setSummaryData(summary);
        }
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError instanceof Error ? nextError.message : "Unable to load filing events");
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

  const events = useMemo(() => data?.events ?? [], [data?.events]);
  const summary = summaryData?.summary ?? null;
  const pageCompany = company ?? data?.company ?? null;
  const effectiveRefreshState = data?.refresh ?? refreshState;
  const latestEventDate = events[0]?.filing_date ?? events[0]?.report_date ?? null;
  const categorySummary = useMemo(() => {
    const counts = new Map<string, number>();
    for (const event of events) {
      counts.set(event.category, (counts.get(event.category) ?? 0) + 1);
    }
    return [...counts.entries()]
      .sort((left, right) => right[1] - left[1])
      .slice(0, 3)
      .map(([category, count]) => `${category}: ${count.toLocaleString()}`)
      .join(" · ");
  }, [events]);

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
          actionSubtitle="Refresh current reports or jump to the filings workspace for broader SEC coverage."
          primaryActionLabel="Refresh Event Feed"
          primaryActionDescription="Queues a company refresh so the latest 8-K current reports are reloaded from SEC submissions."
          secondaryActionHref={`/company/${encodeURIComponent(ticker)}/filings`}
          secondaryActionLabel="Open Filings Workspace"
          secondaryActionDescription="Move from event intelligence back to the full SEC filing timeline and filing viewer."
          statusLines={[
            `8-K events: ${(summary?.total_events ?? events.length).toLocaleString()}`,
            `Latest event date: ${summary?.latest_event_date ? formatDate(summary.latest_event_date) : latestEventDate ? formatDate(latestEventDate) : "Pending"}`,
            categorySummary || "Event categories pending"
          ]}
          consoleEntries={consoleEntries}
          connectionState={connectionState}
        />
      }
      mainClassName="company-page-grid"
    >
      <Panel title="Event Feed" subtitle={pageCompany?.name ?? ticker} aside={effectiveRefreshState ? <StatusPill state={effectiveRefreshState} /> : undefined}>
        <div className="metric-grid">
          <Metric label="Ticker" value={ticker} />
          <Metric label="Current Reports" value={(summary?.total_events ?? events.length).toLocaleString()} />
          <Metric label="Unique Filings" value={(summary?.unique_accessions ?? 0).toLocaleString()} />
          <Metric label="Latest Event" value={summary?.latest_event_date ? formatDate(summary.latest_event_date) : latestEventDate ? formatDate(latestEventDate) : "Pending"} />
          <Metric label="Largest Amount" value={summary?.max_key_amount != null ? `$${Math.round(summary.max_key_amount).toLocaleString()}` : "Pending"} />
          <Metric label="Last Checked" value={pageCompany?.last_checked ? formatDate(pageCompany.last_checked) : null} />
        </div>
      </Panel>

      <Panel title="Event Categories" subtitle="Item-based classification of current reports so the filing stream is easier to scan">
        <FilingEventCategoryChart events={events} />
      </Panel>

      <Panel title="Recent 8-K Timeline" subtitle="Current reports classified into earnings, leadership, financing, and other event buckets">
        {error || data?.error ? (
          <div className="text-muted">{error ?? data?.error}</div>
        ) : loading || workspaceLoading ? (
          <div className="text-muted">Loading filing events...</div>
        ) : events.length ? (
          <div style={{ display: "grid", gap: 12 }}>
            {events.map((event) => (
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
                    Key amounts: {event.key_amounts.slice(0, 3).map((amount) => `$${Math.round(amount).toLocaleString()}`).join(" · ")}
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
            <div className="grid-empty-kicker">Event intelligence</div>
            <div className="grid-empty-title">No 8-K events yet</div>
            <div className="grid-empty-copy">This page fills in once SEC submissions include current reports for the selected company.</div>
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