"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { BeneficialOwnershipFormChart } from "@/components/charts/beneficial-ownership-form-chart";
import { CompanyResearchHeader } from "@/components/layout/company-research-header";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { Panel } from "@/components/ui/panel";
import { PlainEnglishScorecard } from "@/components/ui/plain-english-scorecard";
import { StatusPill } from "@/components/ui/status-pill";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { getCompanyBeneficialOwnership, getCompanyBeneficialOwnershipSummary } from "@/lib/api";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { formatDate } from "@/lib/format";
import type { CompanyBeneficialOwnershipResponse, CompanyBeneficialOwnershipSummaryResponse } from "@/lib/types";

interface OwnerRow {
  key: string;
  partyName: string;
  role: string | null;
  filingDate: string | null;
  eventDate: string | null;
  percentOwned: number | null;
  sharesOwned: number | null;
  percentChangePp: number | null;
  changeDirection: string | null;
  purpose: string | null;
}

interface ActivistSignal {
  key: string;
  form: string;
  filingDate: string | null;
  sourceUrl: string;
  label: string;
  changeDirection: string | null;
  headline: string;
  detail: string;
}

export default function CompanyOwnershipChangesPage() {
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
  const [data, setData] = useState<CompanyBeneficialOwnershipResponse | null>(null);
  const [summaryData, setSummaryData] = useState<CompanyBeneficialOwnershipSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        const [response, summary] = await Promise.all([
          getCompanyBeneficialOwnership(ticker),
          getCompanyBeneficialOwnershipSummary(ticker)
        ]);
        if (!cancelled) {
          setData(response);
          setSummaryData(summary);
        }
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError instanceof Error ? nextError.message : "Unable to load beneficial ownership filings");
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
  const amendments = filings.filter((filing) => filing.is_amendment).length;
  const initialFilings = filings.length - amendments;
  const increaseEvents = filings.filter((filing) => filing.change_direction === "increase").length;
  const decreaseEvents = filings.filter((filing) => filing.change_direction === "decrease").length;
  const formMix = useMemo(() => {
    const counts = new Map<string, number>();
    for (const filing of filings) {
      counts.set(filing.base_form, (counts.get(filing.base_form) ?? 0) + 1);
    }
    return [...counts.entries()].map(([form, count]) => `${form}: ${count.toLocaleString()}`).join(" · ");
  }, [filings]);
  const monthlyTimeline = useMemo(() => buildMonthlyTimeline(filings), [filings]);
  const directionBreakdown = useMemo(() => buildDirectionBreakdown(filings), [filings]);
  const ownerRows = useMemo(() => buildOwnerRows(filings), [filings]);
  const activistSignals = useMemo(() => buildActivistSignals(filings), [filings]);
  const latestPurpose = useMemo(() => {
    for (const filing of filings) {
      for (const party of filing.parties) {
        if (party.purpose?.trim()) {
          return party.purpose.trim();
        }
      }
    }
    return null;
  }, [filings]);
  const latestPartyEventDate = useMemo(() => {
    for (const filing of filings) {
      for (const party of filing.parties) {
        if (party.event_date) {
          return party.event_date;
        }
      }
    }
    return null;
  }, [filings]);
  const signalQuality = useMemo(() => {
    const totalAmendments = summary?.amendments ?? amendments;
    const quantified = summary?.amendments_with_delta ?? filings.filter((filing) => filing.percent_change_pp != null).length;
    const coverage = totalAmendments > 0 ? quantified / totalAmendments : 0;
    return {
      totalAmendments,
      quantified,
      coverage
    };
  }, [amendments, filings, summary?.amendments, summary?.amendments_with_delta]);
  const investorScorecard = useMemo(
    () =>
      buildInvestorScorecard({
        totalFilings: summary?.total_filings ?? filings.length,
        amendmentChains: summary?.chains_with_amendments ?? 0,
        increaseEvents: summary?.ownership_increase_events ?? increaseEvents,
        decreaseEvents: summary?.ownership_decrease_events ?? decreaseEvents,
        coverage: signalQuality.coverage
      }),
    [
      decreaseEvents,
      filings.length,
      increaseEvents,
      signalQuality.coverage,
      summary?.chains_with_amendments,
      summary?.ownership_decrease_events,
      summary?.ownership_increase_events,
      summary?.total_filings
    ]
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
          actionSubtitle="Refresh SEC ownership-change filings or move back into the broader ownership workspace."
          primaryActionLabel="Refresh Stake Changes"
          primaryActionDescription="Queues a company refresh so recent 13D and 13G activity is reloaded from SEC submissions."
          secondaryActionHref={`/company/${encodeURIComponent(ticker)}/ownership`}
          secondaryActionLabel="Open Ownership Dashboard"
          secondaryActionDescription="Compare 13F trends, top holders, and smart-money flow alongside stake-change filings."
          statusLines={[
            `Major stake filings: ${(summary?.total_filings ?? filings.length).toLocaleString()}`,
            `Latest filing date: ${summary?.latest_filing_date ? formatDate(summary.latest_filing_date) : latestFilingDate ? formatDate(latestFilingDate) : "Pending"}`,
            formMix || "Form mix pending"
          ]}
          consoleEntries={consoleEntries}
          connectionState={connectionState}
        />
      }
      mainClassName="company-page-grid"
    >
      <CompanyResearchHeader
        ticker={ticker}
        title="Stake Changes"
        companyName={pageCompany?.name ?? ticker}
        sector={pageCompany?.sector ?? null}
        cacheState={pageCompany?.cache_state ?? null}
        description="SEC-first stake-change workspace centered on Schedules 13D and 13G, amendment chains, and quantified ownership deltas."
        aside={effectiveRefreshState ? <StatusPill state={effectiveRefreshState} /> : undefined}
        facts={[
          { label: "Ticker", value: ticker },
          { label: "13D / 13G Filings", value: (summary?.total_filings ?? filings.length).toLocaleString() },
          { label: "Reporting Persons", value: (summary?.unique_reporting_persons ?? 0).toLocaleString() },
          { label: "Latest Event", value: summary?.latest_event_date ? formatDate(summary.latest_event_date) : "Pending" },
        ]}
        ribbonItems={[
          { label: "Latest Filing", value: summary?.latest_filing_date ? formatDate(summary.latest_filing_date) : latestFilingDate ? formatDate(latestFilingDate) : "Pending", tone: "cyan" },
          { label: "Signal Quality", value: `${(signalQuality.coverage * 100).toFixed(1)}% quantified deltas`, tone: "gold" },
          { label: "Sources", value: "SEC Schedules 13D + 13G", tone: "green" },
          { label: "Refresh", value: effectiveRefreshState?.job_id ? "Queued" : "Background-first", tone: effectiveRefreshState?.job_id ? "cyan" : "green" },
        ]}
        summaries={[
          { label: "Increase Events", value: (summary?.ownership_increase_events ?? increaseEvents).toLocaleString(), accent: "green" },
          { label: "Decrease Events", value: (summary?.ownership_decrease_events ?? decreaseEvents).toLocaleString(), accent: "red" },
          { label: "Largest Stake", value: summary?.max_reported_percent != null ? `${summary.max_reported_percent.toFixed(2)}%` : "?", accent: "cyan" },
          { label: "Amendment Chains", value: (summary?.chains_with_amendments ?? 0).toLocaleString(), accent: "gold" },
        ]}
      />

      <Panel title="Form Mix" subtitle="How many initial stake disclosures versus amendments are visible in SEC submissions">
        <BeneficialOwnershipFormChart filings={filings} />
      </Panel>

      <Panel title="Signal Visuals" subtitle="Quick trend views to spot ownership momentum without reading every filing">
        {error || data?.error ? (
          <div className="text-muted">{error ?? data?.error}</div>
        ) : loading || workspaceLoading ? (
          <div className="text-muted">Preparing stake-change visuals...</div>
        ) : filings.length ? (
          <div className="workspace-card-stack workspace-card-stack-lg">
            <PlainEnglishScorecard
              title="Simple Activity Scorecard"
              label={investorScorecard.label}
              tone={investorScorecard.tone}
              summary={investorScorecard.summary}
              explanation={investorScorecard.explanation}
              chips={[
                `${(summary?.total_filings ?? filings.length).toLocaleString()} filings`,
                `${(summary?.chains_with_amendments ?? 0).toLocaleString()} amendment chains`,
                `${signalQuality.quantified.toLocaleString()} quantified deltas`,
                latestPartyEventDate ? `latest event ${formatDate(latestPartyEventDate)}` : "latest event pending",
                latestPurpose ? `purpose: ${truncateText(latestPurpose, 70)}` : "purpose signal pending"
              ]}
            />

            <div className="workspace-two-column-panels">
              <div className="metric-card workspace-chart-card">
                <div className="metric-label">Monthly Filing Pace</div>
                <div className="text-muted workspace-card-copy">
                  More filings usually mean active stake updates or governance pressure.
                </div>
                <div className="workspace-chart-frame">
                  <ResponsiveContainer>
                    <BarChart data={monthlyTimeline} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                      <XAxis dataKey="month" stroke={CHART_AXIS_COLOR} tick={chartTick(11)} />
                      <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick(11)} allowDecimals={false} />
                      <Tooltip
                        {...RECHARTS_TOOLTIP_PROPS}
                        formatter={(value: number, name: string) => [value.toLocaleString(), name === "amendments" ? "Amendments" : "Initial filings"]}
                      />
                      <Bar dataKey="initials" name="Initial filings" stackId="filings" fill="var(--accent)" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="amendments" name="Amendments" stackId="filings" fill="#FFB020" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="metric-card workspace-chart-card">
                <div className="metric-label">Direction Breakdown</div>
                <div className="text-muted workspace-card-copy">
                  Shows if disclosed ownership is mostly increasing, decreasing, or unclear.
                </div>
                <div className="workspace-chart-frame">
                  <ResponsiveContainer>
                    <BarChart data={directionBreakdown} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                      <XAxis dataKey="label" stroke={CHART_AXIS_COLOR} tick={chartTick(11)} interval={0} />
                      <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick(11)} allowDecimals={false} />
                      <Tooltip {...RECHARTS_TOOLTIP_PROPS} formatter={(value: number) => value.toLocaleString()} />
                      <Bar dataKey="count" name="Filings" fill="#5EEA9D" radius={[6, 6, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>

            <div className="metric-card workspace-note-card">
              <div className="metric-label">How To Read This (Plain English)</div>
              <div className="text-muted workspace-note-line">Initial filing: A person or fund reports a meaningful stake for the first time.</div>
              <div className="text-muted workspace-note-line">Amendment: They update an earlier filing, often after changing position size or intent.</div>
              <div className="text-muted workspace-note-line">Increase or decrease event: We measured a clear percentage-point change versus the prior filing.</div>
              <div className="text-muted workspace-note-line">Unknown direction: SEC text did not provide enough structured numbers to quantify the change.</div>
              <div className="text-muted workspace-note-line">
                Signal quality here: {signalQuality.quantified.toLocaleString()} of {signalQuality.totalAmendments.toLocaleString()} amendments have quantified deltas ({(signalQuality.coverage * 100).toFixed(1)}%).
              </div>
              <div className="text-muted workspace-note-line">
                Practical tip: Treat this page as an early signal feed, then open the SEC filing link before making any investment decision.
              </div>
            </div>
          </div>
        ) : (
          <div className="grid-empty-state" style={{ minHeight: 220 }}>
            <div className="grid-empty-kicker">Signal visuals</div>
            <div className="grid-empty-title">No trend visuals yet</div>
            <div className="grid-empty-copy">Visuals appear after the first 13D or 13G filings are cached for this company.</div>
          </div>
        )}
      </Panel>

      <Panel title="Beneficial Owner Table" subtitle="Latest party-level signals, event dates, ownership stakes, and filing deltas">
        {error || data?.error ? (
          <div className="text-muted">{error ?? data?.error}</div>
        ) : loading || workspaceLoading ? (
          <div className="text-muted">Loading owner table...</div>
        ) : ownerRows.length ? (
          <div className="insider-table-shell">
            <table className="insider-table">
              <thead>
                <tr>
                  <th>Beneficial Owner</th>
                  <th>Latest Event</th>
                  <th>Latest Filing</th>
                  <th>Role</th>
                  <th className="align-right">Percent Owned</th>
                  <th className="align-right">Shares Owned</th>
                  <th className="align-right">Delta (pp)</th>
                  <th>Direction</th>
                  <th>Latest Purpose</th>
                </tr>
              </thead>
              <tbody>
                {ownerRows.map((row) => (
                  <tr key={row.key}>
                    <td className="insider-name-cell">{row.partyName}</td>
                    <td>{row.eventDate ? formatDate(row.eventDate) : "--"}</td>
                    <td>{row.filingDate ? formatDate(row.filingDate) : "--"}</td>
                    <td>{row.role ?? "--"}</td>
                    <td className="numeric-cell">{row.percentOwned != null ? `${row.percentOwned.toFixed(2)}%` : "--"}</td>
                    <td className="numeric-cell">{row.sharesOwned != null ? Math.round(row.sharesOwned).toLocaleString() : "--"}</td>
                    <td className="numeric-cell">{row.percentChangePp != null ? `${formatSignedNumber(row.percentChangePp)} pp` : "--"}</td>
                    <td>{row.changeDirection ? row.changeDirection.toUpperCase() : "--"}</td>
                    <td>{row.purpose ? truncateText(row.purpose, 96) : "--"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="grid-empty-state" style={{ minHeight: 220 }}>
            <div className="grid-empty-kicker">Owner table</div>
            <div className="grid-empty-title">No beneficial-owner rows yet</div>
            <div className="grid-empty-copy">Rows will appear after filings include party-level ownership details.</div>
          </div>
        )}
      </Panel>

      <Panel title="Activist Signals" subtitle="Purpose language and large ownership deltas that could matter for governance pressure">
        {error || data?.error ? (
          <div className="text-muted">{error ?? data?.error}</div>
        ) : loading || workspaceLoading ? (
          <div className="text-muted">Loading activist signal panel...</div>
        ) : activistSignals.length ? (
          <div className="workspace-card-stack">
            {activistSignals.map((signal) => (
              <a
                key={signal.key}
                href={signal.sourceUrl}
                target="_blank"
                rel="noreferrer"
                className="filing-link-card workspace-card-link"
              >
                <div className="workspace-card-row">
                  <div className="workspace-pill-row">
                    <span className="pill">{signal.form}</span>
                    <span className="pill">{signal.label}</span>
                    {signal.changeDirection ? <span className="pill">{signal.changeDirection}</span> : null}
                  </div>
                  <div className="text-muted">{signal.filingDate ? formatDate(signal.filingDate) : "Pending"}</div>
                </div>
                <div className="workspace-card-title">{signal.headline}</div>
                <div className="text-muted workspace-card-copy">{signal.detail}</div>
              </a>
            ))}
          </div>
        ) : (
          <div className="grid-empty-state" style={{ minHeight: 220 }}>
            <div className="grid-empty-kicker">Activist panel</div>
            <div className="grid-empty-title">No high-conviction signals yet</div>
            <div className="grid-empty-copy">This panel highlights clear purpose language and measurable stake moves when present in 13D/G filings.</div>
          </div>
        )}
      </Panel>

      <Panel title="Filing Timeline" subtitle="Recent 13D and 13G activity with direct SEC document links">
        {error || data?.error ? (
          <div className="text-muted">{error ?? data?.error}</div>
        ) : loading || workspaceLoading ? (
          <div className="text-muted">Loading beneficial ownership activity...</div>
        ) : filings.length ? (
          <div className="workspace-card-stack">
            {filings.map((filing) => (
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
                    {filing.is_amendment ? <span className="pill">Amendment</span> : <span className="pill">Initial</span>}
                    {filing.amendment_sequence != null && filing.amendment_chain_size != null ? (
                      <span className="pill">Chain {filing.amendment_sequence}/{filing.amendment_chain_size}</span>
                    ) : null}
                    {filing.change_direction && filing.change_direction !== "new" && filing.change_direction !== "unknown" ? (
                      <span className="pill">{filing.change_direction}</span>
                    ) : null}
                  </div>
                  <div className="text-muted">{formatDate(filing.filing_date ?? filing.report_date)}</div>
                </div>
                <div className="workspace-card-title">{filing.summary}</div>
                {filing.is_amendment ? (
                  <div className="text-muted workspace-card-copy">
                    {filing.percent_change_pp != null
                      ? `Ownership change: ${formatSignedNumber(filing.percent_change_pp)} pp${filing.previous_percent_owned != null ? ` from ${filing.previous_percent_owned.toFixed(2)}%` : ""}`
                      : "Ownership change: not quantifiable from this filing"}
                    {filing.previous_filing_date ? ` · Previous filing ${formatDate(filing.previous_filing_date)}` : ""}
                    {filing.previous_accession_number ? ` · Prior accession ${filing.previous_accession_number}` : ""}
                  </div>
                ) : null}
                {filing.parties.length ? (
                  <div className="text-muted workspace-card-copy">
                    {filing.parties
                      .slice(0, 2)
                      .map((party) => {
                        const ownershipBits = [
                          party.percent_owned != null ? `${party.percent_owned.toFixed(2)}%` : null,
                          party.shares_owned != null ? `${Math.round(party.shares_owned).toLocaleString()} shares` : null,
                          party.event_date ? `event ${formatDate(party.event_date)}` : null,
                          party.purpose ? `purpose: ${truncateText(party.purpose, 80)}` : null
                        ].filter(Boolean);
                        return `${party.party_name}${ownershipBits.length ? ` (${ownershipBits.join(" · ")})` : ""}`;
                      })
                      .join(" · ")}
                    {filing.parties.length > 2 ? ` · +${filing.parties.length - 2} more` : ""}
                  </div>
                ) : null}
                <div className="text-muted workspace-card-copy">
                  {filing.accession_number ?? "Accession pending"}
                  {filing.primary_document ? ` · ${filing.primary_document}` : ""}
                </div>
              </a>
            ))}
          </div>
        ) : (
          <div className="grid-empty-state" style={{ minHeight: 220 }}>
            <div className="grid-empty-kicker">Stake changes</div>
            <div className="grid-empty-title">No 13D or 13G activity yet</div>
            <div className="grid-empty-copy">This workflow activates when the SEC submissions feed includes beneficial ownership filings for the selected company.</div>
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

function formatSignedNumber(value: number): string {
  const rounded = Math.abs(value) >= 10 ? value.toFixed(1) : value.toFixed(2);
  return value > 0 ? `+${rounded}` : rounded;
}

function buildMonthlyTimeline(filings: CompanyBeneficialOwnershipResponse["filings"]) {
  const monthMap = new Map<string, { month: string; initials: number; amendments: number }>();

  for (const filing of filings) {
    const date = filing.filing_date ?? filing.report_date;
    if (!date) {
      continue;
    }
    const month = date.slice(0, 7);
    const row = monthMap.get(month) ?? { month, initials: 0, amendments: 0 };
    if (filing.is_amendment) {
      row.amendments += 1;
    } else {
      row.initials += 1;
    }
    monthMap.set(month, row);
  }

  return [...monthMap.values()].sort((left, right) => left.month.localeCompare(right.month)).slice(-18);
}

function buildDirectionBreakdown(filings: CompanyBeneficialOwnershipResponse["filings"]) {
  const counts = {
    increase: 0,
    decrease: 0,
    unchanged: 0,
    new: 0,
    unknown: 0
  };

  for (const filing of filings) {
    const direction = filing.change_direction ?? "unknown";
    if (direction in counts) {
      counts[direction as keyof typeof counts] += 1;
    }
  }

  return [
    { label: "Increase", count: counts.increase },
    { label: "Decrease", count: counts.decrease },
    { label: "Unchanged", count: counts.unchanged },
    { label: "New", count: counts.new },
    { label: "Unknown", count: counts.unknown }
  ];
}

function buildInvestorScorecard({
  totalFilings,
  amendmentChains,
  increaseEvents,
  decreaseEvents,
  coverage
}: {
  totalFilings: number;
  amendmentChains: number;
  increaseEvents: number;
  decreaseEvents: number;
  coverage: number;
}) {
  const directionalEvents = increaseEvents + decreaseEvents;
  const netBias = increaseEvents - decreaseEvents;

  if (totalFilings >= 40 || amendmentChains >= 8) {
    return {
      label: "High activity",
      tone: "high" as const,
      summary: "This company has a busy major-holder filing history.",
      explanation:
        netBias > 0
          ? "There are many stake updates, and the measurable ones lean more toward ownership increases than decreases."
          : netBias < 0
            ? "There are many stake updates, and the measurable ones lean more toward ownership decreases than increases."
            : "There are many stake updates, but the measurable ownership changes look mixed rather than one-sided."
    };
  }

  if (directionalEvents >= 3 || coverage >= 0.25) {
    return {
      label: "Medium activity",
      tone: "medium" as const,
      summary: "There is enough filing movement here to watch for changes in big-holder conviction.",
      explanation:
        coverage >= 0.25
          ? "A meaningful share of amendments can be quantified, so this page is useful for tracking whether major holders are adding or trimming."
          : "Some stake changes are visible, but not enough to call this a strong trend yet."
    };
  }

  return {
    label: "Low activity",
    tone: "low" as const,
    summary: "This filing history looks relatively quiet or hard to quantify.",
    explanation:
      "That does not mean nothing is happening. It means there are fewer major-holder updates, or the SEC text does not provide enough structured numbers to measure them cleanly."
  };
}

function buildOwnerRows(filings: CompanyBeneficialOwnershipResponse["filings"]): OwnerRow[] {
  const rowsByParty = new Map<string, OwnerRow>();

  for (const filing of filings) {
    for (const party of filing.parties) {
      const partyName = party.party_name?.trim();
      if (!partyName) {
        continue;
      }
      const key = partyName.toLowerCase();
      if (rowsByParty.has(key)) {
        continue;
      }
      rowsByParty.set(key, {
        key,
        partyName,
        role: party.role,
        filingDate: filing.filing_date ?? filing.report_date,
        eventDate: party.event_date,
        percentOwned: party.percent_owned,
        sharesOwned: party.shares_owned,
        percentChangePp: filing.percent_change_pp,
        changeDirection: filing.change_direction,
        purpose: party.purpose
      });
    }
  }

  return [...rowsByParty.values()].slice(0, 20);
}

function buildActivistSignals(filings: CompanyBeneficialOwnershipResponse["filings"]): ActivistSignal[] {
  const signals: ActivistSignal[] = [];
  const activistPattern = /activist|board|control|strateg|engage|proxy|nominee|sale|merger|capital/i;

  for (const filing of filings) {
    for (const party of filing.parties) {
      const hasPurposeSignal = Boolean(party.purpose && activistPattern.test(party.purpose));
      const delta = filing.percent_change_pp;
      const hasDeltaSignal = delta != null && Math.abs(delta) >= 1;
      if (!hasPurposeSignal && !hasDeltaSignal) {
        continue;
      }

      const headlineBits = [party.party_name];
      if (delta != null) {
        headlineBits.push(`${formatSignedNumber(delta)} pp`);
      }

      signals.push({
        key: `${filing.accession_number ?? filing.source_url}-${party.party_name}`,
        form: filing.form,
        filingDate: filing.filing_date ?? filing.report_date,
        sourceUrl: filing.source_url,
        label: hasPurposeSignal ? "Purpose Signal" : "Delta Signal",
        changeDirection: filing.change_direction,
        headline: headlineBits.join(" · "),
        detail: [
          party.event_date ? `Event date ${formatDate(party.event_date)}` : null,
          party.percent_owned != null ? `${party.percent_owned.toFixed(2)}% reported ownership` : null,
          party.purpose ? `Purpose: ${truncateText(party.purpose, 180)}` : null
        ]
          .filter(Boolean)
          .join(" · ")
      });
    }
  }

  return signals.slice(0, 10);
}

function truncateText(value: string, maxChars: number): string {
  if (value.length <= maxChars) {
    return value;
  }
  return `${value.slice(0, maxChars - 3).trimEnd()}...`;
}
