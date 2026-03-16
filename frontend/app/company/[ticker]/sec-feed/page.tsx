"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { Panel } from "@/components/ui/panel";
import { StatusPill } from "@/components/ui/status-pill";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { getCompanyBeneficialOwnership, getCompanyEvents, getCompanyGovernance } from "@/lib/api";
import { formatCompactNumber, formatDate } from "@/lib/format";
import type { CompanyBeneficialOwnershipResponse, CompanyEventsResponse, CompanyGovernanceResponse } from "@/lib/types";

type FeedEntry = {
  id: string;
  date: string | null;
  type: string;
  badge: string;
  title: string;
  detail: string;
  href?: string;
};

export default function CompanySecFeedPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(params.ticker).toUpperCase();
  const {
    company,
    insiderTrades,
    institutionalHoldings,
    loading: workspaceLoading,
    refreshing,
    refreshState,
    consoleEntries,
    connectionState,
    queueRefresh,
    reloadKey
  } = useCompanyWorkspace(ticker, { includeInsiders: true, includeInstitutional: true });
  const [eventsData, setEventsData] = useState<CompanyEventsResponse | null>(null);
  const [governanceData, setGovernanceData] = useState<CompanyGovernanceResponse | null>(null);
  const [ownershipData, setOwnershipData] = useState<CompanyBeneficialOwnershipResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        const [events, governance, ownership] = await Promise.all([
          getCompanyEvents(ticker),
          getCompanyGovernance(ticker),
          getCompanyBeneficialOwnership(ticker),
        ]);
        if (!cancelled) {
          setEventsData(events);
          setGovernanceData(governance);
          setOwnershipData(ownership);
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

  const feed = useMemo<FeedEntry[]>(() => {
    const entries: FeedEntry[] = [];

    for (const event of eventsData?.events ?? []) {
      entries.push({
        id: `event-${event.accession_number ?? event.source_url}`,
        date: event.filing_date ?? event.report_date,
        type: "event",
        badge: event.category,
        title: event.summary,
        detail: `${event.form}${event.items ? ` · Items ${event.items}` : ""}`,
        href: event.source_url,
      });
    }

    for (const filing of governanceData?.filings ?? []) {
      entries.push({
        id: `gov-${filing.accession_number ?? filing.source_url}`,
        date: filing.filing_date ?? filing.report_date,
        type: "governance",
        badge: filing.form,
        title: filing.summary,
        detail: filing.accession_number ?? "Proxy filing",
        href: filing.source_url,
      });
    }

    for (const filing of ownershipData?.filings ?? []) {
      entries.push({
        id: `owner-${filing.accession_number ?? filing.source_url}`,
        date: filing.filing_date ?? filing.report_date,
        type: "ownership-change",
        badge: filing.form,
        title: filing.summary,
        detail: filing.is_amendment ? "Amendment" : "Initial stake disclosure",
        href: filing.source_url,
      });
    }

    for (const trade of insiderTrades.slice(0, 40)) {
      entries.push({
        id: `insider-${trade.accession_number ?? `${trade.name}-${trade.date}`}`,
        date: trade.filing_date ?? trade.date,
        type: "insider",
        badge: trade.action,
        title: `${trade.name} ${trade.action.toLowerCase()} activity`,
        detail: `${trade.role ?? "Insider"}${trade.value !== null ? ` · ${formatCompactNumber(trade.value)}` : ""}`,
        href: trade.source ?? undefined,
      });
    }

    for (const holding of institutionalHoldings.slice(0, 40)) {
      entries.push({
        id: `inst-${holding.accession_number ?? `${holding.fund_name}-${holding.reporting_date}`}`,
        date: holding.filing_date ?? holding.reporting_date,
        type: "institutional",
        badge: "13F",
        title: `${holding.fund_name} reported updated holdings`,
        detail: `${holding.shares_held !== null ? `${formatCompactNumber(holding.shares_held)} shares` : "Tracked position"}${holding.percent_change !== null ? ` · ${holding.percent_change.toFixed(2)}% change` : ""}`,
        href: holding.source ?? undefined,
      });
    }

    return entries.sort((left, right) => Date.parse(right.date ?? "1970-01-01") - Date.parse(left.date ?? "1970-01-01"));
  }, [eventsData?.events, governanceData?.filings, insiderTrades, institutionalHoldings, ownershipData?.filings]);

  const effectiveRefreshState = eventsData?.refresh ?? governanceData?.refresh ?? ownershipData?.refresh ?? refreshState;
  const latestDate = feed[0]?.date ?? null;

  return (
    <CompanyWorkspaceShell
      rail={
        <CompanyUtilityRail
          ticker={ticker}
          companyName={company?.name ?? eventsData?.company?.name ?? governanceData?.company?.name ?? ownershipData?.company?.name ?? null}
          sector={company?.sector ?? eventsData?.company?.sector ?? governanceData?.company?.sector ?? ownershipData?.company?.sector ?? null}
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
            `Insider trades loaded: ${insiderTrades.length.toLocaleString()} · 13F rows loaded: ${institutionalHoldings.length.toLocaleString()}`
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
          <Metric label="Last Checked" value={company?.last_checked ? formatDate(company.last_checked) : null} />
        </div>
      </Panel>

      <Panel title="Chronological SEC Stream" subtitle="Events, proxy filings, stake disclosures, insider trades, and 13F updates in one timeline">
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
                      <span className="pill">{entry.type}</span>
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