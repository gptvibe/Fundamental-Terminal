"use client";

import { useParams } from "next/navigation";
import dynamic from "next/dynamic";

import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { Panel } from "@/components/ui/panel";
import { StatusPill } from "@/components/ui/status-pill";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { formatDate } from "@/lib/format";

const PeerComparisonDashboard = dynamic(
  () => import("@/components/peers/peer-comparison-dashboard").then((module) => module.PeerComparisonDashboard),
  { ssr: false, loading: () => <div className="text-muted">Loading peer comparison...</div> }
);

export default function CompanyPeersPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(params.ticker).toUpperCase();
  const {
    company,
    financials,
    loading,
    refreshing,
    refreshState,
    consoleEntries,
    connectionState,
    queueRefresh,
    reloadKey
  } = useCompanyWorkspace(ticker);

  return (
    <CompanyWorkspaceShell
      rail={
        <CompanyUtilityRail
          ticker={ticker}
          companyName={company?.name ?? null}
          sector={company?.sector ?? null}
          refreshState={refreshState}
          refreshing={refreshing}
          onRefresh={() => queueRefresh()}
          actionTitle="Next Steps"
          actionSubtitle="Refresh this company, then compare valuation and quality against close peers."
          primaryActionLabel="Refresh Peer Data"
          primaryActionDescription="Updates cached filings, prices, and model metrics used by peer comparison panels."
          secondaryActionHref={`/company/${encodeURIComponent(ticker)}/financials`}
          secondaryActionLabel="Open Financials"
          secondaryActionDescription="Review statement context behind peer valuation, margin, and quality differences."
          statusLines={[
            `Financial statements available: ${financials.length.toLocaleString()}`,
            `Selection model: focus company plus up to 4 peers`,
            company?.last_checked ? `Last checked: ${formatDate(company.last_checked)}` : "Last checked: pending"
          ]}
          consoleEntries={consoleEntries}
          connectionState={connectionState}
        />
      }
      mainClassName="company-page-grid"
    >
      <Panel title="Peer Workspace" subtitle={company?.name ?? ticker} aside={refreshState ? <StatusPill state={refreshState} /> : undefined}>
        {loading ? (
          <div className="text-muted">Loading company context...</div>
        ) : (
          <div className="metric-grid">
            <Metric label="Ticker" value={ticker} />
            <Metric label="Sector" value={company?.sector ?? null} />
            <Metric label="Peer Limit" value="4 selected peers" />
            <Metric label="Last Checked" value={company?.last_checked ? formatDate(company.last_checked) : null} />
          </div>
        )}
      </Panel>

      <PeerComparisonDashboard ticker={ticker} reloadKey={reloadKey} />
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