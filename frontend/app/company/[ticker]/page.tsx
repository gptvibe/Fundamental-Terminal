"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";

import { RiskRedFlagPanel } from "@/components/alerts/risk-red-flag-panel";
import { PanelErrorBoundary } from "@/components/company/brief-primitives";
import { CompanyOverviewStatusStrip } from "@/components/company/company-overview-layout-sections";
import { CompanyResearchHeader } from "@/components/layout/company-research-header";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { DeferredClientSection } from "@/components/performance/deferred-client-section";
import { resolveCommercialFallbackLabels } from "@/components/ui/commercial-fallback-notice";
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
} from "@/lib/api";
import { MODEL_NAMES } from "@/lib/constants";
import { prefetchCompanyWorkspaceTabs } from "@/lib/company-workspace-prefetch";
import { downloadJsonFile, normalizeExportFileStem } from "@/lib/export";
import { formatDate, formatPercent } from "@/lib/format";
import { ResearchBriefHeroSummary } from "./_components/research-brief-hero-summary";
import { ResearchBriefSectionNav } from "./_components/research-brief-section-nav";
import { ResearchBriefWarmupPanel } from "./_components/research-brief-warmup-panel";
import { useResearchBriefData } from "./_hooks/use-research-brief-data";
import { useActiveBriefSection, useResearchBriefSectionPreferences } from "./_hooks/use-research-brief-sections";
import {
  buildBusinessQualityNarrative,
  buildCapitalRiskNarrative,
  buildCapitalSignalRows,
  buildInitialCompanyLoadMessage,
  buildMonitorChecklist,
  buildMonitorNarrative,
  buildRefreshQueueDetailLine,
  buildSnapshotNarrative,
  buildValuationNarrative,
  buildWhatChangedNarrative,
  extractTopSegment,
  findBriefSummaryCardValue,
  formatCompactCurrency,
  isForeignIssuerAnnualForm,
  mergeBusinessQualitySectionStatus,
} from "./_lib/research-brief-utils";
import { BRIEF_SECTION_IDS } from "./_lib/research-brief-types";
import { SnapshotSection } from "./_sections/snapshot-section";

const WhatChangedSection = dynamic(
  () => import("./_sections/what-changed-section").then((module) => module.WhatChangedSection),
  { loading: () => <DeferredSectionPlaceholder title="What changed" /> }
);

const CapitalRiskSection = dynamic(
  () => import("./_sections/capital-risk-section").then((module) => module.CapitalRiskSection),
  { loading: () => <DeferredSectionPlaceholder title="Capital & risk" /> }
);

const BriefBusinessQualitySection = dynamic(
  () => import("@/components/company/brief-business-quality-section").then((module) => module.BriefBusinessQualitySection),
  { loading: () => <DeferredSectionPlaceholder title="Business quality" /> }
);

const BriefValuationSection = dynamic(
  () => import("@/components/company/brief-valuation-section").then((module) => module.BriefValuationSection),
  { loading: () => <DeferredSectionPlaceholder title="Valuation" /> }
);

const BriefMonitorSection = dynamic(
  () => import("@/components/company/brief-monitor-section").then((module) => module.BriefMonitorSection),
  { loading: () => <DeferredSectionPlaceholder title="Monitor" /> }
);

const ResearchBriefPlainEnglishPanel = dynamic(
  () => import("@/components/company/research-brief-plain-english-panel").then((module) => module.ResearchBriefPlainEnglishPanel),
  { loading: () => <DeferredSectionPlaceholder title="Loading plain-English analysis" /> }
);

const CompanyOverviewDataQualitySourcesSection = dynamic(
  () => import("@/components/company/company-overview-layout-sections").then((module) => module.CompanyOverviewDataQualitySourcesSection),
  { loading: () => <DeferredSectionPlaceholder title="Data quality & sources" /> }
);

function DeferredSectionPlaceholder({ title }: { title: string }) {
  return (
    <div className="research-brief-state research-brief-state-loading" aria-live="polite">
      <h2 className="workspace-state-title">{title}</h2>
      <div className="grid-empty-kicker">Research brief</div>
      <div className="grid-empty-title">Loading section</div>
      <div className="grid-empty-copy">Preparing persisted cached data for this section.</div>
    </div>
  );
}


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

  const snapshotNarrative = useMemo(
    () =>
      buildSnapshotNarrative({
        company: pageCompany,
        latestFinancial,
        topSegment,
        alertCount: latestAlertCount,
        buildState: briefData.buildState,
        filingTimeline: briefData.filingTimeline,
        sourceMix: data?.source_mix,
        provenance: data?.provenance,
        loading,
      }),
    [pageCompany, latestFinancial, topSegment, latestAlertCount, briefData.buildState, briefData.filingTimeline, data?.source_mix, data?.provenance, loading]
  );
  const whatChangedNarrative = useMemo(
    () =>
      buildWhatChangedNarrative({
        changes: briefData.changes.data,
        earningsSummary: briefData.earningsSummary.data,
        activityOverview: briefData.activityOverview.data,
        loading: briefData.changes.loading || briefData.earningsSummary.loading || briefData.activityOverview.loading,
      }),
    [briefData.changes.data, briefData.earningsSummary.data, briefData.activityOverview.data, briefData.changes.loading, briefData.earningsSummary.loading, briefData.activityOverview.loading]
  );
  const businessQualityNarrative = useMemo(
    () =>
      buildBusinessQualityNarrative({
        latestFinancial,
        previousAnnual,
        loading,
      }),
    [latestFinancial, previousAnnual, loading]
  );
  const capitalRiskNarrative = useMemo(
    () =>
      buildCapitalRiskNarrative({
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
      }),
    [
      briefData.capitalStructure.data,
      briefData.capitalMarketsSummary.data,
      briefData.governanceSummary.data,
      briefData.ownershipSummary.data,
      equityClaimRiskSummary,
      foreignIssuerStyleFiling,
      briefData.capitalStructure.loading,
      briefData.capitalMarketsSummary.loading,
      briefData.governanceSummary.loading,
      briefData.ownershipSummary.loading,
    ]
  );
  const valuationNarrative = useMemo(
    () =>
      buildValuationNarrative({
        models: briefData.models.data?.models ?? [],
        peers: briefData.peers.data?.peers ?? [],
        priceHistory,
        loading: briefData.models.loading || briefData.peers.loading,
      }),
    [briefData.models.data?.models, briefData.peers.data?.peers, priceHistory, briefData.models.loading, briefData.peers.loading]
  );
  const monitorNarrative = useMemo(
    () =>
      buildMonitorNarrative({
        activityOverview: briefData.activityOverview.data,
        refreshState,
        company: pageCompany,
        loading: briefData.activityOverview.loading,
      }),
    [briefData.activityOverview.data, refreshState, pageCompany, briefData.activityOverview.loading]
  );
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
  const eagerDeferredSections = process.env.NODE_ENV === "test";

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

      <CompanyOverviewStatusStrip
        asOf={data?.as_of ?? briefData.brief?.as_of ?? null}
        lastRefreshedAt={data?.last_refreshed_at ?? null}
        sourceMix={data?.source_mix ?? null}
        provenance={data?.provenance ?? null}
        refreshState={refreshState}
        cacheState={pageCompany?.cache_state ?? null}
        hasWarnings={Boolean(error || briefData.error)}
      />



      <SnapshotSection
        loading={loading}
        priceHistory={priceHistory}
        fundamentalsTrendData={fundamentalsTrendData}
        latestFinancial={latestFinancial}
        financials={financials}
        topSegment={topSegment}
        latestAlertCount={latestAlertCount}
        segmentAnalysis={data?.segment_analysis}
        narrative={snapshotNarrative}
        links={snapshotLinks}
        expanded={expandedSections.snapshot ?? true}
        onToggle={() => toggleSection("snapshot")}
      />

      <DeferredClientSection
        forceVisible={eagerDeferredSections}
        rootMargin="120px 0px"
        placeholder={<DeferredSectionPlaceholder title="Plain-English analysis" />}
      >
        <PanelErrorBoundary kicker="Analysis" title="Unable to render plain-English analysis">
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
        </PanelErrorBoundary>
      </DeferredClientSection>

      <ResearchBriefSectionNav activeSectionId={activeSectionId} />

      <DeferredClientSection
        forceVisible={eagerDeferredSections}
        rootMargin="220px 0px"
        placeholder={<DeferredSectionPlaceholder title="What changed" />}
      >
        <WhatChangedSection
          changesState={briefData.changes}
          earningsSummaryState={briefData.earningsSummary}
          activityOverviewState={briefData.activityOverview}
          topAlerts={topAlerts}
          latestEntries={latestEntries}
          briefLoading={briefData.loading}
          ticker={ticker}
          reloadKey={reloadKey}
          narrative={whatChangedNarrative}
          links={whatChangedLinks}
          expanded={expandedSections["what-changed"] ?? true}
          onToggle={() => toggleSection("what-changed")}
        />
      </DeferredClientSection>

      <DeferredClientSection
        forceVisible={eagerDeferredSections}
        rootMargin="260px 0px"
        placeholder={<DeferredSectionPlaceholder title="Business quality" />}
      >
        <PanelErrorBoundary kicker="Business quality" title="Unable to render business quality section">
          <BriefBusinessQualitySection
            financials={financials}
            loading={loading}
            error={error}
            narrative={businessQualityNarrative}
            asOf={data?.as_of}
            lastRefreshedAt={data?.last_refreshed_at}
            lastCheckedFinancials={pageCompany?.last_checked_financials}
            provenance={data?.provenance}
            sourceMix={data?.source_mix}
            confidenceFlags={data?.confidence_flags}
            links={businessQualityLinks}
            expanded={expandedSections["business-quality"] ?? true}
            onToggle={() => toggleSection("business-quality")}
          />
        </PanelErrorBoundary>
      </DeferredClientSection>

      <DeferredClientSection
        forceVisible={eagerDeferredSections}
        rootMargin="320px 0px"
        placeholder={<DeferredSectionPlaceholder title="Capital & risk" />}
      >
        <CapitalRiskSection
          ticker={ticker}
          reloadKey={reloadKey}
          capitalStructureState={briefData.capitalStructure}
          capitalMarketsSummaryState={briefData.capitalMarketsSummary}
          governanceSummaryState={briefData.governanceSummary}
          ownershipSummaryState={briefData.ownershipSummary}
          briefLoading={briefData.loading}
          briefCapitalRiskCue={briefData.brief?.capital_and_risk}
          equityClaimRiskSummary={equityClaimRiskSummary}
          capitalSignalRows={capitalSignalRows}
          foreignIssuerStyleFiling={foreignIssuerStyleFiling}
          financials={financials}
          loading={loading}
          error={error}
          narrative={capitalRiskNarrative}
          links={capitalRiskLinks}
          expanded={expandedSections["capital-risk"] ?? true}
          onToggle={() => toggleSection("capital-risk")}
          lastCheckedFilings={pageCompany?.last_checked_filings}
        />
      </DeferredClientSection>

      <DeferredClientSection
        forceVisible={eagerDeferredSections}
        rootMargin="380px 0px"
        placeholder={<DeferredSectionPlaceholder title="Valuation" />}
      >
        <PanelErrorBoundary kicker="Valuation" title="Unable to render valuation section">
          <BriefValuationSection
            ticker={ticker}
            modelsState={briefData.models}
            peersState={briefData.peers}
            financials={financials}
            priceHistory={priceHistory}
            strictOfficialMode={Boolean(briefData.models.data?.company?.strict_official_mode ?? pageCompany?.strict_official_mode)}
            narrative={valuationNarrative}
            links={valuationLinks}
            expanded={expandedSections.valuation ?? true}
            onToggle={() => toggleSection("valuation")}
          />
        </PanelErrorBoundary>
      </DeferredClientSection>

      <DeferredClientSection
        forceVisible={eagerDeferredSections}
        rootMargin="420px 0px"
        placeholder={<DeferredSectionPlaceholder title="Monitor" />}
      >
        <PanelErrorBoundary kicker="Monitor" title="Unable to render monitor section">
          <BriefMonitorSection
            activityOverviewState={briefData.activityOverview}
            topAlerts={topAlerts}
            latestEntries={latestEntries}
            monitorChecklist={monitorChecklist}
            narrative={monitorNarrative}
            lastChecked={pageCompany?.last_checked}
            links={monitorLinks}
            expanded={expandedSections.monitor ?? true}
            onToggle={() => toggleSection("monitor")}
          />
        </PanelErrorBoundary>
      </DeferredClientSection>

      <DeferredClientSection
        forceVisible={eagerDeferredSections}
        rootMargin="480px 0px"
        placeholder={<DeferredSectionPlaceholder title="Data quality & sources" />}
      >
        <CompanyOverviewDataQualitySourcesSection
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
          fallbackLabels={fallbackLabels}
          warmupPanel={
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
          }
          partialErrors={
            error || briefData.error ? (
              <div className="research-brief-partial-errors">
                {[error, briefData.error].filter(Boolean).map((message) => (
                  <span key={message} className="pill">
                    {message}
                  </span>
                ))}
              </div>
            ) : null
          }
        />
      </DeferredClientSection>
    </CompanyWorkspaceShell>
  );
}

