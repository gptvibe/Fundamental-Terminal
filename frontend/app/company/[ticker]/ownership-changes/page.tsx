"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { BeneficialOwnershipFormChart } from "@/components/charts/beneficial-ownership-form-chart";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { Panel } from "@/components/ui/panel";
import { StatusPill } from "@/components/ui/status-pill";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { getCompanyBeneficialOwnership, getCompanyBeneficialOwnershipSummary } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { CompanyBeneficialOwnershipResponse, CompanyBeneficialOwnershipSummaryResponse } from "@/lib/types";

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
  const formMix = useMemo(() => {
    const counts = new Map<string, number>();
    for (const filing of filings) {
      counts.set(filing.base_form, (counts.get(filing.base_form) ?? 0) + 1);
    }
    return [...counts.entries()].map(([form, count]) => `${form}: ${count.toLocaleString()}`).join(" · ");
  }, [filings]);

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
      <Panel title="Stake Changes" subtitle={pageCompany?.name ?? ticker} aside={effectiveRefreshState ? <StatusPill state={effectiveRefreshState} /> : undefined}>
        <div className="metric-grid">
          <Metric label="Ticker" value={ticker} />
          <Metric label="13D / 13G Filings" value={(summary?.total_filings ?? filings.length).toLocaleString()} />
          <Metric label="Initial Filings" value={(summary?.initial_filings ?? initialFilings).toLocaleString()} />
          <Metric label="Amendments" value={(summary?.amendments ?? amendments).toLocaleString()} />
          <Metric label="Reporting Persons" value={(summary?.unique_reporting_persons ?? 0).toLocaleString()} />
          <Metric
            label="Largest Reported Stake"
            value={summary?.max_reported_percent != null ? `${summary.max_reported_percent.toFixed(2)}%` : "Pending"}
          />
          <Metric
            label="Latest Event Date"
            value={summary?.latest_event_date ? formatDate(summary.latest_event_date) : "Pending"}
          />
        </div>
      </Panel>

      <Panel title="Form Mix" subtitle="How many initial stake disclosures versus amendments are visible in SEC submissions">
        <BeneficialOwnershipFormChart filings={filings} />
      </Panel>

      <Panel title="Filing Timeline" subtitle="Recent 13D and 13G activity with direct SEC document links">
        {error || data?.error ? (
          <div className="text-muted">{error ?? data?.error}</div>
        ) : loading || workspaceLoading ? (
          <div className="text-muted">Loading beneficial ownership activity...</div>
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
                    {filing.is_amendment ? <span className="pill">Amendment</span> : <span className="pill">Initial</span>}
                  </div>
                  <div className="text-muted">{formatDate(filing.filing_date ?? filing.report_date)}</div>
                </div>
                <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text)" }}>{filing.summary}</div>
                {filing.parties.length ? (
                  <div className="text-muted" style={{ fontSize: 13 }}>
                    {filing.parties.slice(0, 2).map((party) => {
                      const ownershipBits = [
                        party.percent_owned != null ? `${party.percent_owned.toFixed(2)}%` : null,
                        party.shares_owned != null ? `${Math.round(party.shares_owned).toLocaleString()} shares` : null
                      ].filter(Boolean);
                      return `${party.party_name}${ownershipBits.length ? ` (${ownershipBits.join(" · ")})` : ""}`;
                    }).join(" · ")}
                    {filing.parties.length > 2 ? ` · +${filing.parties.length - 2} more` : ""}
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