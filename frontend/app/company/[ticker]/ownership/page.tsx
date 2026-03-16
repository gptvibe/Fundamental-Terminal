"use client";

import { useMemo } from "react";
import { useParams } from "next/navigation";

import { InstitutionalOwnershipTrendChart } from "@/components/charts/institutional-ownership-trend-chart";
import { SmartMoneyFlowChart } from "@/components/charts/smart-money-flow-chart";
import { NewVsExitedPositions } from "@/components/institutional/new-vs-exited-positions";
import { ConvictionHeatmap } from "@/components/institutional/conviction-heatmap";
import { SmartMoneySummary } from "@/components/institutional/smart-money-summary";
import { TopHolderTrend } from "@/components/institutional/top-holder-trend";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { HedgeFundActivityTable } from "@/components/tables/hedge-fund-activity-table";
import { Panel } from "@/components/ui/panel";
import { StatusPill } from "@/components/ui/status-pill";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { formatDate } from "@/lib/format";

export default function CompanyOwnershipPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(params.ticker).toUpperCase();
  const {
    company,
    financials,
    institutionalData,
    institutionalHoldings,
    institutionalError,
    loading,
    refreshing,
    refreshState,
    consoleEntries,
    connectionState,
    queueRefresh
  } = useCompanyWorkspace(ticker, { includeInstitutional: true });
  const latestReportingDate = useMemo(
    () =>
      institutionalHoldings.reduce<string | null>(
        (latest, row) => (!latest || row.reporting_date > latest ? row.reporting_date : latest),
        null
      ),
    [institutionalHoldings]
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
          actionSubtitle="Refresh the latest ownership data or jump into valuation models."
          primaryActionLabel="Refresh Ownership Data"
          primaryActionDescription="Updates institutional holdings, filing history, and ownership summaries in the background."
          secondaryActionHref={`/company/${encodeURIComponent(ticker)}/models`}
          secondaryActionLabel="Open Valuation Models"
          secondaryActionDescription="View DCF, health score, scenario analysis, and model outputs."
          statusLines={[
            `Tracked holdings available: ${institutionalHoldings.length.toLocaleString()}`,
            `Latest filing quarter: ${latestReportingDate ? formatDate(latestReportingDate) : "Pending"}`,
            `Financial periods available: ${financials.length.toLocaleString()}`
          ]}
          consoleEntries={consoleEntries}
          connectionState={connectionState}
        />
      }
      mainClassName="company-page-grid"
    >
      <Panel title="Ownership" subtitle={company?.name ?? ticker} aside={refreshState ? <StatusPill state={refreshState} /> : undefined}>
        <div className="metric-grid">
          <Metric label="Ticker" value={ticker} />
          <Metric label="Tracked Holdings" value={institutionalHoldings.length.toLocaleString()} />
          <Metric label="Latest Quarter" value={latestReportingDate ? formatDate(latestReportingDate) : "Pending"} />
          <Metric label="Last Checked" value={company?.last_checked ? formatDate(company.last_checked) : null} />
        </div>
      </Panel>

      <Panel title="Smart Money Summary" subtitle="Quarter-over-quarter view of institutional positioning from 13F filings">
        <SmartMoneySummary
          holdings={institutionalHoldings}
          loading={loading && institutionalData === null}
          error={institutionalError}
          refresh={institutionalData?.refresh ?? refreshState}
        />
      </Panel>

      <Panel title="Institutional Ownership Trend" subtitle="Quarterly tracked shares, top 10 funds combined, and tracked ownership percentage">
        <InstitutionalOwnershipTrendChart holdings={institutionalHoldings} financials={financials} />
      </Panel>

      <Panel title="Top Holder Trend" subtitle="Latest top tracked funds and how their reported share counts moved across quarters">
        <TopHolderTrend holdings={institutionalHoldings} />
      </Panel>

      <Panel title="New vs Exited Positions" subtitle="How the latest quarter compares with the prior quarter across tracked 13F funds">
        <NewVsExitedPositions holdings={institutionalHoldings} />
      </Panel>

      <Panel title="Conviction Heatmap" subtitle="Latest tracked funds ranked by position weight and quarter-over-quarter position change">
        <ConvictionHeatmap holdings={institutionalHoldings} />
      </Panel>

      <Panel title="Smart Money Flow" subtitle="Quarterly buying, selling, and net institutional flow from 13F filings">
        <SmartMoneyFlowChart holdings={institutionalHoldings} loading={loading && institutionalData === null} error={institutionalError} refresh={institutionalData?.refresh ?? refreshState} />
      </Panel>

      <Panel title="Hedge Fund Activity" subtitle="Sortable holdings table with share changes, portfolio weights, and quarter labels">
        <HedgeFundActivityTable ticker={ticker} holdings={institutionalHoldings} loading={loading && institutionalData === null} error={institutionalError} refresh={institutionalData?.refresh ?? refreshState} />
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
