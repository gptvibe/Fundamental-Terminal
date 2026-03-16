"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { GovernanceFilingChart } from "@/components/charts/governance-filing-chart";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { Panel } from "@/components/ui/panel";
import { StatusPill } from "@/components/ui/status-pill";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { getCompanyGovernance } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { CompanyGovernanceResponse } from "@/lib/types";

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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        const response = await getCompanyGovernance(ticker);
        if (!cancelled) {
          setData(response);
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
            `Proxy filings: ${filings.length.toLocaleString()}`,
            `Latest filing date: ${latestFilingDate ? formatDate(latestFilingDate) : "Pending"}`,
            `Definitive proxies: ${definitiveCount.toLocaleString()} · Additional materials: ${additionalCount.toLocaleString()}`
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
          <Metric label="Proxy Filings" value={filings.length.toLocaleString()} />
          <Metric label="DEF 14A" value={definitiveCount.toLocaleString()} />
          <Metric label="DEFA14A" value={additionalCount.toLocaleString()} />
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