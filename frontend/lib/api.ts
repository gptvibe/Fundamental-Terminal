// Barrel file – all public exports are split into focused sub-modules under ./api/.
// Imports from "@/lib/api" continue to work unchanged.

export type { ReadCachePolicy, ApiReadCacheState } from "./api/types";
export { resolveReadPolicy, isReadRequest, shouldBypassReadCache } from "./api/cachePolicy";
export {
  invalidateApiReadCache,
  invalidateApiReadCacheForTicker,
  getApiReadCacheState,
} from "./api/cacheStore";
export {
  setApiAuthHeadersProvider,
  __resetApiClientCacheForTests,
} from "./api/client";
export {
  searchCompanies,
  resolveCompanyIdentifier,
  getOfficialScreenerMetadata,
  searchOfficialScreener,
    getSecFramesScreener,
  getCompanyOverview,
  getCompanyWorkspaceBootstrap,
  getCompaniesCompare,
  getCompanyEquityClaimRisk,
  getCompanyEvents,
  getCompanyCapitalRaises,
  getCompanyCapitalMarkets,
  getCompanyCapitalMarketsSummary,
  getCompanyActivityFeed,
  getCompanyAlerts,
  getCompanyActivityOverview,
  getCompanyMarketContext,
  getCompanySectorContext,
  getGlobalMarketContext,
  getCompanyResearchBrief,
  getCompanyPeers,
  getCompanyCommentLetters,
  refreshCompany,
} from "./api/company";
export {
  getCompanyFinancials,
  getCompanyCapitalStructure,
  getCompanySegmentHistory,
  getCompanyChangesSinceLastFiling,
  getCompanyFinancialRestatements,
  getCompanyMetricsTimeseries,
  getCompanyDerivedMetrics,
  getCompanyDerivedMetricsSummary,
  getCompanyOilScenario,
  getCompanyOilScenarioOverlay,
  getCompanyFinancialHistory,
  type CompanyFactsPayload,
} from "./api/financials";
export {
  getCompanyFilings,
  getCompanyExhibits,
  getCompanyFilingEvents,
  getCompanyFilingEventsSummary,
  getCompanyFilingInsights,
  getCompanyFilingRiskSignals,
  getCompanyEarnings,
  getCompanyEarningsSummary,
  getCompanyEarningsWorkspace,
} from "./api/filings";
export {
  getCompanyInsiderTrades,
  getCompanyBeneficialOwnership,
  getCompanyBeneficialOwnershipSummary,
  getCompanyInstitutionalHoldings,
  getCompanyInstitutionalHoldingsSummary,
  getCompanyForm144Filings,
} from "./api/ownership";
export {
  getCompanyGovernance,
  getCompanyGovernanceSummary,
  getCompanyExecutiveCompensation,
} from "./api/governance";
export {
  getCompanyCharts,
  getCompanyChartsForecastAccuracy,
  getCompanyChartsWhatIf,
  createCompanyChartsShareSnapshot,
  getCompanyChartsShareSnapshot,
  listCompanyChartsScenarios,
  getCompanyChartsScenario,
  createCompanyChartsScenario,
  updateCompanyChartsScenario,
  cloneCompanyChartsScenario,
  getCompanyModels,
  getLatestModelEvaluation,
} from "./api/models";
export {
  getWatchlistSummary,
  getWatchlistCalendar,
  getResearchWorkspace,
  saveResearchWorkspace,
  deleteResearchWorkspace,
  importLocalResearchWorkspace,
} from "./api/watchlist";
export {
  getSourceRegistry,
  getCacheMetrics,
} from "./api/sourceRegistry";
