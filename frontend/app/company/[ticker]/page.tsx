"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";

import { RiskRedFlagPanel } from "@/components/alerts/risk-red-flag-panel";
import { CompanyMetricGrid, CompanyResearchHeader } from "@/components/layout/company-research-header";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { CommercialFallbackNotice } from "@/components/ui/commercial-fallback-notice";
import { Panel } from "@/components/ui/panel";
import { SourceFreshnessSummary } from "@/components/ui/source-freshness-summary";
import { StatusPill } from "@/components/ui/status-pill";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { getCompanyActivityOverview } from "@/lib/api";
import { formatCompactNumber, formatDate } from "@/lib/format";
import type { CompanyActivityOverviewResponse } from "@/lib/types";

const PriceFundamentalsModule = dynamic(
  () => import("@/components/charts/price-fundamentals-module").then((module) => module.PriceFundamentalsModule),
  { ssr: false }
);
const CashFlowWaterfallChart = dynamic(
  () => import("@/components/charts/cash-flow-waterfall-chart").then((module) => module.CashFlowWaterfallChart),
  { ssr: false }
);
const LiquidityCapitalChart = dynamic(
  () => import("@/components/charts/liquidity-capital-chart").then((module) => module.LiquidityCapitalChart),
  { ssr: false }
);
const ShareDilutionTrackerChart = dynamic(
  () => import("@/components/charts/share-dilution-tracker-chart").then((module) => module.ShareDilutionTrackerChart),
  { ssr: false }
);
const BusinessSegmentBreakdown = dynamic(
  () => import("@/components/charts/business-segment-breakdown").then((module) => module.BusinessSegmentBreakdown),
  { ssr: false }
);
const FinancialHistorySection = dynamic(
  () => import("@/components/company/financial-history-section").then((module) => module.FinancialHistorySection),
  { ssr: false }
);
const ChangesSinceLastFilingCard = dynamic(
  () => import("@/components/company/changes-since-last-filing-card").then((module) => module.ChangesSinceLastFilingCard),
  { ssr: false, loading: () => <div className="text-muted">Loading filing comparison...</div> }
);
const MetricsExplorerPanel = dynamic(
  () => import("@/components/company/metrics-explorer-panel").then((module) => module.MetricsExplorerPanel),
  { ssr: false }
);
const PeerComparisonDashboard = dynamic(
  () => import("@/components/peers/peer-comparison-dashboard").then((module) => module.PeerComparisonDashboard),
  { ssr: false }
);
const CompanyVisualizationLab = dynamic(
  () => import("@/components/charts/company-visualization-lab").then((module) => module.CompanyVisualizationLab),
  { ssr: false }
);

export default function CompanyOverviewPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(params.ticker).toUpperCase();
  const {
    data,
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
  const [activityData, setActivityData] = useState<CompanyActivityOverviewResponse | null>(null);
  const [activityLoading, setActivityLoading] = useState(true);
  const [activityError, setActivityError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadActivity() {
      try {
        setActivityLoading(true);
        setActivityError(null);
        const overview = await getCompanyActivityOverview(ticker);
        if (!cancelled) {
          setActivityData(overview);
        }
      } catch (nextError) {
        if (!cancelled) {
          setActivityError(nextError instanceof Error ? nextError.message : "Unable to load activity feed");
        }
      } finally {
        if (!cancelled) {
          setActivityLoading(false);
        }
      }
    }

    void loadActivity();
    return () => {
      cancelled = true;
    };
  }, [ticker, reloadKey]);

  const topAlerts = useMemo(() => (activityData?.alerts ?? []).slice(0, 3), [activityData?.alerts]);
  const latestEntries = useMemo(() => (activityData?.entries ?? []).slice(0, 4), [activityData?.entries]);

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
            `Market context: ${formatMarketContextStatus(activityData?.market_context_status)}`,
          ]}
          consoleEntries={consoleEntries}
          connectionState={connectionState}
        >
          <Panel title="Risk & Red Flags" subtitle="Ongoing watchlist of balance-sheet, cash-flow, dilution, and distress signals" variant="subtle">
            <RiskRedFlagPanel financials={financials} />
          </Panel>
        </CompanyUtilityRail>
      }
      mainClassName="company-page-grid"
    >
      <CompanyResearchHeader
        ticker={ticker}
        title={company?.name ?? ticker}
        companyName={`${ticker}${company?.sector ? ` · ${company.sector}` : " · Company workspace"}`}
        sector={company?.sector}
        cacheState={company?.cache_state ?? null}
        description="Primary company identity, key fundamentals, and price-versus-operating performance in a single high-trust research surface."
        aside={refreshState ? <StatusPill state={refreshState} /> : undefined}
        facts={[
          { label: "Ticker", value: ticker },
          { label: "CIK", value: company?.cik ?? null },
          { label: "Last Checked", value: company?.last_checked ? formatDate(company.last_checked) : null }
        ]}
        ribbonItems={[
          { label: "Financials", value: company?.last_checked_financials ? formatDate(company.last_checked_financials) : "Pending", tone: "green" },
          { label: "Prices", value: company?.last_checked_prices ? formatDate(company.last_checked_prices) : "Pending", tone: "cyan" },
          { label: "Refresh", value: refreshState?.job_id ? "Queued" : "Background-first", tone: refreshState?.job_id ? "cyan" : "green" }
        ]}
        summaries={[
          { label: "Revenue", value: formatCompactNumber(latestFinancial?.revenue), accent: "cyan" },
          { label: "EPS", value: latestFinancial?.eps == null ? "?" : latestFinancial.eps.toFixed(2), accent: latestFinancial?.eps != null && latestFinancial.eps < 0 ? "red" : "cyan" },
          { label: "Net Income", value: formatCompactNumber(latestFinancial?.net_income), accent: latestFinancial?.net_income != null && latestFinancial.net_income < 0 ? "red" : "cyan" },
          { label: "Free Cash Flow", value: formatCompactNumber(latestFinancial?.free_cash_flow), accent: latestFinancial?.free_cash_flow != null && latestFinancial.free_cash_flow < 0 ? "red" : "cyan" }
        ]}
        className="financial-hero"
      >
        <CommercialFallbackNotice
          provenance={data?.provenance}
          sourceMix={data?.source_mix}
          subject="Price history and market profile data on this overview surface"
        />
      </CompanyResearchHeader>

      <div className="company-overview-stage models-page-span-full">
        <PriceFundamentalsModule
          priceData={priceHistory}
          fundamentalsData={fundamentalsTrendData}
          title="Price and Operating Momentum"
          subtitle="Start with price action, revenue growth, EPS trend, and cash generation before moving into secondary modules."
        />
      </div>

      <div className="company-overview-secondary-grid models-page-span-full">
        <Panel
          title="Visualization Lab"
          subtitle="Unified SEC-first chart system with consistent controls, event annotations, provenance badges, and CSV export"
          variant="subtle"
        >
          <CompanyVisualizationLab ticker={ticker} financials={financials} reloadKey={reloadKey} />
        </Panel>

        <Panel title="Cash Flow Bridge" subtitle="How operating cash flow turns into free cash flow and capital allocation uses" variant="subtle">
          <CashFlowWaterfallChart financials={financials} />
        </Panel>

        <Panel title="Liquidity & Capital" subtitle="Current assets, current liabilities, current ratio, and retained earnings trend" variant="subtle">
          <LiquidityCapitalChart financials={financials} />
        </Panel>

        <Panel title="Share Dilution" subtitle="Shares outstanding history and year-over-year dilution rate from SEC filings" variant="subtle">
          <ShareDilutionTrackerChart financials={financials} />
        </Panel>

        <Panel title="Segments & Geography" subtitle="Mix shifts, concentration, margin contribution, and chart views from cached SEC disclosures" variant="subtle">
          <BusinessSegmentBreakdown financials={financials} segmentAnalysis={data?.segment_analysis ?? null} />
        </Panel>

        <Panel title="Changes Since Last Filing" subtitle="Latest filing versus the prior comparable filing, including amended prior values" variant="subtle">
          <ChangesSinceLastFilingCard ticker={ticker} reloadKey={reloadKey} />
        </Panel>

        <Panel title="Derived Metrics Explorer" subtitle="Persisted SEC-derived metrics with provenance and quality flags" variant="subtle">
          <MetricsExplorerPanel ticker={ticker} reloadKey={reloadKey} />
        </Panel>

        <Panel title="10-Year Financial History" subtitle="SEC EDGAR companyfacts (FY)" variant="subtle">
          <FinancialHistorySection cik={company?.cik ?? null} />
        </Panel>
      </div>

      <PeerComparisonDashboard ticker={ticker} reloadKey={reloadKey} />

      <Panel
        title="Research Pulse"
        subtitle="Latest filing activity, alert counts, and freshness cues to orient the read before deeper module work."
        className="company-overview-pulse"
        variant="subtle"
      >
        {activityError ? (
          <div className="text-muted">{activityError}</div>
        ) : activityLoading ? (
          <div className="text-muted">Loading activity feed...</div>
        ) : (
          <div className="company-pulse-stack">
            <SourceFreshnessSummary
              provenance={activityData?.provenance}
              asOf={activityData?.as_of}
              lastRefreshedAt={activityData?.last_refreshed_at}
              sourceMix={activityData?.source_mix}
              confidenceFlags={activityData?.confidence_flags}
            />

            <CompanyMetricGrid
              items={[
                { label: "Feed Entries", value: (activityData?.entries.length ?? 0).toLocaleString() },
                { label: "High Alerts", value: (activityData?.summary.high ?? 0).toLocaleString() },
                { label: "Medium Alerts", value: (activityData?.summary.medium ?? 0).toLocaleString() },
                { label: "Total Alerts", value: (activityData?.summary.total ?? 0).toLocaleString() }
              ]}
            />

            <div className="company-pulse-columns">
              <div className="company-pulse-list">
                <div className="company-pulse-heading">Top Alerts</div>
                {topAlerts.length ? topAlerts.map((alert) => (
                  <AlertOrEntryCard
                    key={alert.id}
                    href={alert.href}
                    danger={alert.level === "high"}
                    topLeft={
                      <>
                        <span className="pill">{alert.level}</span>
                        <span className="pill">{alert.source}</span>
                      </>
                    }
                    topRight={formatDate(alert.date)}
                    title={alert.title}
                    detail={alert.detail}
                  />
                )) : <div className="text-muted">No alerts triggered from current cached SEC activity.</div>}
              </div>

              <div className="company-pulse-list">
                <div className="company-pulse-heading">Latest Timeline</div>
                {latestEntries.length ? latestEntries.map((entry) => (
                  <AlertOrEntryCard
                    key={entry.id}
                    href={entry.href}
                    topLeft={
                      <>
                        <span className="pill">{formatFeedEntryType(entry.type)}</span>
                        <span className="pill">{entry.badge}</span>
                      </>
                    }
                    topRight={formatDate(entry.date)}
                    title={entry.title}
                    detail={entry.detail}
                  />
                )) : <div className="text-muted">No activity entries available yet.</div>}
              </div>
            </div>
          </div>
        )}
      </Panel>
    </CompanyWorkspaceShell>
  );
}

function formatMarketContextStatus(status: CompanyActivityOverviewResponse["market_context_status"]): string {
  if (!status) {
    return "Unavailable";
  }
  const observed = status.observation_date ? ` (${formatDate(status.observation_date)})` : "";
  return `${status.label}${observed}`;
}

function formatFeedEntryType(type: string): string {
  if (type === "form144") {
    return "planned-sale";
  }
  return type;
}

function AlertOrEntryCard({
  href,
  topLeft,
  topRight,
  title,
  detail,
  danger = false,
}: {
  href: string | null;
  topLeft: ReactNode;
  topRight: string;
  title: string;
  detail: string;
  danger?: boolean;
}) {
  const content = (
    <>
      <div className="company-pulse-card-top">
        <div className="company-pulse-card-pills">{topLeft}</div>
        <div className="text-muted">{topRight}</div>
      </div>
      <div className="company-pulse-card-title">{title}</div>
      <div className="company-pulse-card-detail">{detail}</div>
    </>
  );

  if (href) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className={`filing-link-card company-pulse-card${danger ? " is-danger" : ""}`}
        style={{ display: "grid", gap: 8, textDecoration: "none" }}
      >
        {content}
      </a>
    );
  }

  return (
    <div className={`filing-link-card company-pulse-card${danger ? " is-danger" : ""}`} style={{ display: "grid", gap: 8 }}>
      {content}
    </div>
  );
}
