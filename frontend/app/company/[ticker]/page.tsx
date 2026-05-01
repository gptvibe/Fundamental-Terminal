"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";

import { RiskRedFlagPanel } from "@/components/alerts/risk-red-flag-panel";
import { ResearchBriefPlainEnglishPanel } from "@/components/company/research-brief-plain-english-panel";
import { SourceFreshnessTimeline } from "@/components/company/source-freshness-timeline";
import { CompanyMetricGrid, CompanyResearchHeader } from "@/components/layout/company-research-header";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { resolveCommercialFallbackLabels } from "@/components/ui/commercial-fallback-notice";
import { EvidenceMetaBlock } from "@/components/ui/evidence-meta-block";
import { Panel } from "@/components/ui/panel";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { showAppToast } from "@/lib/app-toast";
import { COMMAND_PALETTE_EXPORT_MEMO_EVENT, type CommandPaletteTickerDetail } from "@/lib/command-palette-events";
import {
  getCompanyActivityOverview,
  getCompanyBeneficialOwnershipSummary,
  getCompanyEquityClaimRisk,
  getCompanyCapitalMarketsSummary,
  getCompanyCapitalStructure,
  getCompanyChangesSinceLastFiling,
  getCompanyEarningsSummary,
  getCompanyFinancials,
  getCompanyGovernanceSummary,
  getCompanyInsiderTrades,
  getCompanyInstitutionalHoldings,
  getCompanyMetricsTimeseries,
  getCompanyModels,
  getCompanyPeers,
  getCompanyResearchBrief,
} from "@/lib/api";
import { withPerformanceAuditSource } from "@/lib/performance-audit";
import {
  toneForAlertLevel,
  toneForAlertSource,
  toneForEntryBadge,
  toneForEntryCard,
  toneForEntryType,
  toneForInsiderSentiment,
  type SemanticTone,
} from "@/lib/activity-feed-tone";
import { MODEL_NAMES } from "@/lib/constants";
import { prefetchCompanyWorkspaceTabs } from "@/lib/company-workspace-prefetch";
import { downloadJsonFile, normalizeExportFileStem } from "@/lib/export";
import { formatCompactNumber, formatDate, formatPercent, titleCase } from "@/lib/format";
import type {
  CompanyActivityOverviewResponse,
  CompanyBeneficialOwnershipSummaryResponse,
  CompanyCapitalMarketsSummaryResponse,
  CompanyCapitalStructureResponse,
  ConsoleEntry,
  CompanyChangesSinceLastFilingResponse,
  CompanyEarningsSummaryResponse,
  EquityClaimRiskSummaryPayload,
  CompanyGovernanceSummaryResponse,
  CompanyModelsResponse,
  CompanyPeersResponse,
  CompanyResearchBriefResponse,
  FinancialPayload,
  FilingTimelineItemPayload,
  ProvenanceEntryPayload,
  RefreshState,
  ResearchBriefBuildState,
  ResearchBriefSectionStatusPayload,
  ResearchBriefSummaryCardPayload,
  SourceMixPayload,
} from "@/lib/types";

const PriceFundamentalsModule = dynamic(
  () => import("@/components/charts/price-fundamentals-module").then((module) => module.PriceFundamentalsModule),
  { ssr: false, loading: () => <div className="text-muted">Loading price and fundamentals...</div> }
);
const BusinessSegmentBreakdown = dynamic(
  () => import("@/components/charts/business-segment-breakdown").then((module) => module.BusinessSegmentBreakdown),
  { ssr: false, loading: () => <div className="text-muted">Loading segment breakdown...</div> }
);
const ChangesSinceLastFilingCard = dynamic(
  () => import("@/components/company/changes-since-last-filing-card").then((module) => module.ChangesSinceLastFilingCard),
  { ssr: false, loading: () => <div className="text-muted">Loading filing comparison...</div> }
);
const CashFlowWaterfallChart = dynamic(
  () => import("@/components/charts/cash-flow-waterfall-chart").then((module) => module.CashFlowWaterfallChart),
  { ssr: false, loading: () => <div className="text-muted">Loading cash flow bridge...</div> }
);
const MarginTrendChart = dynamic(
  () => import("@/components/charts/margin-trend-chart").then((module) => module.MarginTrendChart),
  { ssr: false, loading: () => <div className="text-muted">Loading margin trends...</div> }
);
const FinancialQualitySummary = dynamic(
  () => import("@/components/company/financial-quality-summary").then((module) => module.FinancialQualitySummary),
  { ssr: false, loading: () => <div className="text-muted">Loading quality summary...</div> }
);
const ShareDilutionTrackerChart = dynamic(
  () => import("@/components/charts/share-dilution-tracker-chart").then((module) => module.ShareDilutionTrackerChart),
  { ssr: false, loading: () => <div className="text-muted">Loading dilution tracker...</div> }
);
const CapitalStructureIntelligencePanel = dynamic(
  () => import("@/components/company/capital-structure-intelligence-panel").then((module) => module.CapitalStructureIntelligencePanel),
  { ssr: false, loading: () => <div className="text-muted">Loading capital structure intelligence...</div> }
);
const InvestmentSummaryPanel = dynamic(
  () => import("@/components/models/investment-summary-panel").then((module) => module.InvestmentSummaryPanel),
  { ssr: false, loading: () => <div className="text-muted">Loading valuation summary...</div> }
);

type AsyncState<T> = {
  data: T | null;
  error: string | null;
  loading: boolean;
};

type ResearchBriefAsyncState = {
  activityOverview: AsyncState<CompanyActivityOverviewResponse>;
  changes: AsyncState<CompanyChangesSinceLastFilingResponse>;
  earningsSummary: AsyncState<CompanyEarningsSummaryResponse>;
  capitalStructure: AsyncState<CompanyCapitalStructureResponse>;
  capitalMarketsSummary: AsyncState<CompanyCapitalMarketsSummaryResponse>;
  governanceSummary: AsyncState<CompanyGovernanceSummaryResponse>;
  ownershipSummary: AsyncState<CompanyBeneficialOwnershipSummaryResponse>;
  models: AsyncState<CompanyModelsResponse>;
  peers: AsyncState<CompanyPeersResponse>;
};

type ResearchBriefDataState = ResearchBriefAsyncState & {
  brief: CompanyResearchBriefResponse | null;
  error: string | null;
  loading: boolean;
  buildState: ResearchBriefBuildState;
  buildStatus: string | null;
  availableSections: string[];
  sectionStatuses: ResearchBriefSectionStatusPayload[];
  filingTimeline: FilingTimelineItemPayload[];
  summaryCards: ResearchBriefSummaryCardPayload[];
};

type ResearchBriefCue = {
  label: string;
  asOf?: string | null;
  lastRefreshedAt?: string | null;
  lastChecked?: string | null;
  provenance?: ProvenanceEntryPayload[] | null;
  sourceMix?: SourceMixPayload | null;
  confidenceFlags?: string[] | null;
};

type SectionLink = {
  href: string;
  label: string;
};

type MonitorChecklistItem = {
  title: string;
  detail: string;
  tone: SemanticTone;
};

type BriefCompany = {
  ticker?: string | null;
  name?: string | null;
  last_checked?: string | null;
};

const BRIEF_SECTIONS = [
  {
    id: "snapshot",
    title: "Snapshot",
    question: "What matters before I read further?",
  },
  {
    id: "what-changed",
    title: "What changed",
    question: "What is new since the last filing or review?",
  },
  {
    id: "business-quality",
    title: "Business quality",
    question: "Is the business getting stronger, weaker, or just noisier?",
  },
  {
    id: "capital-risk",
    title: "Capital & risk",
    question: "Is the equity claim being protected, diluted, or put at risk?",
  },
  {
    id: "valuation",
    title: "Valuation",
    question: "How does the current price compare with peers and cached model ranges?",
  },
  {
    id: "monitor",
    title: "Monitor",
    question: "What should I keep watching after I leave this page?",
  },
] as const;

const BRIEF_SECTION_IDS = BRIEF_SECTIONS.map((section) => section.id);
const RESEARCH_BRIEF_SECTION_STORAGE_PREFIX = "fundamental-terminal:research-brief:sections";

const INITIAL_ASYNC_STATE: ResearchBriefAsyncState = {
  activityOverview: { data: null, error: null, loading: true },
  changes: { data: null, error: null, loading: true },
  earningsSummary: { data: null, error: null, loading: true },
  capitalStructure: { data: null, error: null, loading: true },
  capitalMarketsSummary: { data: null, error: null, loading: true },
  governanceSummary: { data: null, error: null, loading: true },
  ownershipSummary: { data: null, error: null, loading: true },
  models: { data: null, error: null, loading: true },
  peers: { data: null, error: null, loading: true },
};

const INITIAL_RESEARCH_BRIEF_DATA_STATE: ResearchBriefDataState = {
  ...INITIAL_ASYNC_STATE,
  brief: null,
  error: null,
  loading: true,
  buildState: "building",
  buildStatus: null,
  availableSections: [],
  sectionStatuses: [],
  filingTimeline: [],
  summaryCards: [],
};

export default function CompanyResearchBriefPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(params.ticker).toUpperCase();
  const idlePrefetchTickerRef = useRef<string | null>(null);
  const {
    data,
    company,
    financials,
    annualStatements,
    priceHistory,
    fundamentalsTrendData,
    latestFinancial,
    briefData: initialBriefData,
    loading,
    error,
    refreshing,
    refreshState,
    activeJobId,
    consoleEntries,
    connectionState,
    queueRefresh,
    reloadKey,
  } = useCompanyWorkspace(ticker, {
    includeInsiders: false,
    includeInstitutional: false,
    includeOverviewBrief: true,
    includeChartConsole: true,
    auditPageRoute: "/company/[ticker]",
    auditScenario: "company_overview",
  });

  useEffect(() => {
    idlePrefetchTickerRef.current = null;
  }, [ticker]);

  useEffect(() => {
    if (idlePrefetchTickerRef.current === ticker) {
      return;
    }

    if (loading || !data) {
      return;
    }

    idlePrefetchTickerRef.current = ticker;

    const schedule = (callback: () => void): number => {
      if (typeof window !== "undefined" && typeof window.requestIdleCallback === "function") {
        return window.requestIdleCallback(callback, { timeout: 1500 }) as unknown as number;
      }

      return window.setTimeout(callback, 180);
    };

    const cancel = (id: number): void => {
      if (typeof window !== "undefined" && typeof window.cancelIdleCallback === "function") {
        window.cancelIdleCallback(id as unknown as number);
        return;
      }

      window.clearTimeout(id);
    };

    const scheduledId = schedule(() => {
      void prefetchCompanyWorkspaceTabs(ticker, {
        trigger: "idle",
        activeRefreshJobId: activeJobId ?? refreshState?.job_id ?? null,
        pageRoute: "/company/[ticker]",
        scenario: "company_overview",
      });
    });

    return () => {
      cancel(scheduledId);
    };
  }, [activeJobId, data, loading, refreshState?.job_id, ticker]);

  const briefData = useResearchBriefData(
    ticker,
    reloadKey,
    initialBriefData,
    loading,
    activeJobId ?? refreshState?.job_id ?? initialBriefData?.refresh.job_id ?? null
  );
  const activeSectionId = useActiveBriefSection(BRIEF_SECTION_IDS);
  const { expandedSections, toggleSection } = useResearchBriefSectionPreferences(ticker);
  const [exportingResearchPackage, setExportingResearchPackage] = useState(false);
  const pageCompany = company ?? briefData.brief?.company ?? data?.company ?? briefData.activityOverview.data?.company ?? briefData.models.data?.company ?? null;
  const topSegment = useMemo(() => extractTopSegment(latestFinancial), [latestFinancial]);
  const fallbackLabels = useMemo(() => resolveCommercialFallbackLabels(data?.provenance, data?.source_mix), [data?.provenance, data?.source_mix]);
  const previousAnnual = annualStatements[1] ?? null;
  const foreignIssuerStyleFiling = isForeignIssuerAnnualForm(latestFinancial?.filing_type);
  const latestAlertCount = briefData.activityOverview.data?.summary.total ?? 0;
  const topAlerts = useMemo(() => (briefData.activityOverview.data?.alerts ?? []).slice(0, 3), [briefData.activityOverview.data?.alerts]);
  const latestEntries = useMemo(() => (briefData.activityOverview.data?.entries ?? []).slice(0, 4), [briefData.activityOverview.data?.entries]);
  const equityClaimRiskSummary = briefData.brief?.capital_and_risk.equity_claim_risk_summary ?? null;
  const capitalSignalRows = useMemo(
    () =>
      buildCapitalSignalRows({
        capitalMarketsSummary: briefData.capitalMarketsSummary.data?.summary ?? null,
        governanceSummary: briefData.governanceSummary.data?.summary ?? null,
        ownershipSummary: briefData.ownershipSummary.data?.summary ?? null,
        equityClaimRiskSummary,
        isForeignIssuerLike: foreignIssuerStyleFiling,
      }),
    [
      briefData.capitalMarketsSummary.data?.summary,
      briefData.governanceSummary.data?.summary,
      briefData.ownershipSummary.data?.summary,
      equityClaimRiskSummary,
      foreignIssuerStyleFiling,
    ]
  );
  const monitorChecklist = useMemo(
    () =>
      buildMonitorChecklist({
        refreshState,
        activityOverview: briefData.activityOverview.data,
        company: pageCompany,
        ownershipSummary: briefData.ownershipSummary.data?.summary ?? null,
        capitalMarketsSummary: briefData.capitalMarketsSummary.data?.summary ?? null,
      }),
    [
      briefData.activityOverview.data,
      briefData.capitalMarketsSummary.data?.summary,
      briefData.ownershipSummary.data?.summary,
      pageCompany,
      refreshState,
    ]
  );
  const snapshotLinks = useMemo(
    () => [
      { href: `/company/${encodeURIComponent(ticker)}/financials`, label: "Financials" },
      { href: `/company/${encodeURIComponent(ticker)}/filings`, label: "Filings" },
    ],
    [ticker]
  );
  const whatChangedLinks = useMemo(
    () => [
      { href: `/company/${encodeURIComponent(ticker)}/earnings`, label: "Earnings" },
      { href: `/company/${encodeURIComponent(ticker)}/events`, label: "Events" },
    ],
    [ticker]
  );
  const businessQualityLinks = useMemo(
    () => [
      { href: `/company/${encodeURIComponent(ticker)}/financials`, label: "Full Financials" },
      { href: `/company/${encodeURIComponent(ticker)}/earnings`, label: "Earnings Detail" },
    ],
    [ticker]
  );
  const capitalRiskLinks = useMemo(
    () => [
      { href: `/company/${encodeURIComponent(ticker)}/capital-markets`, label: "Equity Claim Risk Pack" },
      { href: `/company/${encodeURIComponent(ticker)}/governance`, label: "Governance" },
    ],
    [ticker]
  );
  const valuationLinks = useMemo(
    () => [
      { href: `/company/${encodeURIComponent(ticker)}/models`, label: "Models" },
      { href: `/company/${encodeURIComponent(ticker)}/peers`, label: "Peers" },
    ],
    [ticker]
  );
  const monitorLinks = useMemo(
    () => [
      { href: `/company/${encodeURIComponent(ticker)}/sec-feed`, label: "SEC Feed" },
      { href: `/company/${encodeURIComponent(ticker)}/events`, label: "Events" },
    ],
    [ticker]
  );

  const snapshotNarrative = buildSnapshotNarrative({
    company: pageCompany,
    latestFinancial,
    topSegment,
    alertCount: latestAlertCount,
    buildState: briefData.buildState,
    filingTimeline: briefData.filingTimeline,
    sourceMix: data?.source_mix,
    provenance: data?.provenance,
    loading,
  });
  const whatChangedNarrative = buildWhatChangedNarrative({
    changes: briefData.changes.data,
    earningsSummary: briefData.earningsSummary.data,
    activityOverview: briefData.activityOverview.data,
    loading: briefData.changes.loading || briefData.earningsSummary.loading || briefData.activityOverview.loading,
  });
  const businessQualityNarrative = buildBusinessQualityNarrative({
    latestFinancial,
    previousAnnual,
    loading,
  });
  const capitalRiskNarrative = buildCapitalRiskNarrative({
    capitalStructure: briefData.capitalStructure.data,
    capitalMarketsSummary: briefData.capitalMarketsSummary.data,
    governanceSummary: briefData.governanceSummary.data,
    ownershipSummary: briefData.ownershipSummary.data,
    equityClaimRiskSummary,
    isForeignIssuerLike: foreignIssuerStyleFiling,
    loading:
      briefData.capitalStructure.loading ||
      briefData.capitalMarketsSummary.loading ||
      briefData.governanceSummary.loading ||
      briefData.ownershipSummary.loading,
  });
  const valuationNarrative = buildValuationNarrative({
    models: briefData.models.data?.models ?? [],
    peers: briefData.peers.data?.peers ?? [],
    priceHistory,
    loading: briefData.models.loading || briefData.peers.loading,
  });
  const monitorNarrative = buildMonitorNarrative({
    activityOverview: briefData.activityOverview.data,
    refreshState,
    company: pageCompany,
    loading: briefData.activityOverview.loading,
  });
  const bootstrapRevenueValue = findBriefSummaryCardValue(briefData.summaryCards, "Revenue");
  const bootstrapFreeCashFlowValue = findBriefSummaryCardValue(briefData.summaryCards, "Free Cash Flow");
  const bootstrapTopSegmentValue = findBriefSummaryCardValue(briefData.summaryCards, "Top Segment");
  const bootstrapLatestFilingValue = findBriefSummaryCardValue(briefData.summaryCards, "Latest Filing");
  const activeRefreshEntry = useMemo(() => {
    if (!activeJobId) {
      return null;
    }

    for (let index = consoleEntries.length - 1; index >= 0; index -= 1) {
      const entry = consoleEntries[index];
      if (entry.source === "backend" && entry.job_id === activeJobId) {
        return entry;
      }
    }

    return null;
  }, [activeJobId, consoleEntries]);
  const initialCompanyLoad =
    loading &&
    !pageCompany &&
    !latestFinancial &&
    !financials.length &&
    !priceHistory.length &&
    !briefData.brief &&
    !briefData.activityOverview.data &&
    !error &&
    !briefData.error;
  const refreshQueueDetailLine = useMemo(() => buildRefreshQueueDetailLine(activeRefreshEntry), [activeRefreshEntry]);
  const initialCompanyLoadMessage = useMemo(
    () => buildInitialCompanyLoadMessage(initialCompanyLoad, activeRefreshEntry, briefData.buildState, briefData.buildStatus),
    [activeRefreshEntry, briefData.buildState, briefData.buildStatus, initialCompanyLoad]
  );

  const handleExportResearchPackage = useCallback(async () => {
    try {
      setExportingResearchPackage(true);

      const exportRequests = [
        ["financials", () => getCompanyFinancials(ticker)],
        ["insider_trades", () => getCompanyInsiderTrades(ticker)],
        ["institutional_holdings", () => getCompanyInstitutionalHoldings(ticker)],
        ["activity_overview", () => getCompanyActivityOverview(ticker)],
        ["changes_since_last_filing", () => getCompanyChangesSinceLastFiling(ticker)],
        ["earnings_summary", () => getCompanyEarningsSummary(ticker)],
        ["capital_structure", () => getCompanyCapitalStructure(ticker)],
        ["capital_markets_summary", () => getCompanyCapitalMarketsSummary(ticker)],
        ["equity_claim_risk", () => getCompanyEquityClaimRisk(ticker)],
        ["governance_summary", () => getCompanyGovernanceSummary(ticker)],
        ["beneficial_ownership_summary", () => getCompanyBeneficialOwnershipSummary(ticker)],
        ["models", () => getCompanyModels(ticker, MODEL_NAMES)],
        ["peers", () => getCompanyPeers(ticker)],
        ["derived_metrics_timeseries_quarterly", () => getCompanyMetricsTimeseries(ticker, { cadence: "quarterly", maxPoints: 24 })],
        ["derived_metrics_timeseries_annual", () => getCompanyMetricsTimeseries(ticker, { cadence: "annual", maxPoints: 24 })],
        ["derived_metrics_timeseries_ttm", () => getCompanyMetricsTimeseries(ticker, { cadence: "ttm", maxPoints: 24 })],
      ] as const;

      const endpointEntries = await Promise.all(
        exportRequests.map(async ([key, load]) => {
          try {
            return [key, { status: "fulfilled", payload: await load() }] as const;
          } catch (nextError) {
            return [
              key,
              {
                status: "rejected",
                error: nextError instanceof Error ? nextError.message : "Request failed",
              },
            ] as const;
          }
        })
      );

      downloadJsonFile(`${normalizeExportFileStem(ticker, "company")}-research-package.json`, {
        exported_at: new Date().toISOString(),
        ticker,
        company: pageCompany,
        endpoints: Object.fromEntries(endpointEntries),
      });
      showAppToast({ message: "Research package exported as JSON.", tone: "info" });
    } catch (nextError) {
      showAppToast({
        message: nextError instanceof Error ? nextError.message : "Unable to export research package.",
        tone: "danger",
      });
    } finally {
      setExportingResearchPackage(false);
    }
  }, [pageCompany, ticker]);

  useEffect(() => {
    function onCommandExportMemo(event: Event) {
      const customEvent = event as CustomEvent<CommandPaletteTickerDetail>;
      if (customEvent.detail?.ticker !== ticker) {
        return;
      }

      void handleExportResearchPackage();
    }

    window.addEventListener(COMMAND_PALETTE_EXPORT_MEMO_EVENT, onCommandExportMemo as EventListener);
    return () => window.removeEventListener(COMMAND_PALETTE_EXPORT_MEMO_EVENT, onCommandExportMemo as EventListener);
  }, [handleExportResearchPackage, ticker]);

  return (
    <CompanyWorkspaceShell
      rail={
        <CompanyUtilityRail
          ticker={ticker}
          companyName={pageCompany?.name ?? null}
          sector={pageCompany?.sector ?? pageCompany?.market_sector ?? null}
          refreshState={refreshState}
          refreshing={refreshing}
          onRefresh={() => queueRefresh()}
          actionTitle="Next steps"
          actionSubtitle="Refresh the brief in the background or jump straight into the full underwriting workspace."
          primaryActionLabel="Refresh Brief Data"
          primaryActionDescription="Rebuilds cached company, filing, market, and summary surfaces without turning the default brief into a live-fetch route."
          secondaryActionHref={`/company/${encodeURIComponent(ticker)}/models`}
          secondaryActionLabel="Open Valuation Models"
          secondaryActionDescription="Move from the brief into full model diagnostics, scenarios, and assumption detail."
          extraActions={[
            {
              label: exportingResearchPackage ? "Exporting..." : "Export Research Package",
              description: "Download the company financial, model, derived-metric, and brief endpoint responses as JSON.",
              onClick: handleExportResearchPackage,
              disabled: exportingResearchPackage || initialCompanyLoad,
            },
          ]}
          statusLines={[
            `Annual filings available: ${annualStatements.length.toLocaleString()}`,
            `Price history points available: ${priceHistory.length.toLocaleString()}`,
            `Current alerts: ${latestAlertCount.toLocaleString()}`,
            `Last checked: ${pageCompany?.last_checked ? formatDate(pageCompany.last_checked) : "Pending"}`,
          ]}
          consoleEntries={consoleEntries}
          connectionState={connectionState}
          presentation="brief"
        >
          <Panel title="Risk & red flags" subtitle="Ongoing watchlist of balance-sheet, cash-flow, dilution, and distress signals" variant="subtle">
            <RiskRedFlagPanel financials={financials} />
          </Panel>
        </CompanyUtilityRail>
      }
      mainClassName="company-page-grid research-brief-layout"
      railClassName="research-brief-rail"
    >
      <CompanyResearchHeader
        ticker={ticker}
        title={pageCompany?.name ?? ticker}
        companyName={`${ticker} · Research Brief`}
        sector={pageCompany?.sector ?? pageCompany?.market_sector ?? null}
        freshness={{
          cacheState: pageCompany?.cache_state ?? null,
          refreshState,
          loading,
          hasData: Boolean(pageCompany || latestFinancial || financials.length || priceHistory.length),
          lastChecked: pageCompany?.last_checked ?? null,
          errors: [error, briefData.error],
          detailLines: [
            refreshQueueDetailLine,
            `Annual filings cached: ${annualStatements.length.toLocaleString()}`,
            `Price history points: ${priceHistory.length.toLocaleString()}`,
            `Current alerts: ${latestAlertCount.toLocaleString()}`,
          ],
        }}
        freshnessPlacement="title"
        className="research-brief-header-compact"
      >
        <ResearchBriefHeroSummary
          summary={snapshotNarrative}
          metrics={[
            { label: "Revenue", value: latestFinancial ? formatCompactCurrency(latestFinancial.revenue) : bootstrapRevenueValue },
            { label: "Free Cash Flow", value: latestFinancial ? formatCompactCurrency(latestFinancial.free_cash_flow) : bootstrapFreeCashFlowValue },
            {
              label: "Top Segment",
              value:
                topSegment && topSegment.share_of_revenue != null
                  ? `${topSegment.segment_name} · ${formatPercent(topSegment.share_of_revenue)}`
                  : topSegment?.segment_name ?? bootstrapTopSegmentValue,
            },
            {
              label: "Latest Filing",
              value: latestFinancial ? `${latestFinancial.filing_type} · ${formatDate(latestFinancial.period_end)}` : bootstrapLatestFilingValue,
            },
          ]}
          metaItems={[
            pageCompany?.cik ? `CIK ${pageCompany.cik}` : null,
            annualStatements.length ? `${annualStatements.length.toLocaleString()} annual filing periods cached` : null,
            pageCompany?.last_checked ? `Updated ${formatDate(pageCompany.last_checked)}` : null,
          ]}
          fallbackLabels={fallbackLabels}
          loading={initialCompanyLoad}
          loadingMessage={initialCompanyLoadMessage}
        />
      </CompanyResearchHeader>

      <SourceFreshnessTimeline
        ticker={ticker}
        company={pageCompany}
        refreshState={refreshState}
        activeJobId={activeJobId}
        financialsResponse={data}
        filingTimeline={briefData.filingTimeline}
        asOf={data?.as_of ?? briefData.brief?.as_of ?? null}
        lastRefreshedAt={data?.last_refreshed_at ?? null}
        provenance={data?.provenance ?? null}
        sourceMix={data?.source_mix ?? null}
      />

      <ResearchBriefWarmupPanel
        buildState={briefData.buildState}
        buildStatus={briefData.buildStatus}
        sectionStatuses={mergeBusinessQualitySectionStatus(briefData.sectionStatuses, {
          loading,
          hasFinancials: Boolean(financials.length || latestFinancial),
        })}
        summaryCards={briefData.summaryCards}
        filingTimeline={briefData.filingTimeline}
        refreshState={briefData.brief?.refresh ?? refreshState}
      />

      {error || briefData.error ? (
        <div className="panel workspace-error-state research-brief-partial-note">
          <h2 className="workspace-state-title">Some brief inputs are still warming</h2>
          <p className="text-muted workspace-state-copy">
            The brief keeps specialist routes and cached section fallbacks visible even when one workspace payload is delayed. Refreshing the company will usually backfill the missing slice.
          </p>
          <div className="research-brief-partial-errors">
            {[error, briefData.error].filter(Boolean).map((message) => (
              <span key={message} className="pill">
                {message}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      <ResearchBriefSection
        id="snapshot"
        title="Snapshot"
        question="What matters before I read further?"
        summary={null}
        cues={[]}
        links={snapshotLinks}
        expanded={expandedSections.snapshot ?? true}
        onToggle={() => toggleSection("snapshot")}
      >
        <EvidenceCard
          title="Price vs operating momentum"
          copy="Operating history stays SEC-first; market context remains explicitly labeled when a commercial fallback is involved."
          className="is-wide"
        >
          {loading && !priceHistory.length && !fundamentalsTrendData.length ? (
            <ResearchBriefStateBlock
              kind="loading"
              kicker="Snapshot"
              title="Loading momentum view"
              message="Preparing the persisted price-versus-fundamentals comparison used at the top of the brief."
            />
          ) : priceHistory.length || fundamentalsTrendData.length ? (
            <PriceFundamentalsModule
              priceData={priceHistory}
              fundamentalsData={fundamentalsTrendData}
              title="Price and operating momentum"
              subtitle="Start with price action, revenue growth, EPS trend, and free-cash-flow direction before diving into specialist evidence."
            />
          ) : (
            <ResearchBriefStateBlock
              kind="empty"
              kicker="Snapshot"
              title="No momentum history yet"
              message="This visual appears once cached price history or annual filing trends are available for the company."
            />
          )}
        </EvidenceCard>

        <EvidenceCard title="Business context" copy="The minimum operating context needed before opening specialist views.">
          {loading && !latestFinancial ? (
            <ResearchBriefStateBlock
              kind="loading"
              kicker="Snapshot"
              title="Loading company context"
              message="Reading the latest cached filing, segment mix, and alert count for the default brief."
            />
          ) : latestFinancial || topSegment ? (
            <CompanyMetricGrid
              items={[
                { label: "Reported Revenue", value: latestFinancial ? formatCompactCurrency(latestFinancial.revenue) : null },
                { label: "Free Cash Flow", value: latestFinancial ? formatCompactCurrency(latestFinancial.free_cash_flow) : null },
                {
                  label: "Top Segment",
                  value:
                    topSegment && topSegment.share_of_revenue != null
                      ? `${topSegment.segment_name} · ${formatPercent(topSegment.share_of_revenue)}`
                      : topSegment?.segment_name ?? null,
                },
                { label: "Current Alerts", value: latestAlertCount.toLocaleString() },
              ]}
            />
          ) : (
            <ResearchBriefStateBlock
              kind="empty"
              kicker="Snapshot"
              title="No persisted filing context yet"
              message="Queue a refresh to populate the default brief from cached company financials, segments, and activity summaries."
            />
          )}
        </EvidenceCard>

        <EvidenceCard
          title="Reported segment mix"
          copy="Segment and geography mix orient the read before deeper statement or filing work."
          className="is-wide"
        >
          {loading && !financials.length ? (
            <ResearchBriefStateBlock
              kind="loading"
              kicker="Snapshot"
              title="Loading segment disclosures"
              message="Reading the latest persisted segment and geography disclosures from cached filings."
            />
          ) : financials.length ? (
            <BusinessSegmentBreakdown financials={financials} segmentAnalysis={data?.segment_analysis ?? null} />
          ) : (
            <ResearchBriefStateBlock
              kind="empty"
              kicker="Snapshot"
              title="No reported segment breakdown yet"
              message="This section fills in once cached filings include segment or geographic disclosure detail."
            />
          )}
        </EvidenceCard>
      </ResearchBriefSection>

      <ResearchBriefPlainEnglishPanel
        ticker={ticker}
        models={briefData.models.data?.models ?? []}
        modelsLoading={briefData.models.loading}
        modelsError={briefData.models.error}
        latestFinancial={latestFinancial}
        previousAnnual={previousAnnual}
        diagnostics={data?.diagnostics ?? null}
        confidenceFlags={data?.confidence_flags ?? null}
        strictOfficialMode={Boolean(pageCompany?.strict_official_mode)}
        reloadKey={reloadKey}
      />

      <ResearchBriefSectionNav activeSectionId={activeSectionId} />

      <ResearchBriefSection
        id="what-changed"
        title="What changed"
        question="What is new since the last filing or review?"
        summary={whatChangedNarrative}
        cues={[
          {
            label: "Filing comparison",
            asOf: briefData.changes.data?.as_of,
            lastRefreshedAt: briefData.changes.data?.last_refreshed_at,
            provenance: briefData.changes.data?.provenance,
            sourceMix: briefData.changes.data?.source_mix,
            confidenceFlags: briefData.changes.data?.confidence_flags,
          },
          {
            label: "Activity overview",
            asOf: briefData.activityOverview.data?.as_of,
            lastRefreshedAt: briefData.activityOverview.data?.last_refreshed_at,
            provenance: briefData.activityOverview.data?.provenance,
            sourceMix: briefData.activityOverview.data?.source_mix,
            confidenceFlags: briefData.activityOverview.data?.confidence_flags,
          },
        ]}
        links={whatChangedLinks}
        expanded={expandedSections["what-changed"] ?? true}
        onToggle={() => toggleSection("what-changed")}
      >
        <EvidenceCard title="Update scoreboard" copy="The shortest possible read on filing deltas, earnings capture, and alert volume.">
          {briefData.changes.error && !briefData.changes.data && briefData.earningsSummary.error && !briefData.earningsSummary.data ? (
            <ResearchBriefStateBlock
              kind="error"
              kicker="What changed"
              title="Unable to load change summaries"
              message={briefData.changes.error ?? briefData.earningsSummary.error ?? "Change summaries are temporarily unavailable."}
            />
          ) : briefData.changes.loading && !briefData.changes.data && briefData.earningsSummary.loading && !briefData.earningsSummary.data ? (
            <ResearchBriefStateBlock
              kind="loading"
              kicker="What changed"
              title="Loading latest deltas"
              message="Comparing the most recent filing, recent earnings payloads, and the cached activity overview."
            />
          ) : briefData.changes.data || briefData.earningsSummary.data || briefData.activityOverview.data ? (
            <CompanyMetricGrid
              items={[
                {
                  label: "High-Signal Changes",
                  value: briefData.changes.data ? String(briefData.changes.data.summary.high_signal_change_count) : null,
                },
                {
                  label: "Comment Letters",
                  value: briefData.changes.data ? String(briefData.changes.data.summary.comment_letter_count) : null,
                },
                {
                  label: "Latest EPS",
                  value:
                    briefData.earningsSummary.data?.summary.latest_diluted_eps != null
                      ? briefData.earningsSummary.data.summary.latest_diluted_eps.toFixed(2)
                      : null,
                },
                {
                  label: "High Alerts",
                  value: briefData.activityOverview.data ? String(briefData.activityOverview.data.summary.high) : null,
                },
              ]}
            />
          ) : (
            <ResearchBriefStateBlock
              kind="empty"
              kicker="What changed"
              title="No recent change summary yet"
              message="This section fills in after the latest filing comparison, earnings summary, or activity overview is cached."
            />
          )}
        </EvidenceCard>

        <EvidenceCard
          title="Latest filing comparison"
          copy="Only the highest-signal filing changes surface here by default; the filings drill-down keeps the broader metric and evidence detail."
          className="is-wide"
        >
          <ChangesSinceLastFilingCard
            ticker={ticker}
            reloadKey={reloadKey}
            initialPayload={briefData.changes.data}
            detailMode="brief"
            deferFetch={briefData.loading}
          />
        </EvidenceCard>

        <EvidenceCard
          title="Recent SEC activity"
          copy="Top alerts and the latest timeline entries keep the default brief anchored to dated evidence instead of generic commentary."
          className="is-wide"
        >
          {briefData.activityOverview.error && !briefData.activityOverview.data ? (
            <ResearchBriefStateBlock
              kind="error"
              kicker="What changed"
              title="Unable to load recent activity"
              message={briefData.activityOverview.error}
            />
          ) : briefData.activityOverview.loading && !briefData.activityOverview.data ? (
            <ResearchBriefStateBlock
              kind="loading"
              kicker="What changed"
              title="Loading recent activity"
              message="Preparing the latest persisted alerts and SEC timeline entries for the default brief."
            />
          ) : topAlerts.length || latestEntries.length ? (
            <div className="company-pulse-columns research-brief-pulse-columns">
              <div className="company-pulse-list">
                <div className="company-pulse-heading">Top alerts</div>
                {topAlerts.length ? (
                  topAlerts.map((alert) => {
                    const levelTone = toneForAlertLevel(alert.level);
                    const sourceTone = toneForAlertSource(alert.source);

                    return (
                      <AlertOrEntryCard
                        key={alert.id}
                        href={alert.href}
                        tone={levelTone}
                        topLeft={
                          <>
                            <span className={`pill tone-${levelTone}`}>{alert.level}</span>
                            <span className={`pill tone-${sourceTone}`}>{alert.source}</span>
                          </>
                        }
                        topRight={formatDate(alert.date)}
                        title={alert.title}
                        detail={alert.detail}
                      />
                    );
                  })
                ) : (
                  <ResearchBriefStateBlock
                    kind="empty"
                    kicker="What changed"
                    title="No current alerts"
                    message="No alert thresholds are currently triggered in the persisted activity overview."
                    minHeight={180}
                  />
                )}
              </div>

              <div className="company-pulse-list">
                <div className="company-pulse-heading">Latest timeline</div>
                {latestEntries.length ? (
                  latestEntries.map((entry) => {
                    const typeTone = toneForEntryType(entry.type);
                    const badgeTone = toneForEntryBadge(entry.type, entry.badge);
                    const cardTone = toneForEntryCard(entry);

                    return (
                      <AlertOrEntryCard
                        key={entry.id}
                        href={entry.href}
                        tone={cardTone}
                        topLeft={
                          <>
                            <span className={`pill tone-${typeTone}`}>{formatFeedEntryType(entry.type)}</span>
                            <span className={`pill tone-${badgeTone}`}>{entry.badge}</span>
                          </>
                        }
                        topRight={formatDate(entry.date)}
                        title={entry.title}
                        detail={entry.detail}
                      />
                    );
                  })
                ) : (
                  <ResearchBriefStateBlock
                    kind="empty"
                    kicker="What changed"
                    title="No recent timeline entries"
                    message="The cached activity stream will list the latest filing, governance, ownership, and insider events here once available."
                    minHeight={180}
                  />
                )}
              </div>
            </div>
          ) : (
            <ResearchBriefStateBlock
              kind="empty"
              kicker="What changed"
              title="No recent activity yet"
              message="This section fills in once the cached activity overview has alerts or dated SEC entries for the selected company."
            />
          )}
        </EvidenceCard>
      </ResearchBriefSection>

      <ResearchBriefSection
        id="business-quality"
        title="Business quality"
        question="Is the business getting stronger, weaker, or just noisier?"
        summary={businessQualityNarrative}
        cues={[
          {
            label: "Financial quality inputs",
            asOf: data?.as_of,
            lastRefreshedAt: data?.last_refreshed_at,
            lastChecked: pageCompany?.last_checked_financials,
            provenance: data?.provenance,
            sourceMix: data?.source_mix,
            confidenceFlags: data?.confidence_flags,
          },
        ]}
        links={businessQualityLinks}
        expanded={expandedSections["business-quality"] ?? true}
        onToggle={() => toggleSection("business-quality")}
      >
        <EvidenceCard title="Quality summary" copy="A compact read on margins, profitability, leverage, growth, and share-count direction.">
          {error && !financials.length ? (
            <ResearchBriefStateBlock kind="error" kicker="Business quality" title="Unable to load quality summary" message={error} />
          ) : loading && !financials.length ? (
            <ResearchBriefStateBlock
              kind="loading"
              kicker="Business quality"
              title="Loading annual quality read"
              message="Preparing the latest persisted profitability, leverage, and growth view from annual filings."
            />
          ) : financials.length ? (
            <FinancialQualitySummary financials={financials} />
          ) : (
            <ResearchBriefStateBlock
              kind="empty"
              kicker="Business quality"
              title="No annual quality history yet"
              message="This summary appears after the cache includes enough annual filings to compare profitability and growth cleanly."
            />
          )}
        </EvidenceCard>

        <EvidenceCard title="Margin trends" copy="Gross, operating, net, and free-cash-flow margin direction from cached filings.">
          {error && !financials.length ? (
            <ResearchBriefStateBlock kind="error" kicker="Business quality" title="Unable to load margin trends" message={error} />
          ) : loading && !financials.length ? (
            <ResearchBriefStateBlock
              kind="loading"
              kicker="Business quality"
              title="Loading margin trends"
              message="Building the persisted margin history used to judge whether operating quality is improving or degrading."
            />
          ) : financials.length ? (
            <MarginTrendChart financials={financials} />
          ) : (
            <ResearchBriefStateBlock
              kind="empty"
              kicker="Business quality"
              title="No margin history yet"
              message="Margin trend charts appear once multiple comparable filing periods are cached for the company."
            />
          )}
        </EvidenceCard>

        <EvidenceCard title="Cash flow bridge" copy="How operating cash flow turns into free cash flow and how much room capital allocation still has.">
          {error && !financials.length ? (
            <ResearchBriefStateBlock kind="error" kicker="Business quality" title="Unable to load cash flow bridge" message={error} />
          ) : loading && !financials.length ? (
            <ResearchBriefStateBlock
              kind="loading"
              kicker="Business quality"
              title="Loading cash flow bridge"
              message="Preparing the persisted cash flow waterfall used to separate accounting noise from cash-generation strength."
            />
          ) : financials.length ? (
            <CashFlowWaterfallChart financials={financials} />
          ) : (
            <ResearchBriefStateBlock
              kind="empty"
              kicker="Business quality"
              title="No cash flow bridge yet"
              message="The bridge populates when cached filings include operating cash flow, capex, and capital allocation inputs."
            />
          )}
        </EvidenceCard>
      </ResearchBriefSection>

      <ResearchBriefSection
        id="capital-risk"
        title="Capital & risk"
        question="Is the equity claim being protected, diluted, or put at risk?"
        summary={capitalRiskNarrative}
        cues={[
          {
            label: "Equity claim risk pack",
            asOf: briefData.brief?.capital_and_risk.as_of,
            lastRefreshedAt: briefData.brief?.capital_and_risk.last_refreshed_at,
            provenance: briefData.brief?.capital_and_risk.provenance,
            sourceMix: briefData.brief?.capital_and_risk.source_mix,
            confidenceFlags: briefData.brief?.capital_and_risk.confidence_flags,
          },
          {
            label: "Capital structure",
            asOf: briefData.capitalStructure.data?.as_of,
            lastRefreshedAt: briefData.capitalStructure.data?.last_refreshed_at,
            provenance: briefData.capitalStructure.data?.provenance,
            sourceMix: briefData.capitalStructure.data?.source_mix,
            confidenceFlags: briefData.capitalStructure.data?.confidence_flags,
          },
          {
            label: "Governance and stake signals",
            lastChecked: pageCompany?.last_checked_filings,
          },
        ]}
        links={capitalRiskLinks}
        expanded={expandedSections["capital-risk"] ?? true}
        onToggle={() => toggleSection("capital-risk")}
      >
        <EvidenceCard
          title="Equity claim risk pack summary"
          copy="A compact underwriting read on dilution, financing dependency, debt pressure, and reporting-control risk pulled from SEC-derived evidence."
        >
          {equityClaimRiskSummary ? (
            <div className="workspace-card-stack">
              <div className="workspace-card-row">
                <div className="workspace-pill-row">
                  <span className={`pill tone-${toneForRiskLevel(equityClaimRiskSummary.overall_risk_level)}`}>
                    Overall {titleCase(equityClaimRiskSummary.overall_risk_level)}
                  </span>
                  <span className={`pill tone-${toneForRiskLevel(equityClaimRiskSummary.dilution_risk_level)}`}>
                    Dilution {titleCase(equityClaimRiskSummary.dilution_risk_level)}
                  </span>
                  <span className={`pill tone-${toneForRiskLevel(equityClaimRiskSummary.financing_risk_level)}`}>
                    Financing {titleCase(equityClaimRiskSummary.financing_risk_level)}
                  </span>
                  <span className={`pill tone-${toneForRiskLevel(equityClaimRiskSummary.reporting_risk_level)}`}>
                    Reporting {titleCase(equityClaimRiskSummary.reporting_risk_level)}
                  </span>
                </div>
                <div className="text-muted">
                  {equityClaimRiskSummary.latest_period_end ? formatDate(equityClaimRiskSummary.latest_period_end) : "Latest period pending"}
                </div>
              </div>
              <div className="workspace-card-title">{equityClaimRiskSummary.headline || "Risk summary is available once the capital-and-risk pack finishes building."}</div>
              <div className="text-muted workspace-card-copy">
                Net dilution {formatPercent(equityClaimRiskSummary.net_dilution_ratio)} · SBC / revenue {formatPercent(equityClaimRiskSummary.sbc_to_revenue)} · Shelf remaining {formatCompactCurrency(equityClaimRiskSummary.shelf_capacity_remaining)} · Debt due in 24 months {formatCompactCurrency(equityClaimRiskSummary.debt_due_next_twenty_four_months)}
              </div>
              {equityClaimRiskSummary.key_points.length ? (
                <div className="workspace-card-stack">
                  {equityClaimRiskSummary.key_points.slice(0, 4).map((point) => (
                    <div key={point} className="text-muted workspace-card-copy">
                      {point}
                    </div>
                  ))}
                </div>
              ) : null}
              <div>
                <Link href={`/company/${encodeURIComponent(ticker)}/capital-markets`} className="workspace-card-link">
                  Open the full Equity Claim Risk Pack
                </Link>
              </div>
            </div>
          ) : (
            <ResearchBriefStateBlock
              kind={briefData.loading ? "loading" : "empty"}
              kicker="Capital & risk"
              title={briefData.loading ? "Loading equity claim risk summary" : "No equity claim risk summary yet"}
              message={
                briefData.loading
                  ? "Preparing the compact underwriting summary from share-count, financing, debt, and reporting-control signals."
                  : "This summary appears once the derived Equity Claim Risk Pack is available for the selected company."
              }
            />
          )}
        </EvidenceCard>

        <EvidenceCard
          title="Capital structure intelligence"
          copy="Debt ladders, lease schedules, payout mix, and dilution bridges pulled from persisted SEC extraction rather than route-time recomputation."
          className="is-wide"
        >
          {briefData.capitalStructure.error && !briefData.capitalStructure.data ? (
            <ResearchBriefStateBlock
              kind="error"
              kicker="Capital & risk"
              title="Unable to load capital structure"
              message={briefData.capitalStructure.error}
            />
          ) : briefData.capitalStructure.loading && !briefData.capitalStructure.data ? (
            <ResearchBriefStateBlock
              kind="loading"
              kicker="Capital & risk"
              title="Loading capital structure"
              message="Preparing the persisted debt, lease, payout, and dilution intelligence for the brief."
            />
          ) : briefData.capitalStructure.data?.latest ? (
            <CapitalStructureIntelligencePanel
              ticker={ticker}
              reloadKey={reloadKey}
              initialPayload={briefData.capitalStructure.data}
            />
          ) : (
            <ResearchBriefStateBlock
              kind="empty"
              kicker="Capital & risk"
              title="No capital structure snapshot yet"
              message="This section fills in once persisted capital structure extraction is available for the selected company."
            />
          )}
        </EvidenceCard>

        <EvidenceCard title="Share dilution" copy="Share-count direction keeps the equity-claim read grounded in persisted filing history.">
          {error && !financials.length ? (
            <ResearchBriefStateBlock kind="error" kicker="Capital & risk" title="Unable to load dilution history" message={error} />
          ) : loading && !financials.length ? (
            <ResearchBriefStateBlock
              kind="loading"
              kicker="Capital & risk"
              title="Loading dilution history"
              message="Reading cached share-count history to determine whether the equity claim is being diluted or defended."
            />
          ) : financials.length ? (
            <ShareDilutionTrackerChart financials={financials} />
          ) : (
            <ResearchBriefStateBlock
              kind="empty"
              kicker="Capital & risk"
              title="No dilution history yet"
              message="This chart appears once cached filings include enough share-count history to calculate dilution over time."
            />
          )}
        </EvidenceCard>

        <EvidenceCard title="Control and ownership signals" copy="Governance, major-holder, insider, and institutional cues that can change the thesis even when the statements still look clean.">
          {briefData.capitalMarketsSummary.error &&
          !briefData.capitalMarketsSummary.data &&
          briefData.governanceSummary.error &&
          !briefData.governanceSummary.data &&
          briefData.ownershipSummary.error &&
          !briefData.ownershipSummary.data ? (
            <ResearchBriefStateBlock
              kind="error"
              kicker="Capital & risk"
              title="Unable to load control signals"
              message={
                briefData.capitalMarketsSummary.error ??
                briefData.governanceSummary.error ??
                briefData.ownershipSummary.error ??
                "Control and ownership signals are temporarily unavailable."
              }
            />
          ) : briefData.capitalMarketsSummary.loading &&
            !briefData.capitalMarketsSummary.data &&
            briefData.governanceSummary.loading &&
            !briefData.governanceSummary.data &&
            briefData.ownershipSummary.loading &&
            !briefData.ownershipSummary.data ? (
            <ResearchBriefStateBlock
              kind="loading"
              kicker="Capital & risk"
              title="Loading control signals"
              message="Bringing together persisted financing, proxy, and ownership-change context."
            />
          ) : capitalSignalRows.length ? (
            <div className="company-data-table-shell">
              <table className="company-data-table company-data-table-compact">
                <thead>
                  <tr>
                    <th>Signal</th>
                    <th>Current Read</th>
                    <th>Latest Dated Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {capitalSignalRows.map((row) => (
                    <tr key={row.signal}>
                      <td>{row.signal}</td>
                      <td>{row.currentRead}</td>
                      <td>{row.latestEvidence}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <ResearchBriefStateBlock
              kind="empty"
              kicker="Capital & risk"
              title="No control signals yet"
              message={
                foreignIssuerStyleFiling
                  ? "This table fills in as capital markets and ownership-change signals are cached. U.S. proxy coverage can remain limited for many 20-F and 40-F issuers."
                  : "This table fills in after capital markets, governance, or ownership-change signals are cached for the company."
              }
            />
          )}
        </EvidenceCard>
      </ResearchBriefSection>

      <ResearchBriefSection
        id="valuation"
        title="Valuation"
        question="How does the current price compare with peers and cached model ranges?"
        summary={valuationNarrative}
        cues={[
          {
            label: "Valuation models",
            asOf: briefData.models.data?.as_of,
            lastRefreshedAt: briefData.models.data?.last_refreshed_at,
            provenance: briefData.models.data?.provenance,
            sourceMix: briefData.models.data?.source_mix,
            confidenceFlags: briefData.models.data?.confidence_flags,
          },
          {
            label: "Peer comparison",
            asOf: briefData.peers.data?.as_of,
            lastRefreshedAt: briefData.peers.data?.last_refreshed_at,
            provenance: briefData.peers.data?.provenance,
            sourceMix: briefData.peers.data?.source_mix,
            confidenceFlags: briefData.peers.data?.confidence_flags,
          },
        ]}
        links={valuationLinks}
        expanded={expandedSections.valuation ?? true}
        onToggle={() => toggleSection("valuation")}
      >
        <EvidenceCard
          title="Valuation summary"
          copy="Use the default brief to see the cached underwriting conclusion, then jump into the full Models workspace when you need the full assumption tree."
          className="is-wide"
        >
          {briefData.models.error && !briefData.models.data ? (
            <ResearchBriefStateBlock kind="error" kicker="Valuation" title="Unable to load valuation summary" message={briefData.models.error} />
          ) : briefData.models.loading && !briefData.models.data ? (
            <ResearchBriefStateBlock
              kind="loading"
              kicker="Valuation"
              title="Loading valuation summary"
              message="Preparing the cached DCF, residual income, and diagnostic model outputs for the brief."
            />
          ) : briefData.models.data?.models.length ? (
            <InvestmentSummaryPanel
              ticker={ticker}
              models={briefData.models.data.models}
              financials={financials}
              priceHistory={priceHistory}
              strictOfficialMode={Boolean(briefData.models.data.company?.strict_official_mode ?? pageCompany?.strict_official_mode)}
            />
          ) : (
            <ResearchBriefStateBlock
              kind="empty"
              kicker="Valuation"
              title="No cached model outputs yet"
              message="Refresh the company to backfill persisted model outputs before using the brief as a valuation read."
            />
          )}
        </EvidenceCard>

        <EvidenceCard title="Peer comparison snapshot" copy="A compact relative view so the brief can answer whether current multiples look rich, cheap, or roughly in line before deeper peer work.">
          {briefData.peers.error && !briefData.peers.data ? (
            <ResearchBriefStateBlock kind="error" kicker="Valuation" title="Unable to load peer snapshot" message={briefData.peers.error} />
          ) : briefData.peers.loading && !briefData.peers.data ? (
            <ResearchBriefStateBlock
              kind="loading"
              kicker="Valuation"
              title="Loading peer snapshot"
              message="Preparing the persisted peer universe and comparison metrics for the brief."
            />
          ) : briefData.peers.data?.peers.length ? (
            <PeerComparisonSnapshot response={briefData.peers.data} />
          ) : (
            <ResearchBriefStateBlock
              kind="empty"
              kicker="Valuation"
              title="No peer snapshot yet"
              message="Peer comparison will appear after more cached companies are available in the comparison universe."
            />
          )}
        </EvidenceCard>
      </ResearchBriefSection>

      <ResearchBriefSection
        id="monitor"
        title="Monitor"
        question="What should I keep watching after I leave this page?"
        summary={monitorNarrative}
        cues={[
          {
            label: "Monitoring feed",
            asOf: briefData.activityOverview.data?.as_of,
            lastRefreshedAt: briefData.activityOverview.data?.last_refreshed_at,
            lastChecked: pageCompany?.last_checked,
            provenance: briefData.activityOverview.data?.provenance,
            sourceMix: briefData.activityOverview.data?.source_mix,
            confidenceFlags: briefData.activityOverview.data?.confidence_flags,
          },
        ]}
        links={monitorLinks}
        expanded={expandedSections.monitor ?? true}
        onToggle={() => toggleSection("monitor")}
      >
        <EvidenceCard title="Priority alerts" copy="The monitor starts with the highest-signal items the user is likely to revisit first.">
          {briefData.activityOverview.error && !briefData.activityOverview.data ? (
            <ResearchBriefStateBlock kind="error" kicker="Monitor" title="Unable to load alerts" message={briefData.activityOverview.error} />
          ) : briefData.activityOverview.loading && !briefData.activityOverview.data ? (
            <ResearchBriefStateBlock
              kind="loading"
              kicker="Monitor"
              title="Loading alert watchlist"
              message="Preparing the cached alert feed that powers the brief's monitor section."
            />
          ) : topAlerts.length ? (
            <div className="workspace-card-stack">
              {topAlerts.map((alert) => {
                const levelTone = toneForAlertLevel(alert.level);
                const sourceTone = toneForAlertSource(alert.source);

                return (
                  <AlertOrEntryCard
                    key={alert.id}
                    href={alert.href}
                    tone={levelTone}
                    topLeft={
                      <>
                        <span className={`pill tone-${levelTone}`}>{alert.level}</span>
                        <span className={`pill tone-${sourceTone}`}>{alert.source}</span>
                      </>
                    }
                    topRight={formatDate(alert.date)}
                    title={alert.title}
                    detail={alert.detail}
                  />
                );
              })}
            </div>
          ) : (
            <ResearchBriefStateBlock
              kind="empty"
              kicker="Monitor"
              title="No active alerts"
              message="The monitor will list high-priority cached alerts here when thresholds are triggered."
            />
          )}
        </EvidenceCard>

        <EvidenceCard title="Latest timeline" copy="Chronological recent activity keeps the monitor grounded in dated SEC evidence instead of a generic task list.">
          {briefData.activityOverview.error && !briefData.activityOverview.data ? (
            <ResearchBriefStateBlock kind="error" kicker="Monitor" title="Unable to load timeline" message={briefData.activityOverview.error} />
          ) : briefData.activityOverview.loading && !briefData.activityOverview.data ? (
            <ResearchBriefStateBlock
              kind="loading"
              kicker="Monitor"
              title="Loading SEC timeline"
              message="Preparing recent filing, governance, ownership, and insider events for the watchlist-style closeout."
            />
          ) : latestEntries.length ? (
            <div className="workspace-card-stack">
              {latestEntries.map((entry) => {
                const typeTone = toneForEntryType(entry.type);
                const badgeTone = toneForEntryBadge(entry.type, entry.badge);
                const cardTone = toneForEntryCard(entry);

                return (
                  <AlertOrEntryCard
                    key={entry.id}
                    href={entry.href}
                    tone={cardTone}
                    topLeft={
                      <>
                        <span className={`pill tone-${typeTone}`}>{formatFeedEntryType(entry.type)}</span>
                        <span className={`pill tone-${badgeTone}`}>{entry.badge}</span>
                      </>
                    }
                    topRight={formatDate(entry.date)}
                    title={entry.title}
                    detail={entry.detail}
                  />
                );
              })}
            </div>
          ) : (
            <ResearchBriefStateBlock
              kind="empty"
              kicker="Monitor"
              title="No timeline entries yet"
              message="Recent filing and ownership activity will populate here once the monitoring feed has dated SEC events to show."
            />
          )}
        </EvidenceCard>

        <EvidenceCard title="Monitor checklist" copy="The last step in the brief is explicit: what to re-check next, and why.">
          {monitorChecklist.length ? (
            <div className="research-brief-checklist-grid">
              {monitorChecklist.map((item) => (
                <div key={item.title} className={`research-brief-checklist-card tone-${item.tone}`}>
                  <div className="research-brief-checklist-title">{item.title}</div>
                  <div className="research-brief-checklist-detail">{item.detail}</div>
                </div>
              ))}
            </div>
          ) : (
            <ResearchBriefStateBlock
              kind="empty"
              kicker="Monitor"
              title="No next-step checklist yet"
              message="The monitor checklist appears once the brief has enough cached activity and freshness data to recommend the next review points."
            />
          )}
        </EvidenceCard>
      </ResearchBriefSection>
    </CompanyWorkspaceShell>
  );
}

function useResearchBriefData(
  ticker: string,
  reloadKey: string,
  initialBrief: CompanyResearchBriefResponse | null,
  overviewBootstrapLoading: boolean,
  warmupJobId: string | null
): ResearchBriefDataState {
  const [state, setState] = useState<ResearchBriefDataState>(() =>
    initialBrief ? mapBriefResponseToAsyncState(initialBrief) : INITIAL_RESEARCH_BRIEF_DATA_STATE
  );

  useEffect(() => {
    let cancelled = false;
    let timeoutId: number | null = null;
    let idleId: number | null = null;
    const idleWindow = window as Window & {
      requestIdleCallback?: (callback: () => void, options?: { timeout: number }) => number;
      cancelIdleCallback?: (handle: number) => void;
    };

    const loadBrief = async () => {
      try {
        const brief = await withPerformanceAuditSource(
          {
            pageRoute: "/company/[ticker]",
            scenario: "company_overview",
            source: "company-overview:research-brief",
          },
          () => getCompanyResearchBrief(ticker)
        );

        if (cancelled) {
          return;
        }

        setState(mapBriefResponseToAsyncState(brief));
      } catch (nextError) {
        if (cancelled) {
          return;
        }

        const message = nextError instanceof Error ? nextError.message : "Unable to load research brief";
        setState({
          ...INITIAL_RESEARCH_BRIEF_DATA_STATE,
          error: message,
          loading: false,
          activityOverview: { data: null, error: message, loading: false },
          changes: { data: null, error: message, loading: false },
          earningsSummary: { data: null, error: message, loading: false },
          capitalStructure: { data: null, error: message, loading: false },
          capitalMarketsSummary: { data: null, error: message, loading: false },
          governanceSummary: { data: null, error: message, loading: false },
          ownershipSummary: { data: null, error: message, loading: false },
          models: { data: null, error: message, loading: false },
          peers: { data: null, error: message, loading: false },
        });
      }
    };

    const scheduleBriefLoad = () => {
      const runLoad = () => {
        void loadBrief();
      };

      if (typeof idleWindow.requestIdleCallback === "function") {
        idleId = idleWindow.requestIdleCallback(runLoad, { timeout: 1200 });
        return;
      }

      timeoutId = window.setTimeout(runLoad, 0);
    };

    if (initialBrief) {
      setState(mapBriefResponseToAsyncState(initialBrief));

      if (initialBrief.build_state !== "ready" && !warmupJobId) {
        scheduleBriefLoad();
      }

      return () => {
        cancelled = true;
        if (timeoutId != null) {
          window.clearTimeout(timeoutId);
        }
        if (idleId != null && typeof idleWindow.cancelIdleCallback === "function") {
          idleWindow.cancelIdleCallback(idleId);
        }
      };
    }

    if (overviewBootstrapLoading || warmupJobId) {
      setState((current) => ({
        ...current,
        loading: true,
        error: null,
      }));
      return () => {
        cancelled = true;
        if (timeoutId != null) {
          window.clearTimeout(timeoutId);
        }
        if (idleId != null && typeof idleWindow.cancelIdleCallback === "function") {
          idleWindow.cancelIdleCallback(idleId);
        }
      };
    }

    setState((current) => ({
      ...current,
      loading: true,
      error: null,
    }));
    scheduleBriefLoad();

    return () => {
      cancelled = true;
      if (timeoutId != null) {
        window.clearTimeout(timeoutId);
      }
      if (idleId != null && typeof idleWindow.cancelIdleCallback === "function") {
        idleWindow.cancelIdleCallback(idleId);
      }
    };
  }, [initialBrief, overviewBootstrapLoading, reloadKey, ticker, warmupJobId]);

  return state;
}

function ResearchBriefWarmupPanel({
  buildState,
  buildStatus,
  sectionStatuses,
  summaryCards,
  filingTimeline,
  refreshState,
}: {
  buildState: ResearchBriefBuildState;
  buildStatus: string | null;
  sectionStatuses: ResearchBriefSectionStatusPayload[];
  summaryCards: ResearchBriefSummaryCardPayload[];
  filingTimeline: FilingTimelineItemPayload[];
  refreshState: RefreshState | null;
}) {
  if (buildState === "ready" && !summaryCards.length && !filingTimeline.length) {
    return null;
  }

  return (
    <Panel
      title={buildState === "ready" ? "Brief status" : buildState === "partial" ? "Brief warming" : "Cold start bootstrap"}
      subtitle={buildStatus ?? "Preparing the first meaningful screen while the full brief continues to hydrate."}
      variant="subtle"
      className={`research-brief-warmup-panel research-brief-warmup-panel-${buildState}`}
    >
      <div className="research-brief-warmup-stack">
        <div className="research-brief-warmup-topline">
          <span className={`pill research-brief-build-pill research-brief-build-pill-${buildState}`}>{formatResearchBriefBuildState(buildState)}</span>
          {refreshState?.job_id ? <span className="pill">Refresh queued</span> : null}
          {refreshState?.reason ? <span className="pill">{titleCase(refreshState.reason)}</span> : null}
        </div>

        {summaryCards.length ? (
          <div className="research-brief-summary-card-grid">
            {summaryCards.map((card) => (
              <div key={card.key} className="research-brief-summary-card">
                <div className="research-brief-summary-card-title">{card.title}</div>
                <div className="research-brief-summary-card-value">{card.value}</div>
                {card.detail ? <div className="research-brief-summary-card-detail">{card.detail}</div> : null}
              </div>
            ))}
          </div>
        ) : null}

        <div className="research-brief-warmup-grid">
          <div className="research-brief-warmup-section-list">
            <div className="research-brief-warmup-heading">Section build order</div>
            <div className="research-brief-warmup-status-grid">
              {sectionStatuses.map((statusItem) => (
                <div key={statusItem.id} className={`research-brief-warmup-status-card state-${statusItem.state}`}>
                  <div className="research-brief-warmup-status-topline">
                    <span className="research-brief-warmup-status-title">{statusItem.title}</span>
                    <span className={`pill research-brief-status-pill state-${statusItem.state}`}>{formatResearchBriefBuildState(statusItem.state)}</span>
                  </div>
                  {statusItem.detail ? <div className="research-brief-warmup-status-detail">{statusItem.detail}</div> : null}
                </div>
              ))}
            </div>
          </div>

          <div className="research-brief-warmup-section-list">
            <div className="research-brief-warmup-heading">Latest filing timeline</div>
            {filingTimeline.length ? (
              <div className="research-brief-warmup-timeline">
                {filingTimeline.slice(0, 5).map((item) => (
                  <div key={`${item.accession ?? item.form}-${item.date ?? "pending"}`} className="research-brief-warmup-timeline-item">
                    <div className="research-brief-warmup-timeline-topline">
                      <span className="research-brief-warmup-timeline-form">{item.form}</span>
                      <span className="text-muted">{item.date ? formatDate(item.date) : "Pending"}</span>
                    </div>
                    <div className="research-brief-warmup-timeline-detail">{item.description}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="research-brief-warmup-empty">Recent filings will appear here once the first SEC timeline is resolved.</div>
            )}
          </div>
        </div>
      </div>
    </Panel>
  );
}

function useActiveBriefSection(sectionIds: string[]): string {
  const [activeSectionId, setActiveSectionId] = useState(sectionIds[0] ?? "snapshot");

  useEffect(() => {
    const elements = sectionIds
      .map((sectionId) => document.getElementById(sectionId))
      .filter((element): element is HTMLElement => Boolean(element));

    if (!elements.length) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0];

        if (visible?.target instanceof HTMLElement) {
          setActiveSectionId(visible.target.id);
        }
      },
      {
        rootMargin: "-28% 0px -56% 0px",
        threshold: [0.05, 0.2, 0.45],
      }
    );

    elements.forEach((element) => observer.observe(element));

    return () => {
      observer.disconnect();
    };
  }, [sectionIds]);

  return activeSectionId;
}

function useResearchBriefSectionPreferences(ticker: string): {
  expandedSections: Record<string, boolean>;
  toggleSection: (sectionId: string) => void;
} {
  const storageKey = `${RESEARCH_BRIEF_SECTION_STORAGE_PREFIX}:${ticker}`;
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>(() => createDefaultResearchBriefSectionState());
  const [hasLoadedPreferences, setHasLoadedPreferences] = useState(false);
  const canPersistPreferencesRef = useRef(true);

  useEffect(() => {
    const defaultState = createDefaultResearchBriefSectionState();

    try {
      const rawState = window.localStorage.getItem(storageKey);

      if (!rawState) {
        setExpandedSections(defaultState);
        setHasLoadedPreferences(true);
        return;
      }

      const parsedState = JSON.parse(rawState) as unknown;
      setExpandedSections(mergeResearchBriefSectionState(defaultState, parsedState));
    } catch {
      setExpandedSections(defaultState);
    } finally {
      setHasLoadedPreferences(true);
    }
  }, [storageKey]);

  useEffect(() => {
    if (!hasLoadedPreferences) {
      return;
    }

    if (!canPersistPreferencesRef.current) {
      return;
    }

    if (!persistResearchBriefSectionState(storageKey, expandedSections)) {
      canPersistPreferencesRef.current = false;
    }
  }, [expandedSections, hasLoadedPreferences, storageKey]);

  function toggleSection(sectionId: string) {
    setExpandedSections((current) => ({
      ...current,
      [sectionId]: !current[sectionId],
    }));
  }

  return { expandedSections, toggleSection };
}

function persistResearchBriefSectionState(storageKey: string, expandedSections: Record<string, boolean>): boolean {
  try {
    const normalizedState = mergeResearchBriefSectionState(createDefaultResearchBriefSectionState(), expandedSections);
    window.localStorage.setItem(storageKey, JSON.stringify(normalizedState));
    return true;
  } catch {
    return false;
  }
}

function ResearchBriefSection({
  id,
  title,
  question,
  summary,
  cues,
  links,
  expanded,
  onToggle,
  children,
}: {
  id: string;
  title: string;
  question: string;
  summary?: string | null;
  cues: ResearchBriefCue[];
  links: SectionLink[];
  expanded: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  const contentId = `${id}-content`;

  return (
    <section id={id} data-brief-section className="research-brief-anchor">
      <Panel
        title={title}
        subtitle={question}
        aside={<ResearchBriefSectionControls links={links} expanded={expanded} title={title} contentId={contentId} onToggle={onToggle} />}
        variant="subtle"
        bodyId={contentId}
        bodyHidden={!expanded}
        className="research-brief-section-panel"
      >
        <div className="research-brief-section-stack">
          {summary || cues.length ? (
            <div className="research-brief-section-intro">
              {summary ? <p className="research-brief-section-summary">{summary}</p> : null}
              <ResearchBriefFreshness cues={cues} />
            </div>
          ) : null}
          <div className="research-brief-evidence-grid">{children}</div>
        </div>
      </Panel>
    </section>
  );
}

function ResearchBriefHeroSummary({
  summary,
  metrics,
  metaItems,
  fallbackLabels,
  loading = false,
  loadingMessage = null,
}: {
  summary: string;
  metrics: Array<{ label: string; value: string | null }>;
  metaItems: Array<string | null>;
  fallbackLabels: string[];
  loading?: boolean;
  loadingMessage?: string | null;
}) {
  const visibleMetaItems = metaItems.filter((item): item is string => Boolean(item));

  return (
    <div className="research-brief-hero">
      {loadingMessage ? (
        <div className="research-brief-hero-loading" role="status" aria-live="polite">
          {loadingMessage}
        </div>
      ) : null}
      <div className="research-brief-hero-main">
        <div className="research-brief-hero-copy">
          <p className="research-brief-hero-summary">{summary}</p>
          {visibleMetaItems.length ? (
            <div className="research-brief-hero-meta" aria-label="Brief metadata">
              {visibleMetaItems.map((item) => (
                <span key={item} className="research-brief-hero-meta-item">
                  {item}
                </span>
              ))}
            </div>
          ) : null}
          {fallbackLabels.length ? (
            <div className="research-brief-hero-note">
              Price history and market profile context includes a labeled commercial fallback from {fallbackLabels.join(", ")}. Core fundamentals remain sourced from official filings and public datasets.
            </div>
          ) : null}
        </div>

        <div className="research-brief-hero-metrics">
          {metrics.map((item, index) => (
            <div key={item.label} className={`research-brief-hero-metric${index < 2 ? " is-primary" : " is-secondary"}`}>
              <div className="research-brief-hero-metric-label">{item.label}</div>
              <div className="research-brief-hero-metric-value">
                {loading ? (
                  <span aria-hidden="true" className={`workspace-skeleton research-brief-hero-metric-skeleton skeleton-${index % 4}`} />
                ) : (
                  item.value ?? "\u2014"
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function buildInitialCompanyLoadMessage(
  initialCompanyLoad: boolean,
  activeRefreshEntry: ConsoleEntry | null,
  buildState: ResearchBriefBuildState,
  buildStatus: string | null,
): string | null {
  if (!initialCompanyLoad) {
    return buildState !== "ready" ? buildStatus : null;
  }

  if (activeRefreshEntry?.status === "queued") {
    const jobsAhead = activeRefreshEntry.jobs_ahead;
    if (typeof jobsAhead === "number") {
      if (jobsAhead <= 0) {
        return "No cached company snapshot exists yet. Your first overview is next in the refresh queue.";
      }

      const plural = jobsAhead === 1 ? "" : "es";
      return `No cached company snapshot exists yet. Queued behind ${jobsAhead.toLocaleString()} other refresh${plural} before the first overview starts.`;
    }

    return "No cached company snapshot exists yet. The first overview is queued and will start shortly.";
  }

  if (activeRefreshEntry?.status === "running") {
    return "No cached company snapshot exists yet. Building the first overview now.";
  }

  return "No cached company snapshot exists yet. Fetching the first overview now.";
}

function buildRefreshQueueDetailLine(activeRefreshEntry: ConsoleEntry | null): string | null {
  if (activeRefreshEntry?.status === "queued") {
    const jobsAhead = activeRefreshEntry.jobs_ahead;
    if (typeof jobsAhead === "number") {
      if (jobsAhead <= 0) {
        return "Refresh queue: next in line for the worker.";
      }

      const plural = jobsAhead === 1 ? "" : "es";
      return `Refresh queue: ${jobsAhead.toLocaleString()} refresh${plural} ahead before this company snapshot starts.`;
    }

    return "Refresh queue: waiting for the worker to claim this company refresh.";
  }

  if (activeRefreshEntry?.status === "running") {
    return "Refresh queue: worker claimed this company and the first snapshot is building now.";
  }

  return null;
}

function ResearchBriefSectionNav({ activeSectionId }: { activeSectionId: string }) {
  return (
    <nav className="research-brief-nav" aria-label="Research brief sections">
      {BRIEF_SECTIONS.map((section) => (
        <a
          key={section.id}
          href={`#${section.id}`}
          className={`research-brief-nav-link${activeSectionId === section.id ? " is-active" : ""}`}
        >
          {section.title}
        </a>
      ))}
    </nav>
  );
}

function ResearchBriefSectionControls({
  links,
  expanded,
  title,
  contentId,
  onToggle,
}: {
  links: SectionLink[];
  expanded: boolean;
  title: string;
  contentId: string;
  onToggle: () => void;
}) {
  return (
    <div className="research-brief-section-controls">
      <SectionLinks links={links} />
      <button
        type="button"
        className="research-brief-section-toggle"
        aria-controls={contentId}
        aria-label={`${expanded ? "Collapse" : "Expand"} ${title}`}
        data-expanded={expanded ? "true" : "false"}
        onClick={onToggle}
      >
        <span>{expanded ? "Collapse" : "Expand"}</span>
        <span className="research-brief-section-toggle-chevron" aria-hidden="true" />
      </button>
    </div>
  );
}

function SectionLinks({ links }: { links: SectionLink[] }) {
  return (
    <div className="research-brief-section-links">
      {links.map((link) => (
        <Link key={link.href} href={link.href} className="research-brief-section-link">
          {link.label}
        </Link>
      ))}
    </div>
  );
}

function ResearchBriefFreshness({ cues }: { cues: ResearchBriefCue[] }) {
  const visibleCues = cues.filter(
    (cue) => cue.asOf || cue.lastRefreshedAt || cue.lastChecked || cue.provenance?.length || cue.sourceMix || cue.confidenceFlags?.length
  );

  if (!visibleCues.length) {
    return null;
  }

  return (
    <div className="research-brief-freshness-grid">
      {visibleCues.map((cue) => {
        const sourceSummary = formatEvidenceSourceSummary(cue.sourceMix, cue.provenance);
        const fallbackLabel = formatEvidenceFallbackLabel(cue.provenance, cue.sourceMix);
        const confidenceFlags = (cue.confidenceFlags ?? []).slice(0, 2);

        return (
          <div key={cue.label} className="research-brief-freshness-card">
            <div className="research-brief-freshness-head">
              <div className="research-brief-freshness-title">{cue.label}</div>
              {confidenceFlags.length ? <div className="research-brief-freshness-flags">Flags: {confidenceFlags.map(humanizeToken).join(", ")}</div> : null}
            </div>
            <EvidenceMetaBlock
              items={[
                { label: "Source", value: sourceSummary, emphasized: true },
                { label: "As of", value: cue.asOf ? formatDate(cue.asOf) : "Pending" },
                { label: "Freshness", value: formatBriefEvidenceFreshness(cue.lastRefreshedAt, cue.lastChecked) },
                { label: "Fallback label", value: fallbackLabel },
              ]}
            />
            {cue.provenance?.length ? (
              <div className="research-brief-freshness-note">
                {cue.provenance.length.toLocaleString()} registry source{cue.provenance.length === 1 ? "" : "s"} backing this section.
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function EvidenceCard({
  title,
  copy,
  className,
  children,
}: {
  title: string;
  copy: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={`research-brief-evidence-card${className ? ` ${className}` : ""}`}>
      <div className="research-brief-evidence-head">
        <h3 className="research-brief-evidence-title">{title}</h3>
        <p className="research-brief-evidence-copy">{copy}</p>
      </div>
      {children}
    </div>
  );
}

function ResearchBriefStateBlock({
  kind,
  kicker,
  title,
  message,
  minHeight = 220,
}: {
  kind: "loading" | "empty" | "error";
  kicker: string;
  title: string;
  message: string;
  minHeight?: number;
}) {
  return (
    <div className={`research-brief-state research-brief-state-${kind}${minHeight <= 180 ? " is-compact" : ""}`}>
      <div className="grid-empty-kicker">{kicker}</div>
      <div className="grid-empty-title">{title}</div>
      <div className="grid-empty-copy">{message}</div>
    </div>
  );
}

function PeerComparisonSnapshot({ response }: { response: CompanyPeersResponse }) {
  const rows = response.peers.slice(0, 4);

  return (
    <div className="research-brief-table-stack">
      <div className="company-data-table-shell">
        <table className="company-data-table company-data-table-compact">
          <thead>
            <tr>
              <th>Company</th>
              <th className="is-numeric">Price</th>
              <th className="is-numeric">P/E</th>
              <th className="is-numeric">EV / EBIT</th>
              <th className="is-numeric">Revenue Growth</th>
              <th className="is-numeric">ROIC</th>
              <th className="is-numeric">Fair Value Gap</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((peer) => (
              <tr key={peer.ticker} className={peer.is_focus ? "research-brief-table-row-focus" : undefined}>
                <td>
                  <div className="research-brief-peer-cell">
                    <strong>{peer.ticker}</strong>
                    <span className="text-muted">{peer.name}</span>
                  </div>
                </td>
                <td className="is-numeric">{formatCompactCurrency(peer.latest_price)}</td>
                <td className="is-numeric">{formatMultiple(peer.pe)}</td>
                <td className="is-numeric">{formatMultiple(peer.ev_to_ebit)}</td>
                <td className="is-numeric">{formatPercent(peer.revenue_growth)}</td>
                <td className="is-numeric">{formatPercent(peer.roic)}</td>
                <td className="is-numeric">{formatPercent(peer.fair_value_gap)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {response.notes.fair_value_gap ? <div className="text-muted workspace-note-line">{response.notes.fair_value_gap}</div> : null}
      {response.notes.ev_to_ebit ? <div className="text-muted workspace-note-line">{response.notes.ev_to_ebit}</div> : null}
    </div>
  );
}

function AlertOrEntryCard({
  href,
  tone,
  topLeft,
  topRight,
  title,
  detail,
}: {
  href: string | null;
  tone: SemanticTone;
  topLeft: ReactNode;
  topRight: string;
  title: string;
  detail: string;
}) {
  const cardClassName = `filing-link-card company-pulse-card tone-${tone}`;
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
        className={`${cardClassName} research-brief-linked-card`}
      >
        {content}
      </a>
    );
  }

  return (
    <div className={`${cardClassName} research-brief-linked-card`}>
      {content}
    </div>
  );
}

function createDefaultResearchBriefSectionState(): Record<string, boolean> {
  return Object.fromEntries(BRIEF_SECTION_IDS.map((sectionId) => [sectionId, true]));
}

function mergeResearchBriefSectionState(
  defaultState: Record<string, boolean>,
  parsedState: unknown
): Record<string, boolean> {
  if (!parsedState || typeof parsedState !== "object") {
    return defaultState;
  }

  const nextState = { ...defaultState };

  for (const sectionId of BRIEF_SECTION_IDS) {
    const value = (parsedState as Record<string, unknown>)[sectionId];
    if (typeof value === "boolean") {
      nextState[sectionId] = value;
    }
  }

  return nextState;
}

function resolveAsyncState<T>(
  previous: AsyncState<T>,
  result: PromiseSettledResult<T>,
  fallback: string
): AsyncState<T> {
  if (result.status === "fulfilled") {
    return {
      data: result.value,
      error: null,
      loading: false,
    };
  }

  return {
    data: previous.data,
    error: result.reason instanceof Error ? result.reason.message : fallback,
    loading: false,
  };
}

function buildSnapshotNarrative({
  company,
  latestFinancial,
  topSegment,
  alertCount,
  buildState,
  filingTimeline,
  sourceMix,
  provenance,
  loading,
}: {
  company: BriefCompany | null;
  latestFinancial: FinancialPayload | null;
  topSegment: FinancialPayload["segment_breakdown"][number] | null;
  alertCount: number;
  buildState: ResearchBriefBuildState;
  filingTimeline: FilingTimelineItemPayload[];
  sourceMix: SourceMixPayload | null | undefined;
  provenance: ProvenanceEntryPayload[] | null | undefined;
  loading: boolean;
}): string {
  if (!latestFinancial) {
    if (company && filingTimeline.length) {
      const latestFiling = filingTimeline[0];
      return `${company.name ?? company.ticker ?? "This company"} is in ${buildState === "building" ? "cold-start bootstrap" : "partial brief"} mode. The latest visible SEC filing is ${latestFiling.form} dated ${formatDate(latestFiling.date)} and the rest of the specialist sections will fill in as cached datasets finish warming.`;
    }
    return loading
      ? "The brief is loading the latest persisted filing, segment mix, and price context before the deeper sections render."
      : "The default brief is waiting for persisted financials and segment disclosures before it can frame the company at a glance.";
  }

  const fallbackLabels = resolveCommercialFallbackLabels(provenance, sourceMix);
  const topSegmentSummary =
    topSegment && topSegment.share_of_revenue != null
      ? `${topSegment.segment_name} contributes ${formatPercent(topSegment.share_of_revenue)} of reported revenue`
      : topSegment?.segment_name
        ? `${topSegment.segment_name} is the most visible reported segment`
        : "segment concentration is still limited in the cached disclosures";
  const fallbackSummary = fallbackLabels.length
    ? `Price context is coming through a labeled ${fallbackLabels.join(", ")} fallback while fundamentals remain official-source-first.`
    : "Both the operating history and its freshness cues remain anchored in the persisted SEC-first workspace.";

  return `${company?.name ?? company?.ticker ?? "This company"} last reported ${formatCompactCurrency(latestFinancial.revenue)} of revenue and ${formatCompactCurrency(latestFinancial.free_cash_flow)} of free cash flow; ${topSegmentSummary}; ${alertCount.toLocaleString()} current alert${alertCount === 1 ? " is" : "s are"} already on the monitor. ${fallbackSummary}`;
}

function buildWhatChangedNarrative({
  changes,
  earningsSummary,
  activityOverview,
  loading,
}: {
  changes: CompanyChangesSinceLastFilingResponse | null;
  earningsSummary: CompanyEarningsSummaryResponse | null;
  activityOverview: CompanyActivityOverviewResponse | null;
  loading: boolean;
}): string {
  if (!changes && !earningsSummary && !activityOverview) {
    return loading
      ? "The brief is comparing the latest filing, earnings summary, and activity feed before it answers what changed."
      : "This section will summarize filing deltas, earnings capture, and dated SEC activity once the persisted change surfaces are available.";
  }

  const metricDeltas = changes?.summary.metric_delta_count ?? 0;
  const highSignalChanges = changes?.summary.high_signal_change_count ?? 0;
  const commentLetters = changes?.summary.comment_letter_count ?? 0;
  const latestRevenue = earningsSummary?.summary.latest_revenue;
  const latestEps = earningsSummary?.summary.latest_diluted_eps;
  const highAlerts = activityOverview?.summary.high ?? 0;

  return `The latest comparable filing surfaced ${highSignalChanges.toLocaleString()} curated high-signal change${highSignalChanges === 1 ? "" : "s"} and ${commentLetters.toLocaleString()} comment-letter update${commentLetters === 1 ? "" : "s"}; the full comparison still retains ${metricDeltas.toLocaleString()} raw metric delta${metricDeltas === 1 ? "" : "s"}; the latest earnings capture reads ${formatCompactCurrency(latestRevenue)} of revenue and ${latestEps != null ? latestEps.toFixed(2) : "—"} diluted EPS; the activity feed is currently carrying ${highAlerts.toLocaleString()} high-priority alert${highAlerts === 1 ? "" : "s"}.`;
}

function buildBusinessQualityNarrative({
  latestFinancial,
  previousAnnual,
  loading,
}: {
  latestFinancial: FinancialPayload | null;
  previousAnnual: FinancialPayload | null;
  loading: boolean;
}): string {
  if (!latestFinancial) {
    return loading
      ? "The brief is loading the latest quality metrics before it judges whether the business is strengthening or deteriorating."
      : "This section will evaluate margins, cash generation, and balance-sheet quality once persisted annual statement history is available.";
  }

  const revenueGrowth = growthRate(latestFinancial.revenue, previousAnnual?.revenue ?? null);
  const operatingMargin = safeDivide(latestFinancial.operating_income, latestFinancial.revenue);
  const fcfMargin = safeDivide(latestFinancial.free_cash_flow, latestFinancial.revenue);
  const debtToAssets = safeDivide(latestFinancial.total_liabilities, latestFinancial.total_assets);

  return `Revenue is ${revenueGrowth != null ? `${revenueGrowth >= 0 ? "up" : "down"} ${formatPercent(Math.abs(revenueGrowth))} year over year` : "not yet comparable year over year"}, operating margin sits at ${formatPercent(operatingMargin)}, free-cash-flow margin at ${formatPercent(fcfMargin)}, and debt-to-assets at ${formatPercent(debtToAssets)}. The goal here is to decide whether improvement is real, fragile, or mostly accounting noise.`;
}

function buildCapitalRiskNarrative({
  capitalStructure,
  capitalMarketsSummary,
  governanceSummary,
  ownershipSummary,
  equityClaimRiskSummary,
  isForeignIssuerLike,
  loading,
}: {
  capitalStructure: CompanyCapitalStructureResponse | null;
  capitalMarketsSummary: CompanyCapitalMarketsSummaryResponse | null;
  governanceSummary: CompanyGovernanceSummaryResponse | null;
  ownershipSummary: CompanyBeneficialOwnershipSummaryResponse | null;
  equityClaimRiskSummary: EquityClaimRiskSummaryPayload | null;
  isForeignIssuerLike: boolean;
  loading: boolean;
}): string {
  const latest = capitalStructure?.latest ?? null;

  if (!latest && !capitalMarketsSummary && !governanceSummary && !ownershipSummary) {
    return loading
      ? "The brief is loading persisted debt, governance, and ownership signals before it judges whether the equity claim is protected."
      : "This section will summarize debt burden, dilution risk, governance coverage, and ownership pressure once the persisted control signals are available.";
  }

  const debtDue = latest?.summary.debt_due_next_twelve_months;
  const netDilution = latest?.summary.net_dilution_ratio;
  const proxyCount = governanceSummary?.summary.total_filings ?? 0;
  const stakeChangeCount = ownershipSummary?.summary.total_filings ?? 0;
  const registrationFilings = capitalMarketsSummary?.summary.registration_filings ?? 0;
  const governanceRead =
    isForeignIssuerLike && proxyCount === 0
      ? "governance coverage is limited because many 20-F and 40-F issuers do not file U.S. proxy materials"
      : `governance coverage spans ${proxyCount.toLocaleString()} proxy filing${proxyCount === 1 ? "" : "s"}`;

  if (equityClaimRiskSummary) {
    return `${equityClaimRiskSummary.headline} Net dilution currently reads ${formatPercent(equityClaimRiskSummary.net_dilution_ratio)}, remaining shelf capacity is ${formatCompactCurrency(equityClaimRiskSummary.shelf_capacity_remaining)}, debt due inside 24 months is ${formatCompactCurrency(equityClaimRiskSummary.debt_due_next_twenty_four_months)}, and internal-control flags total ${equityClaimRiskSummary.internal_control_flag_count.toLocaleString()}. ${governanceRead}, stake-change monitoring covers ${stakeChangeCount.toLocaleString()} major-holder filing${stakeChangeCount === 1 ? "" : "s"}, and registration activity counts ${registrationFilings.toLocaleString()} financing filing${registrationFilings === 1 ? "" : "s"}.`;
  }

  return `Near-term debt due is ${formatCompactCurrency(debtDue)}, net dilution is ${formatPercent(netDilution)}, ${governanceRead}, stake-change monitoring covers ${stakeChangeCount.toLocaleString()} major-holder filing${stakeChangeCount === 1 ? "" : "s"}, and registration activity counts ${registrationFilings.toLocaleString()} financing filing${registrationFilings === 1 ? "" : "s"} so the brief can answer whether capital allocation is supportive or leaking value.`;
}

function toneForRiskLevel(level: "none" | "low" | "medium" | "high"): SemanticTone {
  switch (level) {
    case "high":
      return "red";
    case "medium":
      return "gold";
    case "low":
      return "green";
    default:
      return "cyan";
  }
}

function buildValuationNarrative({
  models,
  peers,
  priceHistory,
  loading,
}: {
  models: CompanyModelsResponse["models"];
  peers: CompanyPeersResponse["peers"];
  priceHistory: { date: string; close: number | null }[];
  loading: boolean;
}): string {
  if (!models.length && !peers.length) {
    return loading
      ? "The brief is loading cached models and the persisted peer universe before it answers the valuation question."
      : "This section will compare cached model ranges with peer multiples once the valuation workspace has persisted outputs for the company.";
  }

  const latestPrice = priceHistory.at(-1)?.close ?? peers.find((peer) => peer.is_focus)?.latest_price ?? null;
  const dcfFairValue = extractModelNumber(models, "dcf", ["fair_value_per_share"]);
  const residualValue = extractModelNumber(models, "residual_income", ["intrinsic_value", "intrinsic_value_per_share"]);
  const anchors = [dcfFairValue, residualValue].filter((value): value is number => value != null);
  const midpoint = anchors.length ? anchors.reduce((sum, value) => sum + value, 0) / anchors.length : null;
  const gap = midpoint != null && latestPrice != null && latestPrice > 0 ? (midpoint - latestPrice) / latestPrice : null;
  const focusPeer = peers.find((peer) => peer.is_focus) ?? null;
  const otherPeers = peers.filter((peer) => !peer.is_focus);
  const peerMedianPe = median(otherPeers.map((peer) => peer.pe));

  if (gap != null && focusPeer?.pe != null && peerMedianPe != null) {
    const direction = gap >= 0 ? "above" : "below";
    return `Cached model anchors put intrinsic value about ${formatPercent(Math.abs(gap))} ${direction} the latest price, while ${focusPeer.ticker} trades at ${formatMultiple(focusPeer.pe)} earnings versus a ${formatMultiple(peerMedianPe)} peer median. The brief's job here is to tell you whether underwriting still points to upside before you open the full model workbench.`;
  }

  if (midpoint != null && latestPrice != null) {
    return `The current valuation read is anchored on a cached midpoint of ${formatCompactCurrency(midpoint)} per share versus a latest price of ${formatCompactCurrency(latestPrice)}. Peer metrics are available below to pressure-test whether the market is already paying up for that quality.`;
  }

  return `Cached valuation outputs are partially available, so the brief uses the peer snapshot below to frame relative valuation while the fuller model range continues to warm.`;
}

function buildMonitorNarrative({
  activityOverview,
  refreshState,
  company,
  loading,
}: {
  activityOverview: CompanyActivityOverviewResponse | null;
  refreshState: RefreshState | null;
  company: BriefCompany | null;
  loading: boolean;
}): string {
  if (!activityOverview) {
    return loading
      ? "The brief is loading alerts, dated activity, and freshness cues before it closes with the monitor view."
      : "This section will tell you what to re-check next once the cached monitoring feed has alerts and dated SEC activity for the company.";
  }

  const latestEntry = activityOverview.entries[0] ?? null;
  const refreshSummary = refreshState?.job_id ? "A refresh is already queued in the background." : "No refresh job is queued right now.";
  const latestEntrySummary = latestEntry ? `The newest dated activity is ${latestEntry.title} on ${formatDate(latestEntry.date)}.` : "No dated SEC activity is cached yet.";

  return `${activityOverview.summary.total.toLocaleString()} alert${activityOverview.summary.total === 1 ? " is" : "s are"} currently on the monitor for ${company?.ticker ?? "this company"}. ${latestEntrySummary} ${refreshSummary}`;
}

function buildCapitalSignalRows({
  capitalMarketsSummary,
  governanceSummary,
  ownershipSummary,
  equityClaimRiskSummary,
  isForeignIssuerLike,
}: {
  capitalMarketsSummary: CompanyCapitalMarketsSummaryResponse["summary"] | null;
  governanceSummary: CompanyGovernanceSummaryResponse["summary"] | null;
  ownershipSummary: CompanyBeneficialOwnershipSummaryResponse["summary"] | null;
  equityClaimRiskSummary: EquityClaimRiskSummaryPayload | null;
  isForeignIssuerLike: boolean;
}) {
  const rows: Array<{ signal: string; currentRead: string; latestEvidence: string }> = [];

  if (capitalMarketsSummary) {
    rows.push({
      signal: "Capital markets",
      currentRead: `${capitalMarketsSummary.total_filings.toLocaleString()} filings · largest offering ${formatCompactCurrency(capitalMarketsSummary.max_offering_amount)}`,
      latestEvidence: capitalMarketsSummary.latest_filing_date ? formatDate(capitalMarketsSummary.latest_filing_date) : "Pending",
    });
  }

  if (governanceSummary) {
    rows.push({
      signal: "Governance",
      currentRead:
        isForeignIssuerLike && governanceSummary.total_filings === 0
          ? "U.S. proxy materials may be unavailable for many 20-F and 40-F issuers"
          : `${governanceSummary.total_filings.toLocaleString()} proxy filings · ${governanceSummary.filings_with_vote_items.toLocaleString()} with vote items`,
      latestEvidence:
        isForeignIssuerLike && governanceSummary.total_filings === 0
          ? "Limited by filing regime"
          : governanceSummary.latest_meeting_date
            ? formatDate(governanceSummary.latest_meeting_date)
            : "Pending",
    });
  }

  if (ownershipSummary) {
    rows.push({
      signal: "Stake changes",
      currentRead: `${ownershipSummary.total_filings.toLocaleString()} filings · ${ownershipSummary.ownership_increase_events.toLocaleString()} up / ${ownershipSummary.ownership_decrease_events.toLocaleString()} down`,
      latestEvidence: ownershipSummary.latest_event_date ? formatDate(ownershipSummary.latest_event_date) : "Pending",
    });
  }

  if (equityClaimRiskSummary) {
    rows.push({
      signal: "Equity claim",
      currentRead: `${titleCase(equityClaimRiskSummary.overall_risk_level)} risk · net dilution ${formatPercent(equityClaimRiskSummary.net_dilution_ratio)}`,
      latestEvidence: equityClaimRiskSummary.latest_period_end ? formatDate(equityClaimRiskSummary.latest_period_end) : "Pending",
    });
  }

  return rows;
}

function buildMonitorChecklist({
  refreshState,
  activityOverview,
  company,
  ownershipSummary,
  capitalMarketsSummary,
}: {
  refreshState: RefreshState | null;
  activityOverview: CompanyActivityOverviewResponse | null;
  company: BriefCompany | null;
  ownershipSummary: CompanyBeneficialOwnershipSummaryResponse["summary"] | null;
  capitalMarketsSummary: CompanyCapitalMarketsSummaryResponse["summary"] | null;
}): MonitorChecklistItem[] {
  const items: MonitorChecklistItem[] = [];

  items.push({
    title: "Refresh status",
    detail: refreshState?.job_id
      ? `Refresh job ${refreshState.job_id} is running in the background.`
      : company?.last_checked
        ? `No refresh queued. Last full company check ran on ${formatDate(company.last_checked)}.`
        : "No refresh queued yet.",
    tone: refreshState?.job_id || company?.last_checked ? "cyan" : "gold",
  });

  if (activityOverview) {
    items.push({
      title: "Alert count",
      detail: `${activityOverview.summary.high.toLocaleString()} high, ${activityOverview.summary.medium.toLocaleString()} medium, and ${activityOverview.summary.low.toLocaleString()} low alert${activityOverview.summary.total === 1 ? " is" : "s are"} currently active.`,
      tone:
        activityOverview.summary.high > 0
          ? "red"
          : activityOverview.summary.medium > 0
            ? "gold"
            : activityOverview.summary.low > 0
              ? "green"
              : "cyan",
    });

    if (activityOverview.entries[0]) {
      items.push({
        title: "Latest activity",
        detail: `${activityOverview.entries[0].title} on ${formatDate(activityOverview.entries[0].date)} should be the first thing to revisit if the thesis changes.`,
        tone: toneForEntryCard(activityOverview.entries[0]),
      });
    }
  }

  if (ownershipSummary) {
    items.push({
      title: "Ownership watch",
      detail: ownershipSummary.latest_event_date
        ? `${ownershipSummary.total_filings.toLocaleString()} major-holder filing${ownershipSummary.total_filings === 1 ? "" : "s"} are cached through ${formatDate(ownershipSummary.latest_event_date)}.`
        : "Major-holder change monitoring is enabled, but the latest dated filing is still pending.",
      tone: ownershipSummary.ownership_decrease_events > 0 ? "gold" : "cyan",
    });
  }

  if (capitalMarketsSummary) {
    items.push({
      title: "Financing watch",
      detail: capitalMarketsSummary.latest_filing_date
        ? `${capitalMarketsSummary.registration_filings.toLocaleString()} registration filing${capitalMarketsSummary.registration_filings === 1 ? "" : "s"} are cached through ${formatDate(capitalMarketsSummary.latest_filing_date)}.`
        : "No recent financing filing date is cached yet.",
      tone: capitalMarketsSummary.registration_filings > 0 ? "gold" : "cyan",
    });
  }

  return items.slice(0, 4);
}

function extractTopSegment(latestFinancial: FinancialPayload | null) {
  if (!latestFinancial?.segment_breakdown.length) {
    return null;
  }

  return [...latestFinancial.segment_breakdown].sort((left, right) => {
    const leftValue = left.share_of_revenue ?? left.revenue ?? Number.NEGATIVE_INFINITY;
    const rightValue = right.share_of_revenue ?? right.revenue ?? Number.NEGATIVE_INFINITY;
    return rightValue - leftValue;
  })[0] ?? null;
}

function extractModelNumber(models: CompanyModelsResponse["models"], modelName: string, path: string[]): number | null {
  const model = models.find((entry) => entry.model_name === modelName);
  if (!model) {
    return null;
  }

  let current: unknown = model.result;
  for (const key of path) {
    current = asRecord(current)[key];
  }

  return safeNumber(current);
}

function safeNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function safeDivide(numerator: number | null | undefined, denominator: number | null | undefined): number | null {
  if (numerator == null || denominator == null || denominator === 0) {
    return null;
  }

  return numerator / denominator;
}

function growthRate(current: number | null | undefined, previous: number | null | undefined): number | null {
  if (current == null || previous == null || previous === 0) {
    return null;
  }

  return (current - previous) / Math.abs(previous);
}

function median(values: Array<number | null | undefined>): number | null {
  const numericValues = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value)).sort((left, right) => left - right);

  if (!numericValues.length) {
    return null;
  }

  const middle = Math.floor(numericValues.length / 2);
  if (numericValues.length % 2 === 0) {
    return (numericValues[middle - 1] + numericValues[middle]) / 2;
  }

  return numericValues[middle];
}

function formatSourceMixLabel(sourceMix: SourceMixPayload | null | undefined, provenance: ProvenanceEntryPayload[] | null | undefined): string | null {
  const fallbackLabels = resolveCommercialFallbackLabels(provenance, sourceMix);

  if (sourceMix?.official_only) {
    return "Official/public only";
  }

  if (fallbackLabels.length) {
    return "Official + labeled fallback";
  }

  if (provenance?.length) {
    return "Cached source mix";
  }

  return null;
}

function formatEvidenceSourceSummary(sourceMix: SourceMixPayload | null | undefined, provenance: ProvenanceEntryPayload[] | null | undefined): string {
  return formatSourceMixLabel(sourceMix, provenance) ?? "Pending";
}

function formatEvidenceFallbackLabel(
  provenance: ProvenanceEntryPayload[] | null | undefined,
  sourceMix: SourceMixPayload | null | undefined,
): string {
  const fallbackLabels = resolveCommercialFallbackLabels(provenance, sourceMix);

  if (fallbackLabels.length) {
    return fallbackLabels.join(", ");
  }

  if (sourceMix?.official_only || provenance?.length) {
    return "Official only";
  }

  return "Pending";
}

function formatBriefEvidenceFreshness(lastRefreshedAt: string | null | undefined, lastChecked: string | null | undefined): string {
  if (lastRefreshedAt) {
    return `Refreshed ${formatDate(lastRefreshedAt)}`;
  }
  if (lastChecked) {
    return `Checked ${formatDate(lastChecked)}`;
  }
  return "Pending";
}

function formatCompactCurrency(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }

  return `$${formatCompactNumber(value)}`;
}

function formatMultiple(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }

  return `${value.toFixed(1)}x`;
}

function formatFeedEntryType(type: string): string {
  if (type === "form144") {
    return "planned-sale";
  }

  return type;
}

function humanizeToken(value: string): string {
  return value.replaceAll("_", " ");
}

function mapBriefResponseToAsyncState(brief: CompanyResearchBriefResponse): ResearchBriefDataState {
  const whatChangedAvailable = isBriefSectionAvailable(brief, "what_changed") || brief.build_state === "ready";
  const capitalRiskAvailable = isBriefSectionAvailable(brief, "capital_and_risk") || brief.build_state === "ready";
  const valuationAvailable = isBriefSectionAvailable(brief, "valuation") || brief.build_state === "ready";

  return {
    brief,
    error: null,
    loading: false,
    buildState: brief.build_state,
    buildStatus: brief.build_status,
    availableSections: [...brief.available_sections],
    sectionStatuses: [...brief.section_statuses],
    filingTimeline: [...brief.filing_timeline],
    summaryCards: [...brief.stale_summary_cards],
    activityOverview: resolveBriefSectionData(whatChangedAvailable, brief.what_changed.activity_overview),
    changes: resolveBriefSectionData(whatChangedAvailable, brief.what_changed.changes),
    earningsSummary: resolveBriefSectionData(whatChangedAvailable, brief.what_changed.earnings_summary),
    capitalStructure: resolveBriefSectionData(capitalRiskAvailable, brief.capital_and_risk.capital_structure),
    capitalMarketsSummary: resolveBriefSectionData(capitalRiskAvailable, brief.capital_and_risk.capital_markets_summary),
    governanceSummary: resolveBriefSectionData(capitalRiskAvailable, brief.capital_and_risk.governance_summary),
    ownershipSummary: resolveBriefSectionData(capitalRiskAvailable, brief.capital_and_risk.ownership_summary),
    models: resolveBriefSectionData(valuationAvailable, brief.valuation.models),
    peers: resolveBriefSectionData(valuationAvailable, brief.valuation.peers),
  };
}

function resolveBriefSectionData<T>(available: boolean, data: T): AsyncState<T> {
  return {
    data: available ? data : null,
    error: null,
    loading: !available,
  };
}

function isBriefSectionAvailable(brief: CompanyResearchBriefResponse, sectionId: string): boolean {
  return brief.available_sections.includes(sectionId);
}

function advanceResearchBriefDataState(
  current: ResearchBriefDataState,
  sectionId: string,
  updates: Partial<ResearchBriefAsyncState>
): ResearchBriefDataState {
  const availableSections = current.availableSections.includes(sectionId)
    ? current.availableSections
    : [...current.availableSections, sectionId];

  return {
    ...current,
    ...updates,
    loading: false,
    buildState: current.buildState === "building" ? "partial" : current.buildState,
    buildStatus: buildStatusForAvailableSections(availableSections),
    availableSections,
    sectionStatuses: updateResearchBriefSectionStatuses(current.sectionStatuses, availableSections),
  };
}

function updateResearchBriefSectionStatuses(
  currentStatuses: ResearchBriefSectionStatusPayload[],
  availableSections: string[]
): ResearchBriefSectionStatusPayload[] {
  const byId = new Map(currentStatuses.map((item) => [item.id, item]));
  const available = new Set(availableSections);
  let partialAssigned = false;

  return ["snapshot", "what_changed", "business_quality", "capital_and_risk", "valuation"].map((sectionId) => {
    const existing = byId.get(sectionId);
    let state: ResearchBriefBuildState = "building";
    let detail = existing?.detail ?? "Warming up.";

    if (available.has(sectionId)) {
      state = "ready";
      detail = "Available now.";
    } else if (!partialAssigned && available.size > 0) {
      state = "partial";
      detail = "Queued next.";
      partialAssigned = true;
    }

    return {
      id: sectionId,
      title: existing?.title ?? titleCase(sectionId.replaceAll("_", " ")),
      state,
      available: available.has(sectionId),
      detail,
    };
  });
}

function buildStatusForAvailableSections(availableSections: string[]): string {
  if (availableSections.includes("valuation")) {
    return "Most specialist sections are visible while the cached brief catches up.";
  }
  if (availableSections.includes("capital_and_risk")) {
    return "Capital and risk signals are live. Valuation is loading next.";
  }
  if (availableSections.includes("what_changed")) {
    return "Change summaries are live. Capital and risk is loading next.";
  }
  return "Showing the bootstrap snapshot while the rest of the brief hydrates.";
}

function mergeBusinessQualitySectionStatus(
  sectionStatuses: ResearchBriefSectionStatusPayload[],
  { loading, hasFinancials }: { loading: boolean; hasFinancials: boolean }
): ResearchBriefSectionStatusPayload[] {
  const nextStatuses = [...sectionStatuses];
  const sectionId = "business_quality";
  const index = nextStatuses.findIndex((item) => item.id === sectionId);

  const nextStatus: ResearchBriefSectionStatusPayload = {
    id: sectionId,
    title: nextStatuses[index]?.title ?? "Business Quality",
    state: hasFinancials ? "ready" : loading ? "partial" : nextStatuses[index]?.state ?? "building",
    available: hasFinancials || nextStatuses[index]?.available || false,
    detail: hasFinancials
      ? "Available now."
      : loading
        ? "Loading company financial history."
        : nextStatuses[index]?.detail ?? "Warming up.",
  };

  if (index >= 0) {
    nextStatuses[index] = nextStatus;
    return nextStatuses;
  }

  nextStatuses.push(nextStatus);
  return nextStatuses;
}

function findBriefSummaryCardValue(cards: ResearchBriefSummaryCardPayload[], title: string): string | null {
  return cards.find((card) => card.title === title)?.value ?? null;
}

function formatResearchBriefBuildState(state: ResearchBriefBuildState): string {
  if (state === "ready") {
    return "Ready";
  }
  if (state === "partial") {
    return "Partial";
  }
  return "Building";
}

function isForeignIssuerAnnualForm(filingType: string | null | undefined) {
  return filingType === "20-F" || filingType === "40-F";
}
