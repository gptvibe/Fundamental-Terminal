"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { GovernanceFilingChart } from "@/components/charts/governance-filing-chart";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { Panel } from "@/components/ui/panel";
import { StatusPill } from "@/components/ui/status-pill";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { getCompanyGovernance, getCompanyGovernanceSummary } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { CompanyGovernanceResponse, CompanyGovernanceSummaryResponse } from "@/lib/types";

export default function CompanyGovernancePage() {
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
  const [data, setData] = useState<CompanyGovernanceResponse | null>(null);
  const [summaryData, setSummaryData] = useState<CompanyGovernanceSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        const [response, summary] = await Promise.all([
          getCompanyGovernance(ticker),
          getCompanyGovernanceSummary(ticker)
        ]);
        if (!cancelled) {
          setData(response);
          setSummaryData(summary);
        }
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError instanceof Error ? nextError.message : "Unable to load governance filings");
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

  const filings = useMemo(() => data?.filings ?? [], [data?.filings]);
  const summary = summaryData?.summary ?? null;
  const pageCompany = company ?? data?.company ?? null;
  const effectiveRefreshState = data?.refresh ?? refreshState;
  const latestFilingDate = filings[0]?.filing_date ?? filings[0]?.report_date ?? null;
  const definitiveCount = filings.filter((filing) => filing.form === "DEF 14A").length;
  const additionalCount = filings.length - definitiveCount;

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
          actionSubtitle="Refresh proxy filings or return to the main filing workspace for broader SEC coverage."
          primaryActionLabel="Refresh Governance Data"
          primaryActionDescription="Queues a company refresh so the latest proxy statements and related materials are reloaded."
          secondaryActionHref={`/company/${encodeURIComponent(ticker)}/filings`}
          secondaryActionLabel="Open Filings Workspace"
          secondaryActionDescription="View annual, quarterly, current reports, and filing parser snapshots in one place."
          statusLines={[
            `Proxy filings: ${(summary?.total_filings ?? filings.length).toLocaleString()}`,
            `Latest filing date: ${latestFilingDate ? formatDate(latestFilingDate) : "Pending"}`,
            `Definitive proxies: ${(summary?.definitive_proxies ?? definitiveCount).toLocaleString()} · Additional materials: ${(summary?.supplemental_proxies ?? additionalCount).toLocaleString()}`
          ]}
          consoleEntries={consoleEntries}
          connectionState={connectionState}
        />
      }
      mainClassName="company-page-grid"
    >
      <Panel title="Governance" subtitle={pageCompany?.name ?? ticker} aside={effectiveRefreshState ? <StatusPill state={effectiveRefreshState} /> : undefined}>
        <div className="metric-grid">
          <Metric label="Ticker" value={ticker} />
          <Metric label="Proxy Filings" value={(summary?.total_filings ?? filings.length).toLocaleString()} />
          <Metric label="DEF 14A" value={(summary?.definitive_proxies ?? definitiveCount).toLocaleString()} />
          <Metric label="DEFA14A" value={(summary?.supplemental_proxies ?? additionalCount).toLocaleString()} />
          <Metric label="Meeting Dates Parsed" value={(summary?.filings_with_meeting_date ?? 0).toLocaleString()} />
          <Metric label="Comp Tables Parsed" value={(summary?.filings_with_exec_comp ?? 0).toLocaleString()} />
          <Metric label="Vote Items Parsed" value={(summary?.filings_with_vote_items ?? 0).toLocaleString()} />
        </div>
      </Panel>

      <Panel title="Proxy Filing Mix" subtitle="How much of the visible governance record is definitive proxy versus supplemental material">
        <GovernanceFilingChart filings={filings} />
      </Panel>

      <Panel title="Proxy Timeline" subtitle="Recent governance-related filings with direct SEC document links">
        {error || data?.error ? (
          <div className="text-muted">{error ?? data?.error}</div>
        ) : loading || workspaceLoading ? (
          <div className="text-muted">Loading governance activity...</div>
        ) : filings.length ? (
          <div style={{ display: "grid", gap: 12 }}>
            {filings.map((filing) => (
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
                  </div>
                  <div className="text-muted">{formatDate(filing.filing_date ?? filing.report_date)}</div>
                </div>
                <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text)" }}>{filing.summary}</div>
                <div className="text-muted" style={{ fontSize: 13 }}>
                  {filing.meeting_date ? `Meeting: ${formatDate(filing.meeting_date)}` : "Meeting: pending"}
                  {` · Votes: ${filing.vote_item_count}`}
                  {` · Exec comp table: ${filing.executive_comp_table_detected ? "yes" : "no"}`}
                  {filing.board_nominee_count != null ? ` · Nominees: ${filing.board_nominee_count}` : ""}
                </div>
                {filing.key_amounts.length ? (
                  <div className="text-muted" style={{ fontSize: 13 }}>
                    Key amounts: {filing.key_amounts.slice(0, 3).map((amount) => `$${Math.round(amount).toLocaleString()}`).join(" · ")}
                  </div>
                ) : null}
                {filing.vote_outcomes.length ? (
                  <div className="text-muted" style={{ fontSize: 13 }}>
                    {filing.vote_outcomes.slice(0, 2).map((outcome) => {
                      const metrics = [
                        outcome.for_votes != null ? `For ${outcome.for_votes.toLocaleString()}` : null,
                        outcome.against_votes != null ? `Against ${outcome.against_votes.toLocaleString()}` : null,
                        outcome.abstain_votes != null ? `Abstain ${outcome.abstain_votes.toLocaleString()}` : null,
                        outcome.broker_non_votes != null ? `Broker Non-Votes ${outcome.broker_non_votes.toLocaleString()}` : null
                      ].filter(Boolean);
                      const title = outcome.title ? `: ${outcome.title}` : "";
                      return `Prop ${outcome.proposal_number}${title}${metrics.length ? ` (${metrics.join(" · ")})` : ""}`;
                    }).join(" || ")}
                    {filing.vote_outcomes.length > 2 ? ` || +${filing.vote_outcomes.length - 2} more` : ""}
                  </div>
                ) : null}
                <div className="text-muted" style={{ fontSize: 13 }}>
                  {filing.accession_number ?? "Accession pending"}
                  {filing.primary_document ? ` · ${filing.primary_document}` : ""}
                </div>
              </a>
            ))}
          </div>
        ) : (
          <div className="grid-empty-state" style={{ minHeight: 220 }}>
            <div className="grid-empty-kicker">Governance</div>
            <div className="grid-empty-title">No proxy filings yet</div>
            <div className="grid-empty-copy">This workflow activates when SEC submissions include proxy statements or related proxy materials for the selected company.</div>
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