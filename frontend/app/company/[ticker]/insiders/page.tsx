"use client";

import { useMemo } from "react";
import { useParams } from "next/navigation";

import { InsiderActivityTrendChart } from "@/components/charts/insider-activity-trend-chart";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { InsiderActivitySummary } from "@/components/insiders/insider-activity-summary";
import { InsiderTransactionsTable } from "@/components/tables/insider-transactions-table";
import { Panel } from "@/components/ui/panel";
import { StatusPill } from "@/components/ui/status-pill";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { formatDate } from "@/lib/format";

export default function CompanyInsidersPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(params.ticker).toUpperCase();
  const {
    company,
    insiderData,
    insiderTrades,
    insiderError,
    loading,
    refreshing,
    refreshState,
    consoleEntries,
    connectionState,
    queueRefresh
  } = useCompanyWorkspace(ticker, { includeInsiders: true });
  const latestTradeDate = useMemo(
    () => insiderTrades.reduce<string | null>((latest, row) => (!row.date || (latest && row.date <= latest) ? latest : row.date), null),
    [insiderTrades]
  );

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
          actionSubtitle="Refresh the latest insider activity or jump into valuation models."
          primaryActionLabel="Refresh Insider Data"
          primaryActionDescription="Updates Form 4 filings, insider activity, and transaction summaries in the background."
          secondaryActionHref={`/company/${encodeURIComponent(ticker)}/models`}
          secondaryActionLabel="Open Valuation Models"
          secondaryActionDescription="View DCF, health score, scenario analysis, and model outputs."
          statusLines={[
            `Insider trades available: ${insiderTrades.length.toLocaleString()}`,
            `Latest filing date: ${latestTradeDate ? formatDate(latestTradeDate) : "Pending"}`,
            "Open-market activity only; updates appear here automatically in the background."
          ]}
          consoleEntries={consoleEntries}
          connectionState={connectionState}
        />
      }
      mainClassName="company-page-grid"
    >
      <Panel title="Insiders" subtitle={company?.name ?? ticker} aside={refreshState ? <StatusPill state={refreshState} /> : undefined}>
        <div className="metric-grid">
          <Metric label="Ticker" value={ticker} />
          <Metric label="Cached Trades" value={insiderTrades.length.toLocaleString()} />
          <Metric label="Latest Filing" value={latestTradeDate ? formatDate(latestTradeDate) : "Pending"} />
          <Metric label="Last Checked" value={company?.last_checked ? formatDate(company.last_checked) : null} />
        </div>
      </Panel>

      <Panel title="Insider Activity (Last 12 Months)" subtitle="Summary of Form 4 open-market buying and selling signals">
        <InsiderActivitySummary summary={insiderData?.summary ?? null} loading={loading && insiderData === null} error={insiderError} refresh={insiderData?.refresh ?? null} />
      </Panel>

      <Panel title="Insider Activity Trend" subtitle="Monthly insider buys, sells, and net activity from Form 4 filings">
        <InsiderActivityTrendChart trades={insiderTrades} />
      </Panel>

      <Panel title="Insider Transactions" subtitle="Sortable Form 4 activity with buy, sell, and 10b5-1 details">
        <InsiderTransactionsTable ticker={ticker} trades={insiderTrades} loading={loading && insiderData === null} error={insiderError} refresh={insiderData?.refresh ?? null} />
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
