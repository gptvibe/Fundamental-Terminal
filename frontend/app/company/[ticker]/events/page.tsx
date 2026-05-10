"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { FilingEventCategoryChart } from "@/components/charts/filing-event-category-chart";
import { CompanyResearchHeader } from "@/components/layout/company-research-header";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { Panel } from "@/components/ui/panel";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { getCompanyFilingEvents, getCompanyFilingEventsSummary } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { CompanyEventsResponse, CompanyFilingEventsSummaryResponse, FilingEventPayload } from "@/lib/types";

// ---------- filter definitions ----------
const FILTER_OPTIONS = [
  { key: "annual", label: "Annual (10-K)", forms: ["10-K", "10-K/A", "20-F", "20-F/A", "40-F"] },
  { key: "quarterly", label: "Quarterly (10-Q)", forms: ["10-Q", "10-Q/A"] },
  { key: "current", label: "Current (8-K)", forms: ["8-K", "8-K/A"] },
  { key: "proxy", label: "Proxy", forms: ["DEF 14A", "DEFA14A", "PRE 14A", "DEF 14C"] },
  { key: "insider", label: "Insider", forms: ["4", "5"] },
  { key: "late", label: "Late Notices", forms: ["NT 10-K", "NT 10-Q", "NT 20-F"] },
];

function matchesFilter(event: FilingEventPayload, activeKeys: Set<string>): boolean {
  if (activeKeys.size === 0) return true;
  const upperForm = event.form.toUpperCase();
  return [...activeKeys].some((key) => {
    const option = FILTER_OPTIONS.find((o) => o.key === key);
    return option?.forms.some((f) => f.toUpperCase() === upperForm);
  });
}

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
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set());
  const [amendmentsOnly, setAmendmentsOnly] = useState(false);

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

  const allEvents = useMemo(() => data?.events ?? [], [data?.events]);
  const events = useMemo(() => {
    let filtered = allEvents;
    if (activeFilters.size > 0) {
      filtered = filtered.filter((e) => matchesFilter(e, activeFilters));
    }
    if (amendmentsOnly) {
      filtered = filtered.filter((e) => e.is_amendment);
    }
    return filtered;
  }, [allEvents, activeFilters, amendmentsOnly]);

  const summary = summaryData?.summary ?? null;
  const pageCompany = company ?? data?.company ?? null;
  const effectiveRefreshState = data?.refresh ?? refreshState;
  const latestEventDate = allEvents[0]?.filing_date ?? allEvents[0]?.report_date ?? null;

  const categorySummary = useMemo(() => {
    const counts = new Map<string, number>();
    for (const event of allEvents) {
      counts.set(event.category, (counts.get(event.category) ?? 0) + 1);
    }
    return [...counts.entries()]
      .sort((left, right) => right[1] - left[1])
      .slice(0, 3)
      .map(([category, count]) => `${category}: ${count.toLocaleString()}`)
      .join(" · ");
  }, [allEvents]);

  const formCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const e of allEvents) {
      counts[e.form] = (counts[e.form] ?? 0) + 1;
    }
    return counts;
  }, [allEvents]);

  function toggleFilter(key: string) {
    setActiveFilters((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

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
          actionSubtitle="Refresh the filing feed or jump to the filings workspace for broader SEC coverage."
          primaryActionLabel="Refresh Filing Feed"
          primaryActionDescription="Queues a company refresh so the latest SEC filings are reloaded from SEC submissions."
          secondaryActionHref={`/company/${encodeURIComponent(ticker)}/filings`}
          secondaryActionLabel="Open Filings Workspace"
          secondaryActionDescription="Move from the event timeline back to the full SEC filing viewer."
          statusLines={[
            `Total events: ${(summary?.total_events ?? allEvents.length).toLocaleString()}`,
            `Latest event date: ${summary?.latest_event_date ? formatDate(summary.latest_event_date) : latestEventDate ? formatDate(latestEventDate) : "Pending"}`,
            categorySummary || "Event categories pending"
          ]}
          consoleEntries={consoleEntries}
          connectionState={connectionState}
        />
      }
      mainClassName="company-page-grid"
    >
      <CompanyResearchHeader
        ticker={ticker}
        title="Filing Events"
        companyName={pageCompany?.name ?? ticker}
        sector={pageCompany?.sector}
        description="Chronological timeline of SEC filings — annual reports, quarterly reports, 8-K current reports, proxy statements, insider filings, and late-filing notices — sourced from official SEC submissions."
        freshness={{
          cacheState: pageCompany?.cache_state ?? null,
          refreshState: effectiveRefreshState,
          loading: loading || workspaceLoading,
          hasData: Boolean(pageCompany || summary || allEvents.length),
          lastChecked: pageCompany?.last_checked ?? null,
          errors: [error, data?.error],
          detailLines: [
            `Total events: ${(summary?.total_events ?? allEvents.length).toLocaleString()}`,
            `Latest event: ${summary?.latest_event_date ? formatDate(summary.latest_event_date) : latestEventDate ? formatDate(latestEventDate) : "Pending"}`,
            categorySummary || "Event categories pending",
          ],
        }}
        freshnessPlacement="subtitle"
        factsLoading={(loading || workspaceLoading) && !pageCompany && !summary && !allEvents.length}
        summariesLoading={(loading || workspaceLoading) && !pageCompany && !summary && !allEvents.length}
        facts={[
          { label: "Ticker", value: ticker },
          { label: "Total Events", value: (summary?.total_events ?? allEvents.length).toLocaleString() },
          { label: "Unique Filings", value: (summary?.unique_accessions ?? 0).toLocaleString() },
          { label: "Latest Event", value: summary?.latest_event_date ? formatDate(summary.latest_event_date) : latestEventDate ? formatDate(latestEventDate) : "Pending" }
        ]}
        ribbonItems={[
          { label: "Event Source", value: "SEC EDGAR submissions", tone: "green" },
          { label: "Largest Amount", value: summary?.max_key_amount != null ? `$${Math.round(summary.max_key_amount).toLocaleString()}` : "Pending", tone: "gold" },
          { label: "Category Mix", value: categorySummary || "Pending", tone: "cyan" },
          { label: "Refresh", value: effectiveRefreshState?.job_id ? "Queued" : "Background-first", tone: effectiveRefreshState?.job_id ? "cyan" : "green" }
        ]}
        summaries={[
          { label: "Categories", value: Object.keys(summary?.categories ?? {}).length.toLocaleString(), accent: "cyan" },
          { label: "Top Category", value: categorySummary.split(" · ")[0] ?? "Pending", accent: "gold" },
          { label: "Source Policy", value: "Official/public only", accent: "green" },
          { label: "Last Checked", value: pageCompany?.last_checked ? formatDate(pageCompany.last_checked) : "Pending", accent: "cyan" }
        ]}
      />

      <Panel title="Event Categories" subtitle="Filing category breakdown across the full timeline">
        <FilingEventCategoryChart events={allEvents} />
      </Panel>

      <Panel
        title="Filing Timeline"
        subtitle="Chronological view of all SEC filings — use the filters to narrow by form type"
      >
        {/* Filter bar */}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          {FILTER_OPTIONS.map((option) => {
            const count = option.forms.reduce((sum, f) => sum + (formCounts[f] ?? 0), 0);
            const isActive = activeFilters.has(option.key);
            return (
              <button
                key={option.key}
                onClick={() => toggleFilter(option.key)}
                className={`pill${isActive ? " pill--active" : ""}`}
                style={{
                  cursor: "pointer",
                  border: "1px solid var(--border)",
                  background: isActive ? "var(--accent-cyan)" : "var(--surface-2)",
                  color: isActive ? "var(--background)" : "var(--text-muted)",
                  padding: "4px 10px",
                  borderRadius: 4,
                  fontSize: 12,
                  fontWeight: 500,
                }}
              >
                {option.label}{count > 0 ? ` (${count})` : ""}
              </button>
            );
          })}
          <button
            onClick={() => setAmendmentsOnly((prev) => !prev)}
            style={{
              cursor: "pointer",
              border: "1px solid var(--border)",
              background: amendmentsOnly ? "var(--accent-gold)" : "var(--surface-2)",
              color: amendmentsOnly ? "var(--background)" : "var(--text-muted)",
              padding: "4px 10px",
              borderRadius: 4,
              fontSize: 12,
              fontWeight: 500,
            }}
          >
            Amendments only
          </button>
          {(activeFilters.size > 0 || amendmentsOnly) && (
            <button
              onClick={() => { setActiveFilters(new Set()); setAmendmentsOnly(false); }}
              style={{
                cursor: "pointer",
                border: "1px solid var(--border)",
                background: "transparent",
                color: "var(--text-muted)",
                padding: "4px 10px",
                borderRadius: 4,
                fontSize: 12,
              }}
            >
              Clear filters
            </button>
          )}
        </div>

        {error || data?.error ? (
          <div className="text-muted">{error ?? data?.error}</div>
        ) : loading || workspaceLoading ? (
          <div className="text-muted">Loading filing events...</div>
        ) : events.length ? (
          <div style={{ display: "grid", gap: 12 }}>
            {events.map((event) => (
              <a
                key={`${event.accession_number ?? event.source_url}-${event.item_code ?? event.form}`}
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
                    {event.is_amendment && <span className="pill" style={{ color: "var(--accent-gold)" }}>Amendment</span>}
                    {event.is_late_filing && <span className="pill" style={{ color: "var(--accent-red, #e35)" }}>Late Notice</span>}
                    {event.item_code && event.item_code !== "UNSPECIFIED" && event.item_code !== event.form
                      ? <span className="pill">Item {event.item_code}</span>
                      : null}
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
        ) : allEvents.length ? (
          <div className="text-muted">No events match the active filters.</div>
        ) : (
          <div className="grid-empty-state" style={{ minHeight: 220 }}>
            <div className="grid-empty-kicker">Filing timeline</div>
            <div className="grid-empty-title">No filing events yet</div>
            <div className="grid-empty-copy">This page fills in once SEC submissions have been ingested for the selected company.</div>
          </div>
        )}
      </Panel>
    </CompanyWorkspaceShell>
  );
}