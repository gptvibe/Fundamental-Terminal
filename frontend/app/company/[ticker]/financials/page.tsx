"use client";

import { useMemo } from "react";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";

import { BankFinancialStatementsTable } from "@/components/company/bank-financial-statements-table";
import { BankRegulatoryOverview } from "@/components/company/bank-regulatory-overview";
import { FinancialPeriodToolbar } from "@/components/company/financial-period-toolbar";
import { CapitalStructureIntelligencePanel } from "@/components/company/capital-structure-intelligence-panel";
import { FinancialComparisonPanel } from "@/components/company/financial-comparison-panel";
import { PanelEmptyState } from "@/components/company/panel-empty-state";
import { CompanyResearchHeader } from "@/components/layout/company-research-header";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { CommercialFallbackNotice } from "@/components/ui/commercial-fallback-notice";
import { DataQualityDiagnostics } from "@/components/ui/data-quality-diagnostics";
import { Panel } from "@/components/ui/panel";
import { SourceFreshnessSummary } from "@/components/ui/source-freshness-summary";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { usePeriodSelection } from "@/hooks/use-period-selection";
import { resolveFilingChartCadence } from "@/lib/annual-financial-scope";
import type { SharedFinancialChartState } from "@/lib/financial-chart-state";
import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";

const BusinessSegmentBreakdown = dynamic(
  () => import("@/components/charts/business-segment-breakdown").then((module) => module.BusinessSegmentBreakdown),
  { ssr: false, loading: () => <div className="text-muted">Loading segment chart...</div> }
);
const CashFlowWaterfallChart = dynamic(
  () => import("@/components/charts/cash-flow-waterfall-chart").then((module) => module.CashFlowWaterfallChart),
  { ssr: false, loading: () => <div className="text-muted">Loading cash flow chart...</div> }
);
const GrowthWaterfallChart = dynamic(
  () => import("@/components/charts/growth-waterfall-chart").then((module) => module.GrowthWaterfallChart),
  { ssr: false, loading: () => <div className="text-muted">Loading growth chart...</div> }
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
const RatioHistoryTable = dynamic(
  () => import("@/components/company/ratio-history-table").then((module) => module.RatioHistoryTable),
  { ssr: false, loading: () => <div className="text-muted">Loading ratio history...</div> }
);
const ShareDilutionTrackerChart = dynamic(
  () => import("@/components/charts/share-dilution-tracker-chart").then((module) => module.ShareDilutionTrackerChart),
  { ssr: false, loading: () => <div className="text-muted">Loading dilution chart...</div> }
);
const FinancialStatementsTable = dynamic(
  () => import("@/components/company/financial-statements-table").then((module) => module.FinancialStatementsTable),
  { ssr: false, loading: () => <div className="text-muted">Loading financial statements...</div> }
);

function FinancialWorkflowSection({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <div className="financials-workflow-section">
      <div className="financials-workflow-eyebrow">{eyebrow}</div>
      <h2 className="financials-workflow-title">{title}</h2>
      <p className="financials-workflow-copy">{description}</p>
    </div>
  );
}

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
  const bankMode = Boolean(company?.regulated_entity && financials.some((statement) => statement.regulated_bank));
  const periodSelection = usePeriodSelection(financials);
  const pageFinancials = periodSelection.visibleFinancials;
  const activeFinancial = periodSelection.selectedFinancial ?? latestFinancial;
  const comparisonFinancial = periodSelection.comparisonFinancial;
  const sharedChartState = useMemo<SharedFinancialChartState>(
    () => ({
      cadence: periodSelection.cadence,
      effectiveCadence: resolveFilingChartCadence(periodSelection.cadence, periodSelection.effectiveStatementCadence),
      requestedCadence: periodSelection.cadence,
      visiblePeriodCount: pageFinancials.length,
      selectedFinancial: activeFinancial,
      comparisonFinancial,
      selectedPeriodLabel: periodSelection.selectedPeriodLabel,
      comparisonPeriodLabel: periodSelection.comparisonPeriodLabel,
      cadenceNote: periodSelection.cadenceNote,
    }),
    [
      activeFinancial,
      comparisonFinancial,
      periodSelection.cadenceNote,
      periodSelection.effectiveStatementCadence,
      pageFinancials.length,
      periodSelection.cadence,
      periodSelection.comparisonPeriodLabel,
      periodSelection.selectedPeriodLabel,
    ]
  );
  const activeRegulatedBank = activeFinancial?.regulated_bank ?? null;
  const useSegmentAnalysis = useMemo(() => {
    if (periodSelection.cadence !== "annual") {
      return false;
    }
    if (!periodSelection.selectedPeriodKey || !pageFinancials.length) {
      return true;
    }
    return periodSelection.selectedPeriodKey === periodSelection.periodOptions[0]?.key;
  }, [pageFinancials.length, periodSelection.cadence, periodSelection.periodOptions, periodSelection.selectedPeriodKey]);
  const headerDescription = bankMode
    ? "Official regulatory bank financials, deposit mix, credit costs, and capital ratios in one bank-specific review surface."
    : "Statement history, derived SEC metrics, and balance-sheet quality in one review surface fed by cached filings first.";
  const ribbonItems = bankMode
    ? [
        { label: "Financial Source", value: "FDIC / FR Y-9C + SEC", tone: "green" as const },
        { label: "Market Profile", value: "Yahoo Finance", tone: "cyan" as const },
        { label: "Financials Checked", value: company?.last_checked_financials ? formatDate(company.last_checked_financials) : "Pending", tone: "green" as const },
        { label: "Prices Checked", value: company?.last_checked_prices ? formatDate(company.last_checked_prices) : "Pending", tone: "cyan" as const },
      ]
    : [
        { label: "Financial Source", value: "SEC EDGAR/XBRL", tone: "green" as const },
        { label: "Market Profile", value: "Yahoo Finance", tone: "cyan" as const },
        { label: "Financials Checked", value: company?.last_checked_financials ? formatDate(company.last_checked_financials) : "Pending", tone: "green" as const },
        { label: "Prices Checked", value: company?.last_checked_prices ? formatDate(company.last_checked_prices) : "Pending", tone: "cyan" as const },
      ];
  const summaryItems = bankMode
    ? [
        { label: activeFinancial === latestFinancial ? "Latest NIM" : "Selected NIM", value: formatPercent(activeRegulatedBank?.net_interest_margin ?? null), accent: "cyan" as const },
        { label: "CET1", value: formatPercent(activeRegulatedBank?.common_equity_tier1_ratio ?? null), accent: "gold" as const },
        { label: "Deposits", value: formatCompactNumber(activeRegulatedBank?.deposits_total ?? null), accent: "green" as const },
        { label: "TCE", value: formatCompactNumber(activeRegulatedBank?.tangible_common_equity ?? null), accent: "cyan" as const },
      ]
    : [
        { label: activeFinancial === latestFinancial ? "Latest Revenue" : "Selected Revenue", value: formatCompactNumber(activeFinancial?.revenue), accent: "cyan" as const },
        { label: "Operating Income", value: formatCompactNumber(activeFinancial?.operating_income), accent: "gold" as const },
        { label: "Free Cash Flow", value: formatCompactNumber(activeFinancial?.free_cash_flow), accent: "green" as const },
        { label: "Price History", value: priceHistory.length.toLocaleString(), accent: "cyan" as const },
      ];

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
            `Statements visible: ${pageFinancials.length.toLocaleString()} of ${financials.length.toLocaleString()}`,
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
        description={headerDescription}
        freshness={{
          cacheState: company?.cache_state ?? null,
          refreshState,
          loading,
          hasData: Boolean(company || financials.length || priceHistory.length),
          lastChecked: company?.last_checked ?? null,
          errors: [error],
          detailLines: [
            `Statements visible: ${pageFinancials.length.toLocaleString()} of ${financials.length.toLocaleString()}`,
            `Annual filings available: ${annualStatements.length.toLocaleString()}`,
            `Price history points available: ${priceHistory.length.toLocaleString()}`,
          ],
        }}
        freshnessPlacement="subtitle"
        factsLoading={loading && !company && !financials.length && !priceHistory.length}
        summariesLoading={loading && !company && !financials.length && !priceHistory.length}
        facts={[
          { label: "Ticker", value: ticker },
          { label: "Statements", value: `${pageFinancials.length.toLocaleString()} visible` },
          { label: "Annual Filings", value: annualStatements.length.toLocaleString() },
          { label: "Last Checked", value: company?.last_checked ? formatDate(company.last_checked) : null }
        ]}
        ribbonItems={ribbonItems}
        summaries={summaryItems}
      >
        <CommercialFallbackNotice
          provenance={data?.provenance}
          sourceMix={data?.source_mix}
          subject="Price history and market profile data on this surface"
        />
      </CompanyResearchHeader>

      <Panel title="Data Quality Diagnostics" subtitle="Coverage, freshness, and missing-field flags for the cached financial workspace">
        <DataQualityDiagnostics diagnostics={data?.diagnostics} reconciliation={activeFinancial?.reconciliation ?? latestFinancial?.reconciliation} />
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

      <Panel title="Period & Comparison" subtitle="Shared cadence, range, and comparison controls for charts and tables on this page">
        <FinancialPeriodToolbar
          cadence={periodSelection.cadence}
          rangePreset={periodSelection.rangePreset}
          compareMode={periodSelection.compareMode}
          selectedPeriodKey={periodSelection.selectedPeriodKey}
          customComparePeriodKey={periodSelection.customComparePeriodKey}
          activeComparisonPeriodKey={periodSelection.activeComparisonPeriodKey}
          periodOptions={periodSelection.periodOptions}
          comparisonOptions={periodSelection.comparisonOptions}
          visiblePeriodCount={periodSelection.visiblePeriodCount}
          totalFinancialCount={periodSelection.totalFinancialCount}
          cadenceNote={periodSelection.cadenceNote}
          selectedPeriodLabel={periodSelection.selectedPeriodLabel}
          comparisonPeriodLabel={periodSelection.comparisonPeriodLabel}
          onCadenceChange={periodSelection.setCadence}
          onRangePresetChange={periodSelection.setRangePreset}
          onCompareModeChange={periodSelection.setCompareMode}
          onSelectedPeriodChange={periodSelection.setSelectedPeriodKey}
          onCustomComparePeriodChange={periodSelection.setCustomComparePeriodKey}
        />
      </Panel>

      {bankMode ? (
        <>
          <div className="financials-workflow-group">
            <FinancialWorkflowSection
              eyebrow="1. Selected Filing"
              title="Point-in-Time Composition"
              description="Start with the chosen call report or regulatory filing, then read composition, compare deltas, and short in-panel trend context from the same shared state."
            />

            <Panel title="Regulated Bank Snapshot" subtitle="Selected-period funding mix, credit costs, and capital buffers from official bank filings with compare deltas and short trend context.">
              <BankRegulatoryOverview
                latestFinancial={activeFinancial ?? latestFinancial}
                financials={pageFinancials}
                selectedFinancial={activeFinancial}
                comparisonFinancial={comparisonFinancial}
              />
            </Panel>
          </div>

          <div className="financials-workflow-group">
            <FinancialWorkflowSection
              eyebrow="2. Compare Periods"
              title="Period Comparison"
              description="Use the shared comparison state to inspect one regulatory period against another before moving into longer-run bank metric history."
            />

            <Panel title="Regulated Bank Statements" subtitle="Shared selected/comparison state across official bank statement history, deposit mix, capital ratios, and credit-cost detail.">
              {error ? (
                <div className="text-muted">{error}</div>
              ) : pageFinancials.length ? (
                <BankFinancialStatementsTable
                  financials={pageFinancials}
                  ticker={ticker}
                  showComparison={periodSelection.compareMode !== "off"}
                  selectedPeriodKey={periodSelection.selectedPeriodKey}
                  comparisonPeriodKey={periodSelection.activeComparisonPeriodKey}
                  selectedFinancial={activeFinancial}
                  comparisonFinancial={comparisonFinancial}
                />
              ) : (
                <PanelEmptyState loading={loading} loadingMessage="Loading regulated bank statements..." message="No regulated bank statements are available yet for this ticker." />
              )}
            </Panel>
          </div>

          <div className="financials-workflow-group">
            <FinancialWorkflowSection
              eyebrow="3. Follow History"
              title="Historical Trends"
              description="After selecting and comparing a bank period, use the trend surfaces to trace multi-quarter and TTM movement through the broader reporting history."
            />

            <Panel title="Derived Bank Metrics" subtitle="Historical bank trend view with shared cadence across official FDIC and Federal Reserve regulatory financials.">
              <DerivedMetricsPanel
                ticker={ticker}
                reloadKey={reloadKey}
                cadence={periodSelection.cadence}
                showCadenceSelector={false}
                maxPoints={periodSelection.metricsMaxPoints}
              />
            </Panel>
          </div>
        </>
      ) : (
        <>
          <div className="financials-workflow-group">
            <FinancialWorkflowSection
              eyebrow="1. Selected Filing"
              title="Point-in-Time Composition"
              description="Start with the chosen period. Composition surfaces stay anchored to that filing while exposing compare deltas and trend context only where the disclosure history is genuinely comparable."
            />

            <Panel title="Segment & Geography Breakdown" subtitle="Selected-period composition with year-selectable treemap views, compare deltas, and multi-year segment history when disclosures are comparable.">
              {pageFinancials.length ? (
                <BusinessSegmentBreakdown
                  financials={pageFinancials}
                  segmentAnalysis={useSegmentAnalysis ? data?.segment_analysis ?? null : null}
                  chartState={sharedChartState}
                  ticker={ticker}
                  reloadKey={reloadKey}
                />
              ) : (
                <PanelEmptyState loading={loading} loadingMessage="Loading segment data..." message="No business segment breakdowns are reported for this company." />
              )}
            </Panel>

            <Panel title="Cash Flow Waterfall" subtitle="Selected-period bridge from revenue to free cash flow with compare context and a trend strip across visible filings.">
              <CashFlowWaterfallChart financials={pageFinancials} chartState={sharedChartState} />
            </Panel>

            <Panel title="Capital Structure Intelligence" subtitle="Selected-period debt, payout, and dilution snapshot with compare deltas plus persisted multi-period trend history.">
              <CapitalStructureIntelligencePanel
                ticker={ticker}
                reloadKey={reloadKey}
                maxPeriods={periodSelection.capitalStructureMaxPeriods}
                selectedFinancial={activeFinancial}
                comparisonFinancial={comparisonFinancial}
              />
            </Panel>
          </div>

          <div className="financials-workflow-group">
            <FinancialWorkflowSection
              eyebrow="2. Chart-First Analysis"
              title="Growth & Quality Lens"
              description="Start with the annual growth view to frame revenue, earnings, and free cash flow momentum inside the shared range. Then move into quality and side-by-side comparison panels, with raw statement tables last."
            />

            <Panel title="Growth Waterfall" subtitle="Annual-only value bars with a YoY growth overlay for revenue, net income, and free cash flow across the shared range." aside={<span className="pill tone-gold">Annual only</span>}>
              <GrowthWaterfallChart financials={financials} visibleFinancials={pageFinancials} chartState={sharedChartState} />
            </Panel>

            <Panel title="Financial Quality" subtitle="Annual-only summary cards, expandable ratio trends, and multi-year ratio history aligned to the same shared range and comparison state." aside={<span className="pill tone-gold">Annual only</span>}>
              <div style={{ display: "grid", gap: 18 }}>
                <div style={{ display: "grid", gap: 12 }}>
                  <div style={{ display: "grid", gap: 4 }}>
                    <div className="financials-workflow-eyebrow">Summary + Trend</div>
                    <div className="company-data-table-note">Start with the selected-year quality snapshot, then expand trend mode for annual ratio sparklines inside the same shared fiscal-year context.</div>
                  </div>
                  <FinancialQualitySummary
                    financials={financials}
                    visibleFinancials={pageFinancials}
                    chartState={sharedChartState}
                  />
                </div>

                <div style={{ display: "grid", gap: 12, paddingTop: 16, borderTop: "1px solid color-mix(in srgb, var(--panel-border) 132%, transparent)" }}>
                  <div style={{ display: "grid", gap: 6 }}>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                      <div className="financials-workflow-eyebrow">Ratio History</div>
                      <span className="pill">Shared annual range</span>
                    </div>
                    <div className="company-data-table-note">Use the same annual window to inspect multi-year ratio history in a horizontally scrollable matrix, with year-over-year cell tones where improvement direction is meaningful.</div>
                  </div>
                  <RatioHistoryTable
                    financials={financials}
                    visibleFinancials={pageFinancials}
                    chartState={sharedChartState}
                    showContextChips={false}
                    showTableNote={false}
                    ticker={ticker}
                  />
                </div>
              </div>
            </Panel>

            <Panel title="Annual Financial Comparison" subtitle="Annual-only side-by-side comparison across core statements. Quarterly focus resolves to the matching fiscal year." aside={<span className="pill tone-gold">Annual only</span>}>
              <FinancialComparisonPanel
                financials={financials}
                visibleFinancials={pageFinancials}
                chartState={sharedChartState}
                ticker={ticker}
              />
            </Panel>

            <Panel title="Financial Statements" subtitle="Shared selected/comparison table across the visible statement history for direct period-by-period inspection.">
              {error ? (
                <div className="text-muted">{error}</div>
              ) : pageFinancials.length ? (
                <FinancialStatementsTable
                  financials={pageFinancials}
                  ticker={ticker}
                  showComparison={periodSelection.compareMode !== "off"}
                  selectedPeriodKey={periodSelection.selectedPeriodKey}
                  comparisonPeriodKey={periodSelection.activeComparisonPeriodKey}
                  selectedFinancial={activeFinancial}
                  comparisonFinancial={comparisonFinancial}
                />
              ) : (
                <PanelEmptyState loading={loading} loadingMessage="Loading financial statements..." message="No financial statements are available yet for this ticker." />
              )}
            </Panel>
          </div>

          <div className="financials-workflow-group">
            <FinancialWorkflowSection
              eyebrow="3. Follow History"
              title="Historical Trends"
              description="After using the primary growth lens, step back into the longer-run trend surfaces to see how margins, balance sheet, liquidity, cost structure, dilution, and derived metrics evolve over time."
            />

            <Panel title="Margin Trends" subtitle="Historical gross, operating, net, and free cash flow margins across the visible period range.">
              <MarginTrendChart financials={pageFinancials} chartState={sharedChartState} />
            </Panel>

            <Panel title="Derived SEC Metrics" subtitle="Historical quarterly, annual, and TTM quality metrics derived from cached canonical SEC financials and cached market profile.">
              <DerivedMetricsPanel
                ticker={ticker}
                reloadKey={reloadKey}
                cadence={periodSelection.cadence}
                showCadenceSelector={false}
                maxPoints={periodSelection.metricsMaxPoints}
              />
            </Panel>

            <Panel title="Balance Sheet" subtitle="Historical assets versus liabilities across the selected range.">
              {pageFinancials.length ? <BalanceSheetChart financials={pageFinancials} chartState={sharedChartState} /> : <PanelEmptyState loading={loading} loadingMessage="Loading balance-sheet history..." message="No balance-sheet history is available yet." />}
            </Panel>

            <Panel title="Liquidity & Capital" subtitle="Historical current assets, liabilities, and retained earnings from reported filings.">
              <LiquidityCapitalChart financials={pageFinancials} chartState={sharedChartState} />
            </Panel>

            <Panel title="Operating Cost Structure" subtitle="Historical SG&A, R&D, stock-based compensation, interest, and tax expense trends from reported filings.">
              <OperatingCostStructureChart financials={pageFinancials} chartState={sharedChartState} />
            </Panel>

            <Panel title="Share Dilution Tracker" subtitle="Historical shares outstanding and period-over-period dilution rates from reported filings.">
              {pageFinancials.length ? <ShareDilutionTrackerChart financials={pageFinancials} chartState={sharedChartState} /> : <PanelEmptyState loading={loading} loadingMessage="Loading share-count history..." message="No share-count history is available yet." />}
            </Panel>
          </div>
        </>
      )}
    </CompanyWorkspaceShell>
  );
}

