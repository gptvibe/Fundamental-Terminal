"use client";

import { useParams } from "next/navigation";
import dynamic from "next/dynamic";

import { CapitalStructureIntelligencePanel } from "@/components/company/capital-structure-intelligence-panel";
import { PanelEmptyState } from "@/components/company/panel-empty-state";
import { CompanyResearchHeader } from "@/components/layout/company-research-header";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { CommercialFallbackNotice } from "@/components/ui/commercial-fallback-notice";
import { DataQualityDiagnostics } from "@/components/ui/data-quality-diagnostics";
import { Panel } from "@/components/ui/panel";
import { SourceFreshnessSummary } from "@/components/ui/source-freshness-summary";
import { StatusPill } from "@/components/ui/status-pill";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { formatCompactNumber, formatDate } from "@/lib/format";

const BusinessSegmentBreakdown = dynamic(
  () => import("@/components/charts/business-segment-breakdown").then((module) => module.BusinessSegmentBreakdown),
  { ssr: false, loading: () => <div className="text-muted">Loading segment chart...</div> }
);
const CashFlowWaterfallChart = dynamic(
  () => import("@/components/charts/cash-flow-waterfall-chart").then((module) => module.CashFlowWaterfallChart),
  { ssr: false, loading: () => <div className="text-muted">Loading cash flow chart...</div> }
);
const MarginTrendChart = dynamic(
  () => import("@/components/charts/margin-trend-chart").then((module) => module.MarginTrendChart),
  { ssr: false, loading: () => <div className="text-muted">Loading margin trend...</div> }
);
const DerivedMetricsPanel = dynamic(
  () => import("@/components/charts/derived-metrics-panel").then((module) => module.DerivedMetricsPanel),
  { ssr: false, loading: () => <div className="text-muted">Loading derived metrics...</div> }
);
const BalanceSheetChart = dynamic(
  () => import("@/components/charts/balance-sheet-chart").then((module) => module.BalanceSheetChart),
  { ssr: false, loading: () => <div className="text-muted">Loading balance-sheet chart...</div> }
);
const LiquidityCapitalChart = dynamic(
  () => import("@/components/charts/liquidity-capital-chart").then((module) => module.LiquidityCapitalChart),
  { ssr: false, loading: () => <div className="text-muted">Loading liquidity chart...</div> }
);
const OperatingCostStructureChart = dynamic(
  () => import("@/components/charts/operating-cost-structure-chart").then((module) => module.OperatingCostStructureChart),
  { ssr: false, loading: () => <div className="text-muted">Loading cost structure chart...</div> }
);
const FinancialQualitySummary = dynamic(
  () => import("@/components/company/financial-quality-summary").then((module) => module.FinancialQualitySummary),
  { ssr: false, loading: () => <div className="text-muted">Loading quality summary...</div> }
);
const ShareDilutionTrackerChart = dynamic(
  () => import("@/components/charts/share-dilution-tracker-chart").then((module) => module.ShareDilutionTrackerChart),
  { ssr: false, loading: () => <div className="text-muted">Loading dilution chart...</div> }
);
const FinancialStatementsTable = dynamic(
  () => import("@/components/company/financial-statements-table").then((module) => module.FinancialStatementsTable),
  { ssr: false, loading: () => <div className="text-muted">Loading financial statements...</div> }
);

export default function CompanyFinancialsTabPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(params.ticker).toUpperCase();
  const {
    data,
    company,
    financials,
    annualStatements,
    priceHistory,
    latestFinancial,
    loading,
    error,
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
      <CompanyResearchHeader
        ticker={ticker}
        title="Financials"
        companyName={company?.name ?? ticker}
        sector={company?.sector}
        cacheState={company?.cache_state ?? null}
        description="Statement history, derived SEC metrics, and balance-sheet quality in one review surface fed by cached filings first."
        aside={refreshState ? <StatusPill state={refreshState} /> : undefined}
        facts={[
          { label: "Ticker", value: ticker },
          { label: "Statements", value: financials.length.toLocaleString() },
          { label: "Annual Filings", value: annualStatements.length.toLocaleString() },
          { label: "Last Checked", value: company?.last_checked ? formatDate(company.last_checked) : null }
        ]}
        ribbonItems={[
          { label: "Financial Source", value: "SEC EDGAR/XBRL", tone: "green" },
          { label: "Market Profile", value: "Yahoo Finance", tone: "cyan" },
          { label: "Financials Checked", value: company?.last_checked_financials ? formatDate(company.last_checked_financials) : "Pending", tone: "green" },
          { label: "Prices Checked", value: company?.last_checked_prices ? formatDate(company.last_checked_prices) : "Pending", tone: "cyan" }
        ]}
        summaries={[
          { label: "Latest Revenue", value: formatCompactNumber(latestFinancial?.revenue), accent: "cyan" },
          { label: "Operating Income", value: formatCompactNumber(latestFinancial?.operating_income), accent: "gold" },
          { label: "Free Cash Flow", value: formatCompactNumber(latestFinancial?.free_cash_flow), accent: "green" },
          { label: "Price History", value: priceHistory.length.toLocaleString(), accent: "cyan" }
        ]}
      >
        <CommercialFallbackNotice
          provenance={data?.provenance}
          sourceMix={data?.source_mix}
          subject="Price history and market profile data on this surface"
        />
      </CompanyResearchHeader>

      <Panel title="Data Quality Diagnostics" subtitle="Coverage, freshness, and missing-field flags for the cached financial workspace">
        <DataQualityDiagnostics diagnostics={data?.diagnostics} reconciliation={latestFinancial?.reconciliation} />
      </Panel>

      <Panel title="Source & Freshness" subtitle="Centralized registry metadata for filing inputs, price overlays, and disclosure notes">
        <SourceFreshnessSummary
          provenance={data?.provenance}
          asOf={data?.as_of}
          lastRefreshedAt={data?.last_refreshed_at}
          sourceMix={data?.source_mix}
          confidenceFlags={data?.confidence_flags}
        />
      </Panel>

      <Panel title="Segment & Geography Breakdown" subtitle="Mix shifts, concentration, margin contribution, and chart views from reported segment disclosures">
        {financials.length ? (
          <BusinessSegmentBreakdown financials={financials} segmentAnalysis={data?.segment_analysis ?? null} />
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

      <Panel title="Derived SEC Metrics" subtitle="Quarterly, annual, and TTM quality metrics derived from cached canonical SEC financials and cached market profile">
        <DerivedMetricsPanel ticker={ticker} reloadKey={reloadKey} />
      </Panel>

      <Panel title="Capital Structure Intelligence" subtitle="Debt ladders, lease schedules, issuance and repayment flow, payout mix, SBC, and dilution bridges derived from persisted SEC extraction">
        <CapitalStructureIntelligencePanel ticker={ticker} reloadKey={reloadKey} />
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

