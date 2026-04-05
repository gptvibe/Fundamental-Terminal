"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { GovernanceFilingChart } from "@/components/charts/governance-filing-chart";
import { CompanyResearchHeader } from "@/components/layout/company-research-header";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { Panel } from "@/components/ui/panel";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { getCompanyExecutiveCompensation, getCompanyGovernance, getCompanyGovernanceSummary } from "@/lib/api";
import { formatCompactNumber, formatDate } from "@/lib/format";
import { RECHARTS_TOOLTIP_PROPS, CHART_GRID_COLOR, chartTick } from "@/lib/chart-theme";
import type {
  CompanyExecutiveCompensationResponse,
  CompanyGovernanceResponse,
  CompanyGovernanceSummaryResponse,
  ExecCompRowPayload,
} from "@/lib/types";

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
  const [execCompData, setExecCompData] = useState<CompanyExecutiveCompensationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        const [response, summary, execComp] = await Promise.all([
          getCompanyGovernance(ticker),
          getCompanyGovernanceSummary(ticker),
          getCompanyExecutiveCompensation(ticker),
        ]);
        if (!cancelled) {
          setData(response);
          setSummaryData(summary);
          setExecCompData(execComp);
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

  // Exec comp derived state
  const execRows = useMemo(() => execCompData?.rows ?? [], [execCompData]);
  const execFiscalYears = useMemo(() => execCompData?.fiscal_years ?? [], [execCompData]);

  // Pay trend data: for each fiscal year, pick the highest total_compensation in the dataset
  const payTrendData = useMemo(() => {
    if (!execRows.length) return [];
    const byYear = new Map<number, number>();
    for (const row of execRows) {
      if (row.fiscal_year == null || row.total_compensation == null) continue;
      const prev = byYear.get(row.fiscal_year) ?? 0;
      if (row.total_compensation > prev) byYear.set(row.fiscal_year, row.total_compensation);
    }
    return Array.from(byYear.entries())
      .sort(([a], [b]) => a - b)
      .map(([year, total]) => ({ year, total }));
  }, [execRows]);

  // Proxy filings sorted newest-first, used for derived panels
  const definitiveFilings = useMemo(
    () => filings.filter((f) => f.form === "DEF 14A"),
    [filings]
  );
  // Most recent filing with actual vote outcomes
  const latestWithVotes = useMemo(
    () => definitiveFilings.find((f) => f.vote_outcomes.length > 0) ?? null,
    [definitiveFilings]
  );

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
      <CompanyResearchHeader
        ticker={ticker}
        title="Governance"
        companyName={pageCompany?.name ?? ticker}
        sector={pageCompany?.sector}
        description="Proxy intelligence stays centered on SEC DEF 14A and DEFA14A filings, surfacing meeting metadata, vote outcomes, and executive compensation tables from cache before refresh jobs complete. Many 20-F and 40-F issuers may have limited U.S. proxy coverage here."
        freshness={{
          cacheState: pageCompany?.cache_state ?? null,
          refreshState: effectiveRefreshState,
          loading: loading || workspaceLoading,
          hasData: Boolean(pageCompany || summary || filings.length || execRows.length),
          lastChecked: pageCompany?.last_checked ?? null,
          errors: [error],
          detailLines: [
            `Proxy filings: ${(summary?.total_filings ?? filings.length).toLocaleString()}`,
            `Latest proxy: ${latestFilingDate ? formatDate(latestFilingDate) : "Pending"}`,
            `Exec comp rows: ${execRows.length.toLocaleString()}`,
          ],
        }}
        freshnessPlacement="subtitle"
        factsLoading={(loading || workspaceLoading) && !pageCompany && !summary && !filings.length && !execRows.length}
        summariesLoading={(loading || workspaceLoading) && !pageCompany && !summary && !filings.length && !execRows.length}
        facts={[
          { label: "Ticker", value: ticker },
          { label: "Proxy Filings", value: (summary?.total_filings ?? filings.length).toLocaleString() },
          { label: "Latest Proxy", value: latestFilingDate ? formatDate(latestFilingDate) : "Pending" },
          { label: "Latest Meeting", value: summary?.latest_meeting_date ? formatDate(summary.latest_meeting_date) : latestWithVotes?.meeting_date ? formatDate(latestWithVotes.meeting_date) : null }
        ]}
        ribbonItems={[
          { label: "Primary Source", value: "SEC DEF 14A / DEFA14A", tone: "green" },
          { label: "Meeting Dates Parsed", value: (summary?.filings_with_meeting_date ?? 0).toLocaleString(), tone: "cyan" },
          { label: "Comp Tables Parsed", value: (summary?.filings_with_exec_comp ?? 0).toLocaleString(), tone: "gold" },
          { label: "Refresh", value: effectiveRefreshState?.job_id ? "Queued" : "Background-first", tone: effectiveRefreshState?.job_id ? "cyan" : "green" }
        ]}
        summaries={[
          { label: "DEF 14A", value: (summary?.definitive_proxies ?? definitiveCount).toLocaleString(), accent: "cyan" },
          { label: "DEFA14A", value: (summary?.supplemental_proxies ?? additionalCount).toLocaleString(), accent: "gold" },
          { label: "Vote Items Parsed", value: (summary?.filings_with_vote_items ?? 0).toLocaleString(), accent: "green" },
          { label: "Peak Vote Count", value: (summary?.max_vote_item_count ?? 0).toLocaleString(), accent: "cyan" }
        ]}
      />

      <Panel title="Proxy Filing Mix" subtitle="How much of the visible governance record is definitive proxy versus supplemental material">
        <GovernanceFilingChart filings={filings} />
      </Panel>

      <Panel title="Board & Meeting History" subtitle="Meeting date, board nominees, and exec comp signal from each definitive proxy">
        {loading || workspaceLoading ? (
          <div className="text-muted">Loading board history...</div>
        ) : definitiveFilings.length ? (
          <div className="company-data-table-shell">
            <table className="company-data-table company-data-table-compact">
              <thead>
                <tr>
                  {(["Filed", "Meeting", "Nominees", "Vote Items", "Exec Comp"] as const).map((h) => (
                    <th key={h} className={h === "Nominees" || h === "Vote Items" ? "is-numeric" : undefined}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {definitiveFilings.map((f) => (
                  <tr key={f.accession_number ?? `${f.filing_date}-${f.source_url}`}>
                    <td>{formatDate(f.filing_date ?? f.report_date)}</td>
                    <td className={!f.meeting_date ? "is-muted" : undefined}>{f.meeting_date ? formatDate(f.meeting_date) : "—"}</td>
                    <td className="is-numeric">{f.board_nominee_count ?? "—"}</td>
                    <td className="is-numeric">{f.vote_item_count || "—"}</td>
                    <td>
                      <span className={f.executive_comp_table_detected ? "company-signal-positive" : "text-muted"}>
                        {f.executive_comp_table_detected ? "Yes" : "No"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-muted" style={{ padding: "16px 0" }}>No definitive proxy filings parsed yet. Many 20-F and 40-F issuers may not publish U.S. proxy materials in the SEC archive.</div>
        )}
      </Panel>

      {latestWithVotes ? (
        <Panel
          title="Vote Outcomes"
          subtitle={`Proposal-level ballot results — ${formatDate(latestWithVotes.filing_date ?? latestWithVotes.report_date)} DEF 14A`}
        >
          <div style={{ display: "grid", gap: 14 }}>
            {latestWithVotes.vote_outcomes.map((outcome) => {
              const total = (outcome.for_votes ?? 0) + (outcome.against_votes ?? 0) + (outcome.abstain_votes ?? 0);
              const forPct = total > 0 && outcome.for_votes != null ? (outcome.for_votes / total) * 100 : null;
              const againstPct = total > 0 && outcome.against_votes != null ? (outcome.against_votes / total) * 100 : null;
              return (
                <div key={outcome.proposal_number} style={{ display: "grid", gap: 6 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", fontSize: 13, fontWeight: 600, color: "var(--text)" }}>
                    <span>Prop {outcome.proposal_number}{outcome.title ? `: ${outcome.title}` : ""}</span>
                    {forPct != null && <span style={{ color: "var(--positive)", fontSize: 12 }}>{forPct.toFixed(1)}% For</span>}
                  </div>
                  {total > 0 ? (
                    <div style={{ height: 8, borderRadius: 4, background: "var(--border)", overflow: "hidden", display: "flex" }}>
                      {forPct != null && <div style={{ width: `${forPct}%`, background: "var(--positive)", height: "100%" }} />}
                      {againstPct != null && <div style={{ width: `${againstPct}%`, background: "var(--negative)", height: "100%" }} />}
                    </div>
                  ) : null}
                  <div style={{ display: "flex", gap: 16, fontSize: 12, color: "var(--text-muted)" }}>
                    {outcome.for_votes != null && <span style={{ color: "var(--positive)" }}>For {outcome.for_votes.toLocaleString()}</span>}
                    {outcome.against_votes != null && <span style={{ color: "var(--negative)" }}>Against {outcome.against_votes.toLocaleString()}</span>}
                    {outcome.abstain_votes != null && <span>Abstain {outcome.abstain_votes.toLocaleString()}</span>}
                    {outcome.broker_non_votes != null && <span>Broker Non-Votes {outcome.broker_non_votes.toLocaleString()}</span>}
                  </div>
                </div>
              );
            })}
          </div>
        </Panel>
      ) : null}

      {/* Executive Compensation Table */}
      <Panel
        title="Executive Compensation"
        subtitle={
          execFiscalYears.length
            ? `Named-executive pay — fiscal year${execFiscalYears.length > 1 ? "s" : ""} ${execFiscalYears.join(", ")}`
            : "Named-executive pay from Summary Compensation Table"
        }
      >
        {loading || workspaceLoading ? (
          <div className="text-muted">Loading executive compensation data...</div>
        ) : execRows.length ? (
          <div className="company-data-table-shell">
            <table className="company-data-table company-data-table-compact company-data-table-wide">
              <thead>
                <tr>
                  {(["Executive", "Title", "Year", "Salary", "Bonus", "Stock Awards", "Option Awards", "Non-Equity", "Other", "Total"] as const).map((h) => (
                    <th key={h} className={h === "Executive" || h === "Title" ? "is-wrap" : "is-numeric"}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {execRows.map((row, i) => (
                  <tr key={`${row.executive_name}-${row.fiscal_year ?? i}`}>
                    <td className="is-wrap company-data-cell-strong">{row.executive_name}</td>
                    <td className="is-wrap is-muted">{row.executive_title ?? "—"}</td>
                    <td className="is-numeric">{row.fiscal_year ?? "—"}</td>
                    <CompCell value={row.salary} />
                    <CompCell value={row.bonus} />
                    <CompCell value={row.stock_awards} />
                    <CompCell value={row.option_awards} />
                    <CompCell value={row.non_equity_incentive} />
                    <CompCell value={row.other_compensation} />
                    <CompCell value={row.total_compensation} highlight />
                  </tr>
                ))}
              </tbody>
            </table>
            {execCompData?.source === "live" && (
              <div className="company-data-table-note">
                Live-parsed from latest DEF 14A · not yet persisted
              </div>
            )}
          </div>
        ) : (
          <div className="grid-empty-state" style={{ minHeight: 140 }}>
            <div className="grid-empty-kicker">Compensation</div>
            <div className="grid-empty-title">No named-executive pay rows extracted yet</div>
            <div className="grid-empty-copy">Executive pay rows will appear here once a DEF 14A with a Summary Compensation Table has been parsed.</div>
          </div>
        )}
      </Panel>

      {/* Pay Trend Chart */}
      {payTrendData.length >= 2 && (
        <Panel
          title="Pay Trend"
          subtitle="Highest reported total compensation per fiscal year across all named executives"
        >
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={payTrendData} margin={{ top: 8, right: 16, left: 8, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_COLOR} vertical={false} />
              <XAxis dataKey="year" tick={chartTick()} axisLine={false} tickLine={false} />
              <YAxis
                tick={chartTick()}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v: number) => formatCompactNumber(v) ?? ""}
              />
              <Tooltip
                {...RECHARTS_TOOLTIP_PROPS}
                formatter={(value: number) => [`$${Math.round(value).toLocaleString()}`, "Peak Total"]}
              />
              <Bar dataKey="total" fill="var(--positive)" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Panel>
      )}

      <Panel title="Proxy Timeline" subtitle="Recent governance-related filings with direct SEC document links">        {error || data?.error ? (
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
            <div className="grid-empty-copy">This workflow activates when SEC submissions include proxy statements or related proxy materials for the selected company. Many 20-F and 40-F issuers may have limited U.S. proxy coverage here.</div>
          </div>
        )}
      </Panel>
    </CompanyWorkspaceShell>
  );
}

function CompCell({ value, highlight }: { value: number | null; highlight?: boolean }) {
  return (
    <td className={`is-numeric${highlight ? " company-data-cell-strong" : " is-muted"}`}>
      {value != null ? `$${Math.round(value).toLocaleString()}` : "—"}
    </td>
  );
}