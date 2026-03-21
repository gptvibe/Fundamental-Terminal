"use client";

import { useParams } from "next/navigation";

import { BalanceSheetChart } from "@/components/charts/balance-sheet-chart";
import { LiquidityCapitalChart } from "@/components/charts/liquidity-capital-chart";
import { BusinessSegmentBreakdown } from "@/components/charts/business-segment-breakdown";
import { CashFlowWaterfallChart } from "@/components/charts/cash-flow-waterfall-chart";
import { MarginTrendChart } from "@/components/charts/margin-trend-chart";
import { OperatingCostStructureChart } from "@/components/charts/operating-cost-structure-chart";
import { ShareDilutionTrackerChart } from "@/components/charts/share-dilution-tracker-chart";
import { FinancialStatementsTable } from "@/components/company/financial-statements-table";
import { FinancialQualitySummary } from "@/components/company/financial-quality-summary";
import { PanelEmptyState } from "@/components/company/panel-empty-state";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { Panel } from "@/components/ui/panel";
import { StatusPill } from "@/components/ui/status-pill";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { formatDate } from "@/lib/format";

export default function CompanyFinancialsTabPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(params.ticker).toUpperCase();
  const {
    company,
    financials,
    annualStatements,
    priceHistory,
    loading,
    error,
    refreshing,
    refreshState,
    consoleEntries,
    connectionState,
    queueRefresh
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
          actionSubtitle="Refresh the latest financial data or jump into valuation models."
          primaryActionLabel="Refresh Financial Data"
          primaryActionDescription="Updates filings, market prices, and statement views in the background."
          secondaryActionHref={`/company/${encodeURIComponent(ticker)}/models`}
          secondaryActionLabel="Open Valuation Models"
          secondaryActionDescription="View DCF, health score, scenario analysis, and model outputs."
          statusLines={[
            `Statements available: ${financials.length.toLocaleString()}`,
            `Annual filings available: ${annualStatements.length.toLocaleString()}`,
            `Price history points available: ${priceHistory.length.toLocaleString()}`
          ]}
          consoleEntries={consoleEntries}
          connectionState={connectionState}
        />
      }
      mainClassName="company-page-grid"
    >
      <Panel title="Financials" subtitle={company?.name ?? ticker} aside={refreshState ? <StatusPill state={refreshState} /> : undefined}>
        <div className="metric-grid">
          <Metric label="Ticker" value={ticker} />
          <Metric label="Statements" value={financials.length.toLocaleString()} />
          <Metric label="Annual Filings" value={annualStatements.length.toLocaleString()} />
          <Metric label="Last Checked" value={company?.last_checked ? formatDate(company.last_checked) : null} />
        </div>
      </Panel>

      <Panel title="Business Segment Breakdown" subtitle="Treemap, share, and growth from reported segment revenue">
        {financials.length ? (
          <BusinessSegmentBreakdown financials={financials} />
        ) : (
          <PanelEmptyState message={loading ? "Loading segment data..." : "No business segment breakdowns are reported for this company."} />
        )}
      </Panel>

      <Panel title="Cash Flow Waterfall" subtitle="Bridge from revenue to free cash flow and capital allocation over time">
        <CashFlowWaterfallChart financials={financials} />
      </Panel>

      <Panel title="Margin Trends" subtitle="Gross, operating, net, and free cash flow margins over time">
        <MarginTrendChart financials={financials} />
      </Panel>

      <Panel title="Balance Sheet" subtitle="Assets versus liabilities over time">
        {financials.length ? <BalanceSheetChart financials={financials} /> : <PanelEmptyState message={loading ? "Loading balance-sheet history..." : "No balance-sheet history is available yet."} />}
      </Panel>

      <Panel title="Liquidity & Capital" subtitle="Current assets, liabilities, and retained earnings from reported filings">
        <LiquidityCapitalChart financials={financials} />
      </Panel>

      <Panel title="Operating Cost Structure" subtitle="SG&A, R&D, stock-based compensation, interest, and tax expense trends from reported filings">
        <OperatingCostStructureChart financials={financials} />
      </Panel>

      <Panel title="Financial Quality Summary" subtitle="Quick view of margins, balance-sheet leverage, profitability, and growth quality from annual filings">
        <FinancialQualitySummary financials={financials} />
      </Panel>

      <Panel title="Share Dilution Tracker" subtitle="Shares outstanding trend with period-over-period dilution rates from reported filings">
        {financials.length ? <ShareDilutionTrackerChart financials={financials} /> : <PanelEmptyState message={loading ? "Loading share-count history..." : "No share-count history is available yet."} />}
      </Panel>

      <Panel title="Financial Statements" subtitle="Full company statement history in one table">
        {error ? (
          <div className="text-muted">{error}</div>
        ) : financials.length ? (
          <FinancialStatementsTable financials={financials} ticker={ticker} />
        ) : (
          <PanelEmptyState message={loading ? "Loading financial statements..." : "No financial statements are available yet for this ticker."} />
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

