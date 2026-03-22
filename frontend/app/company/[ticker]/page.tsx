"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";

import { RiskRedFlagPanel } from "@/components/alerts/risk-red-flag-panel";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { Panel } from "@/components/ui/panel";
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
const PeerComparisonDashboard = dynamic(
  () => import("@/components/peers/peer-comparison-dashboard").then((module) => module.PeerComparisonDashboard),
  { ssr: false }
);

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
  const latestEntries = useMemo(() => (activityData?.entries ?? []).slice(0, 8), [activityData?.entries]);

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
          <Panel title="Risk & Red Flags" subtitle="Ongoing watchlist of balance-sheet, cash-flow, dilution, and distress signals">
            <RiskRedFlagPanel financials={financials} />
          </Panel>

          <Panel title="Live Activity & Alerts" subtitle="Latest SEC activity including events, ownership changes, insider trades, Form 144 planned sales, and prioritized alerts">
            {activityError ? (
              <div className="text-muted">{activityError}</div>
            ) : activityLoading ? (
              <div className="text-muted">Loading activity feed...</div>
            ) : (
              <div style={{ display: "grid", gap: 16 }}>
                <div className="metric-grid">
                  <Metric label="Feed Entries" value={(activityData?.entries.length ?? 0).toLocaleString()} />
                  <Metric label="High Alerts" value={(activityData?.summary.high ?? 0).toLocaleString()} />
                  <Metric label="Medium Alerts" value={(activityData?.summary.medium ?? 0).toLocaleString()} />
                  <Metric label="Total Alerts" value={(activityData?.summary.total ?? 0).toLocaleString()} />
                </div>

                <div style={{ display: "grid", gap: 12 }}>
                  <div style={{ fontWeight: 600, color: "var(--text)" }}>Top Alerts</div>
                  {topAlerts.length ? topAlerts.map((alert) => (
                    <AlertOrEntryCard
                      key={alert.id}
                      href={alert.href}
                      borderColor={alert.level === "high" ? "rgba(255, 83, 83, 0.5)" : undefined}
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

                <div style={{ display: "grid", gap: 12 }}>
                  <div style={{ fontWeight: 600, color: "var(--text)" }}>Latest Timeline Entries</div>
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
            )}
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

function AlertOrEntryCard({
  href,
  topLeft,
  topRight,
  title,
  detail,
  borderColor,
}: {
  href: string | null;
  topLeft: ReactNode;
  topRight: string;
  title: string;
  detail: string;
  borderColor?: string;
}) {
  const content = (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>{topLeft}</div>
        <div className="text-muted">{topRight}</div>
      </div>
      <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text)" }}>{title}</div>
      <div className="text-muted" style={{ fontSize: 13 }}>{detail}</div>
    </>
  );

  if (href) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className="filing-link-card"
        style={{ display: "grid", gap: 8, textDecoration: "none", borderColor }}
      >
        {content}
      </a>
    );
  }

  return (
    <div className="filing-link-card" style={{ display: "grid", gap: 8, borderColor }}>
      {content}
    </div>
  );
}
