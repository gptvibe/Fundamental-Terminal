"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { FilingDocumentViewer } from "@/components/filings/filing-document-viewer";
import { FilingParserInsights } from "@/components/filings/filing-parser-insights";
import { CompanyFilingsTimeline } from "@/components/filings/company-filings-timeline";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { Panel } from "@/components/ui/panel";
import { StatusPill } from "@/components/ui/status-pill";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { getCompanyFilingInsights, getCompanyFilings } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { CompanyFilingInsightsResponse, CompanyFilingsResponse } from "@/lib/types";

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
      <Panel title="Filings" subtitle={pageCompany?.name ?? ticker} aside={effectiveRefreshState ? <StatusPill state={effectiveRefreshState} /> : undefined}>
        <div className="metric-grid">
          <Metric label="Ticker" value={ticker} />
          <Metric label="Recent Filings" value={filings.length.toLocaleString()} />
          <Metric label="Latest Filing" value={latestFilingDate ? formatDate(latestFilingDate) : "Pending"} />
          <Metric label="Last Checked" value={pageCompany?.last_checked ? formatDate(pageCompany.last_checked) : null} />
        </div>
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

