"use client";

import { useParams } from "next/navigation";

import { RiskRedFlagPanel } from "@/components/alerts/risk-red-flag-panel";
import { BusinessSegmentBreakdown } from "@/components/charts/business-segment-breakdown";
import { CashFlowWaterfallChart } from "@/components/charts/cash-flow-waterfall-chart";
import { LiquidityCapitalChart } from "@/components/charts/liquidity-capital-chart";
import { PriceFundamentalsModule } from "@/components/charts/price-fundamentals-module";
import { ShareDilutionTrackerChart } from "@/components/charts/share-dilution-tracker-chart";
import { FinancialHistorySection } from "@/components/company/financial-history-section";
import { PeerComparisonDashboard } from "@/components/peers/peer-comparison-dashboard";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { Panel } from "@/components/ui/panel";
import { StatusPill } from "@/components/ui/status-pill";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { formatCompactNumber, formatDate } from "@/lib/format";

export default function CompanyOverviewPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(params.ticker).toUpperCase();
  const {
    company,
    financials,
    priceHistory,
    fundamentalsTrendData,
    latestFinancial,
    refreshing,
    refreshState,
    consoleEntries,
    connectionState,
    queueRefresh,
    reloadKey
  } = useCompanyWorkspace(ticker, { includeChartConsole: true });

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
          actionSubtitle="Refresh the latest company data or jump into valuation models."
          primaryActionLabel="Refresh Company Data"
          primaryActionDescription="Updates filings, market prices, and summary panels in the background."
          secondaryActionHref={`/company/${encodeURIComponent(ticker)}/models`}
          secondaryActionLabel="Open Valuation Models"
          secondaryActionDescription="View DCF, health score, scenario analysis, and model outputs."
          statusLines={[
            `Price history points available: ${priceHistory.length.toLocaleString()}`,
            `Annual results available: ${fundamentalsTrendData.length.toLocaleString()}`,
            `${financials.filter((statement) => statement.segment_breakdown.length > 0).length.toLocaleString()} filings include segment detail`,
          ]}
          consoleEntries={consoleEntries}
          connectionState={connectionState}
        >
          <Panel title="Risk & Red Flags" subtitle="Ongoing watchlist of balance-sheet, cash-flow, dilution, and distress signals">
            <RiskRedFlagPanel ticker={ticker} financials={financials} reloadKey={reloadKey} />
          </Panel>
        </CompanyUtilityRail>
      }
      mainClassName="company-page-grid"
    >
      <Panel title="Company" subtitle={company?.name ?? ticker} aside={refreshState ? <StatusPill state={refreshState} /> : undefined} className="financial-hero">
        <div style={{ display: "grid", gap: 14 }}>
          <div className="metric-grid">
            <Metric label="Ticker" value={ticker} />
            <Metric label="CIK" value={company?.cik ?? null} />
            <Metric label="Sector" value={company?.sector ?? null} />
            <Metric label="Last Checked" value={company?.last_checked ? formatDate(company.last_checked) : null} />
          </div>
          <div className="financial-summary-strip">
            <SummaryCard label="Revenue" value={formatCompactNumber(latestFinancial?.revenue)} accent="cyan" />
            <SummaryCard label="EPS" value={latestFinancial?.eps == null ? "?" : latestFinancial.eps.toFixed(2)} accent="gold" />
            <SummaryCard label="Net Income" value={formatCompactNumber(latestFinancial?.net_income)} accent="green" />
            <SummaryCard label="Free Cash Flow" value={formatCompactNumber(latestFinancial?.free_cash_flow)} accent="green" />
          </div>
        </div>
      </Panel>

      <PriceFundamentalsModule priceData={priceHistory} fundamentalsData={fundamentalsTrendData} />

      <Panel title="Cash Flow Bridge" subtitle="How operating cash flow turns into free cash flow and capital allocation uses">
        <CashFlowWaterfallChart financials={financials} />
      </Panel>

      <Panel title="Liquidity & Capital" subtitle="Current assets, current liabilities, current ratio, and retained earnings trend">
        <LiquidityCapitalChart financials={financials} />
      </Panel>

      <Panel title="Share Dilution" subtitle="Shares outstanding history and year-over-year dilution rate from SEC filings">
        <ShareDilutionTrackerChart financials={financials} />
      </Panel>

      <Panel title="Business Segments" subtitle="Reported segment revenue mix and growth from cached SEC filing data">
        <BusinessSegmentBreakdown financials={financials} />
      </Panel>

      <Panel title="10-Year Financial History" subtitle="SEC EDGAR companyfacts (FY)">
        <FinancialHistorySection cik={company?.cik ?? null} />
      </Panel>

      <PeerComparisonDashboard ticker={ticker} reloadKey={reloadKey} />
    </CompanyWorkspaceShell>
  );
}

function Metric({ label, value }: { label: string; value: number | string | null }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{typeof value === "number" ? formatCompactNumber(value) : value ?? "?"}</div>
    </div>
  );
}

function SummaryCard({ label, value, accent }: { label: string; value: string; accent: "green" | "cyan" | "gold" }) {
  return (
    <div className={`summary-card accent-${accent}`}>
      <div className="summary-card-label">{label}</div>
      <div className="summary-card-value">{value}</div>
    </div>
  );
}
