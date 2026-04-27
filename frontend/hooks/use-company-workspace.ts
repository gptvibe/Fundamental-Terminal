"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { buildCompanyWorkspaceCacheKey, useCompanyLayoutContext } from "@/components/layout/company-layout-context";
import { useJobStream } from "@/hooks/use-job-stream";
import { rememberActiveJob } from "@/lib/active-job";
import { COMMAND_PALETTE_REFRESH_EVENT, type CommandPaletteTickerDetail } from "@/lib/command-palette-events";
import {
  getCompanyWorkspaceBootstrap,
  getCompanyFinancials,
  getCompanyEarningsSummary,
  getCompanyOverview,
  getCompanyInsiderTrades,
  getCompanyInstitutionalHoldings,
  invalidateApiReadCacheForTicker,
  refreshCompany,
} from "@/lib/api";
import { withPerformanceAuditSource } from "@/lib/performance-audit";
import { recordRecentCompany } from "@/lib/recent-companies";
import type {
  CompanyFinancialsResponse,
  CompanyEarningsSummaryResponse,
  CompanyInsiderTradesResponse,
  CompanyInstitutionalHoldingsResponse,
  CompanyResearchBriefResponse,
  CompanyWorkspaceBootstrapResponse,
  ConsoleEntry,
  FundamentalsTrendPoint
} from "@/lib/types";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);

interface UseCompanyWorkspaceOptions {
  includeInsiders?: boolean;
  includeInstitutional?: boolean;
  includeOverviewBrief?: boolean;
  includeEarningsSummary?: boolean;
  includeChartConsole?: boolean;
  financialsView?: "full" | "core_segments" | "core";
  workspaceAsOf?: string | null;
  auditPageRoute?: string;
  auditScenario?: string;
  initialWorkspaceData?: LoadCompanyWorkspaceDataResult | null;
}

export interface LoadCompanyWorkspaceDataResult {
  financialData: CompanyFinancialsResponse;
  briefData: CompanyResearchBriefResponse | null;
  earningsSummaryData: CompanyEarningsSummaryResponse | null;
  insiderData: CompanyInsiderTradesResponse | null;
  institutionalData: CompanyInstitutionalHoldingsResponse | null;
  insiderError: string | null;
  institutionalError: string | null;
  activeJobId: string | null;
}

const COMPATIBILITY_FALLBACK_STATUSES = new Set([404, 405, 501]);
const WORKSPACE_PRICE_HISTORY_LATEST_N = 3200;
const WORKSPACE_PRICE_HISTORY_MAX_POINTS = 480;
const WORKSPACE_LAYOUT_CACHE_TTL_MS = 30_000;

export function useCompanyWorkspace(
  ticker: string,
  {
    includeInsiders = false,
    includeInstitutional = false,
    includeOverviewBrief = false,
    includeEarningsSummary = false,
    includeChartConsole = false,
    financialsView,
    workspaceAsOf,
    auditPageRoute,
    auditScenario,
    initialWorkspaceData = null,
  }: UseCompanyWorkspaceOptions = {}
) {
  const normalizedTicker = ticker.toUpperCase();
  const resolvedFinancialsView =
    financialsView ??
    (includeOverviewBrief && !includeInsiders && !includeInstitutional ? "core_segments" : "full");
  const normalizedWorkspaceAsOf = workspaceAsOf?.trim() || null;
  const companyLayout = useCompanyLayoutContext();
  const workspaceCacheKey = useMemo(
    () =>
      buildCompanyWorkspaceCacheKey({
        ticker: normalizedTicker,
        financialsView: resolvedFinancialsView,
        includeInsiders,
        includeInstitutional,
        includeOverviewBrief,
        includeEarningsSummary,
        asOf: normalizedWorkspaceAsOf,
      }),
    [
      includeEarningsSummary,
      includeInsiders,
      includeInstitutional,
      includeOverviewBrief,
      normalizedTicker,
      normalizedWorkspaceAsOf,
      resolvedFinancialsView,
    ]
  );
  const initialWorkspaceSeed = useMemo(() => {
    if (!initialWorkspaceData) {
      return null;
    }

    const initialTicker = initialWorkspaceData.financialData.company?.ticker?.toUpperCase();
    return initialTicker === normalizedTicker ? initialWorkspaceData : null;
  }, [initialWorkspaceData, normalizedTicker]);
  const getWorkspaceCacheEntry = companyLayout?.getWorkspaceCacheEntry;
  const setWorkspaceCacheEntry = companyLayout?.setWorkspaceCacheEntry;
  const invalidateWorkspaceCacheForTicker = companyLayout?.invalidateWorkspaceCacheForTicker;
  const initialHydratedResult = initialWorkspaceSeed ?? getWorkspaceCacheEntry?.(workspaceCacheKey)?.payload ?? null;

  const [data, setData] = useState<CompanyFinancialsResponse | null>(initialHydratedResult?.financialData ?? null);
  const [briefData, setBriefData] = useState<CompanyResearchBriefResponse | null>(initialHydratedResult?.briefData ?? null);
  const [earningsSummaryData, setEarningsSummaryData] = useState<CompanyEarningsSummaryResponse | null>(initialHydratedResult?.earningsSummaryData ?? null);
  const [insiderData, setInsiderData] = useState<CompanyInsiderTradesResponse | null>(initialHydratedResult?.insiderData ?? null);
  const [institutionalData, setInstitutionalData] = useState<CompanyInstitutionalHoldingsResponse | null>(initialHydratedResult?.institutionalData ?? null);
  const [insiderError, setInsiderError] = useState<string | null>(initialHydratedResult?.insiderError ?? null);
  const [institutionalError, setInstitutionalError] = useState<string | null>(initialHydratedResult?.institutionalError ?? null);
  const [loading, setLoading] = useState(initialHydratedResult == null);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(initialHydratedResult?.activeJobId ?? null);
  const [chartConsoleEntries, setChartConsoleEntries] = useState<ConsoleEntry[]>([]);
  const [lastChartKey, setLastChartKey] = useState<string | null>(null);
  const [settledJobIds, setSettledJobIds] = useState<string[]>([]);
  const [refreshTick, setRefreshTick] = useState(0);

  const applyWorkspaceResult = useCallback((result: LoadCompanyWorkspaceDataResult) => {
    setData(result.financialData);
    setBriefData(result.briefData);
    setEarningsSummaryData(result.earningsSummaryData);
    setInsiderData(result.insiderData);
    setInstitutionalData(result.institutionalData);
    setInsiderError(result.insiderError);
    setInstitutionalError(result.institutionalError);
    setActiveJobId(result.activeJobId);
  }, []);

  const clearWorkspaceResult = useCallback(() => {
    setData(null);
    setBriefData(null);
    setEarningsSummaryData(null);
    setInsiderError(null);
    setInstitutionalError(null);
    setInsiderData(null);
    setInstitutionalData(null);
    setActiveJobId(null);
  }, []);

  const financials = useMemo(() => data?.financials ?? [], [data?.financials]);
  const priceHistory = useMemo(() => data?.price_history ?? [], [data?.price_history]);
  const insiderTrades = useMemo(() => insiderData?.insider_trades ?? [], [insiderData?.insider_trades]);
  const institutionalHoldings = useMemo(() => institutionalData?.institutional_holdings ?? [], [institutionalData?.institutional_holdings]);
  const latestFinancial = financials[0] ?? null;
  const annualStatements = useMemo(
    () => financials.filter((item) => ANNUAL_FORMS.has(item.filing_type)),
    [financials]
  );
  const fundamentalsTrendData = useMemo<FundamentalsTrendPoint[]>(
    () =>
      [...annualStatements].reverse().map((item) => ({
        date: item.period_end,
        revenue: item.revenue,
        eps: item.eps,
        free_cash_flow: item.free_cash_flow
      })),
    [annualStatements]
  );
  const refreshState = data?.refresh ?? institutionalData?.refresh ?? insiderData?.refresh ?? null;
  const trackedJobId = activeJobId ?? refreshState?.job_id;
  const { consoleEntries: streamEntries, connectionState, lastEvent } = useJobStream(trackedJobId);

  const runWithAudit = useCallback(async <T,>(source: string, work: () => Promise<T>): Promise<T> => {
    if (!auditPageRoute || !auditScenario) {
      return work();
    }

    return withPerformanceAuditSource(
      {
        pageRoute: auditPageRoute,
        scenario: auditScenario,
        source,
      },
      work
    );
  }, [auditPageRoute, auditScenario]);

  useEffect(() => {
    const controller = new AbortController();
    const cachedEntry = getWorkspaceCacheEntry?.(workspaceCacheKey) ?? null;
    const seedEntry =
      cachedEntry ??
      (initialWorkspaceSeed
        ? {
            cacheKey: workspaceCacheKey,
            ticker: normalizedTicker,
            asOf: resolveWorkspaceAsOf(initialWorkspaceSeed, normalizedWorkspaceAsOf),
            updatedAt: Date.now(),
            payload: initialWorkspaceSeed,
          }
        : null);

    if (seedEntry) {
      applyWorkspaceResult(seedEntry.payload);
      setError(null);

      if (!cachedEntry) {
        setWorkspaceCacheEntry?.(seedEntry);
      }

      if (isWorkspaceCacheFresh(seedEntry)) {
        setLoading(false);
        setUpdating(false);
        return () => {
          controller.abort();
        };
      }

      setLoading(true);
      setUpdating(true);
    } else {
      setLoading(true);
      setUpdating(false);
      setError(null);
      clearWorkspaceResult();
      setChartConsoleEntries([]);
      setLastChartKey(null);
      setSettledJobIds([]);
      setRefreshTick(0);
    }

    async function load() {
      try {
        setLoading(true);
        setError(null);

        const result = await runWithAudit("company-workspace:initial-load", () =>
          loadCompanyWorkspaceData(normalizedTicker, {
            includeInsiders,
            includeInstitutional,
            includeOverviewBrief,
            includeEarningsSummary,
            financialsView: resolvedFinancialsView,
            signal: controller.signal,
          })
        );
        if (controller.signal.aborted) {
          return;
        }

        applyWorkspaceResult(result);
        setWorkspaceCacheEntry?.({
          cacheKey: workspaceCacheKey,
          ticker: normalizedTicker,
          asOf: resolveWorkspaceAsOf(result, normalizedWorkspaceAsOf),
          updatedAt: Date.now(),
          payload: result,
        });
      } catch (nextError) {
        if (!isAbortError(nextError)) {
          setError(asErrorMessage(nextError, "Unable to load company workspace"));
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
          setUpdating(false);
        }
      }
    }

    void load();
    return () => {
      controller.abort();
    };
  }, [
    applyWorkspaceResult,
    clearWorkspaceResult,
    getWorkspaceCacheEntry,
    includeEarningsSummary,
    includeInsiders,
    includeInstitutional,
    includeOverviewBrief,
    initialWorkspaceSeed,
    normalizedTicker,
    normalizedWorkspaceAsOf,
    resolvedFinancialsView,
    runWithAudit,
    setWorkspaceCacheEntry,
    workspaceCacheKey,
  ]);

  useEffect(() => {
    if (!activeJobId || !lastEvent) {
      return;
    }

    const isTerminal = lastEvent.status === "completed" || lastEvent.status === "failed";
    if (!isTerminal || settledJobIds.includes(activeJobId)) {
      return;
    }

    const controller = new AbortController();
    setSettledJobIds((current) => (current.includes(activeJobId) ? current : [...current, activeJobId]));
    setRefreshTick((current) => current + 1);
    invalidateApiReadCacheForTicker(normalizedTicker);
    invalidateWorkspaceCacheForTicker?.(normalizedTicker);

    void runWithAudit("company-workspace:reload-after-refresh", () =>
      loadCompanyWorkspaceData(normalizedTicker, {
        includeInsiders,
        includeInstitutional,
        includeOverviewBrief,
        includeEarningsSummary,
        financialsView: resolvedFinancialsView,
        signal: controller.signal,
      })
    )
      .then((result) => {
        if (controller.signal.aborted) {
          return;
        }

        setError(null);
        applyWorkspaceResult(result);
        setWorkspaceCacheEntry?.({
          cacheKey: workspaceCacheKey,
          ticker: normalizedTicker,
          asOf: resolveWorkspaceAsOf(result, normalizedWorkspaceAsOf),
          updatedAt: Date.now(),
          payload: result,
        });
      })
      .catch((nextError) => {
        if (!isAbortError(nextError)) {
          setError(asErrorMessage(nextError, "Unable to reload company workspace"));
        }
      });

    return () => {
      controller.abort();
    };
  }, [
    activeJobId,
    applyWorkspaceResult,
    includeEarningsSummary,
    includeInsiders,
    includeInstitutional,
    includeOverviewBrief,
    invalidateWorkspaceCacheForTicker,
    lastEvent,
    normalizedTicker,
    normalizedWorkspaceAsOf,
    resolvedFinancialsView,
    runWithAudit,
    setWorkspaceCacheEntry,
    settledJobIds,
    workspaceCacheKey,
  ]);

  useEffect(() => {
    if (!includeChartConsole) {
      setChartConsoleEntries([]);
      setLastChartKey(null);
      return;
    }

    const nextChartKey = `${ticker}:${financials[0]?.period_end ?? "none"}:${financials.length}:${priceHistory.at(-1)?.date ?? "none"}:${priceHistory.length}`;
    if ((!financials.length && !priceHistory.length) || nextChartKey === lastChartKey) {
      return;
    }

    const timestamp = new Date().toISOString();
    setChartConsoleEntries((current) => [
      ...current,
      {
        id: `client-chart-${nextChartKey}`,
        timestamp,
        stage: "charts",
        message: "Preparing charts...",
        level: "info",
        status: "running",
        source: "client"
      }
    ]);
    setLastChartKey(nextChartKey);
  }, [financials, includeChartConsole, lastChartKey, priceHistory, ticker]);

  useEffect(() => {
    if (!trackedJobId) {
      return;
    }

    rememberActiveJob(trackedJobId, ticker);
  }, [ticker, trackedJobId]);

  const queueRefresh = useCallback(async (force = true) => {
    try {
      setRefreshing(true);
      invalidateApiReadCacheForTicker(normalizedTicker);
      invalidateWorkspaceCacheForTicker?.(normalizedTicker);
      const response = await runWithAudit("company-workspace:queue-refresh", () => refreshCompany(normalizedTicker, force));
      setError(null);
      setActiveJobId(response.refresh.job_id);
      setChartConsoleEntries([]);
      setSettledJobIds([]);
    } catch (nextError) {
      setError(asErrorMessage(nextError, "Unable to start refresh"));
    } finally {
      setRefreshing(false);
    }
  }, [invalidateWorkspaceCacheForTicker, normalizedTicker, runWithAudit]);

  useEffect(() => {
    function onCommandRefresh(event: Event) {
      const customEvent = event as CustomEvent<CommandPaletteTickerDetail>;
      if (customEvent.detail?.ticker !== ticker) {
        return;
      }
      void queueRefresh();
    }

    window.addEventListener(COMMAND_PALETTE_REFRESH_EVENT, onCommandRefresh as EventListener);
    return () => window.removeEventListener(COMMAND_PALETTE_REFRESH_EVENT, onCommandRefresh as EventListener);
  }, [queueRefresh, ticker]);

  const consoleEntries = useMemo(
    () => [...streamEntries, ...chartConsoleEntries].sort((left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp)),
    [chartConsoleEntries, streamEntries]
  );

  const mergedCompany = useMemo(() => {
    const baseCompany =
      data?.company ?? briefData?.company ?? institutionalData?.company ?? insiderData?.company ?? null;
    if (!baseCompany) {
      return null;
    }

    return {
      ...baseCompany,
      last_checked_insiders: insiderData?.company?.last_checked_insiders ?? baseCompany.last_checked_insiders,
      last_checked_institutional:
        institutionalData?.company?.last_checked_institutional ?? baseCompany.last_checked_institutional,
    };
  }, [briefData?.company, data?.company, insiderData?.company, institutionalData?.company]);

  useEffect(() => {
    if (!companyLayout) {
      return;
    }

    return companyLayout.registerPublisher();
  }, [companyLayout]);

  useEffect(() => {
    if (!companyLayout) {
      return;
    }

    if (companyLayout.company?.ticker?.toUpperCase() === normalizedTicker) {
      return;
    }

    companyLayout.setCompany(null);
  }, [companyLayout, normalizedTicker]);

  useEffect(() => {
    companyLayout?.setCompany(mergedCompany);
  }, [companyLayout, mergedCompany]);

  useEffect(() => {
    if (!mergedCompany?.ticker) {
      return;
    }

    recordRecentCompany({
      ticker: mergedCompany.ticker,
      name: mergedCompany.name,
      sector: mergedCompany.sector ?? mergedCompany.market_sector ?? null,
    });
  }, [mergedCompany?.market_sector, mergedCompany?.name, mergedCompany?.sector, mergedCompany?.ticker]);

  return {
    data,
    briefData,
    earningsSummaryData,
    company: mergedCompany,
    financials,
    priceHistory,
    annualStatements,
    fundamentalsTrendData,
    latestFinancial,
    insiderData,
    insiderTrades,
    institutionalData,
    institutionalHoldings,
    loading,
    updating,
    error,
    insiderError,
    institutionalError,
    refreshing,
    refreshState,
    activeJobId: trackedJobId,
    consoleEntries,
    connectionState,
    queueRefresh,
    reloadKey: `${refreshTick}:${data?.company?.last_checked ?? briefData?.generated_at ?? "none"}:${financials.length}:${priceHistory.length}:${briefData?.build_state ?? "none"}`
  };
}

function isWorkspaceCacheFresh(entry: { updatedAt: number; payload: LoadCompanyWorkspaceDataResult }): boolean {
  if (Date.now() - entry.updatedAt > WORKSPACE_LAYOUT_CACHE_TTL_MS) {
    return false;
  }

  const refreshStates = [
    entry.payload.financialData.refresh,
    entry.payload.briefData?.refresh ?? null,
    entry.payload.earningsSummaryData?.refresh ?? null,
    entry.payload.insiderData?.refresh ?? null,
    entry.payload.institutionalData?.refresh ?? null,
  ];

  return refreshStates.every((refreshState) => {
    if (!refreshState) {
      return true;
    }

    if (refreshState.job_id) {
      return false;
    }

    return refreshState.reason === "fresh" || refreshState.reason === "none";
  });
}

function resolveWorkspaceAsOf(
  result: LoadCompanyWorkspaceDataResult,
  explicitAsOf: string | null
): string | null {
  if (explicitAsOf) {
    return explicitAsOf;
  }

  return result.financialData.as_of ?? result.briefData?.as_of ?? null;
}

async function loadCompanyWorkspaceData(
  ticker: string,
  options: Pick<UseCompanyWorkspaceOptions, "includeInsiders" | "includeInstitutional" | "includeOverviewBrief" | "includeEarningsSummary" | "financialsView"> & { signal?: AbortSignal }
): Promise<LoadCompanyWorkspaceDataResult> {
  const financialsView = options.financialsView ?? (options.includeOverviewBrief && !options.includeInsiders && !options.includeInstitutional ? "core_segments" : "full");
  try {
    const bootstrap = await getCompanyWorkspaceBootstrap(ticker, {
      financialsView,
      priceLatestN: WORKSPACE_PRICE_HISTORY_LATEST_N,
      priceMaxPoints: WORKSPACE_PRICE_HISTORY_MAX_POINTS,
      includeOverviewBrief: options.includeOverviewBrief,
      includeInsiders: options.includeInsiders,
      includeInstitutional: options.includeInstitutional,
      includeEarningsSummary: options.includeEarningsSummary,
      signal: options.signal,
    });
    return mapBootstrapToWorkspaceResult(bootstrap);
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }
    if (!shouldUseCompatibilityFallback(error)) {
      throw error;
    }
  }

  return loadCompanyWorkspaceDataLegacy(ticker, options, financialsView);
}

function mapBootstrapToWorkspaceResult(bootstrap: CompanyWorkspaceBootstrapResponse): LoadCompanyWorkspaceDataResult {
  let activeJobId = bootstrap.financials.refresh.job_id ?? bootstrap.brief?.refresh.job_id ?? null;
  activeJobId = activeJobId ?? bootstrap.institutional_holdings?.refresh.job_id ?? null;
  activeJobId = activeJobId ?? bootstrap.insider_trades?.refresh.job_id ?? null;
  activeJobId = activeJobId ?? bootstrap.earnings_summary?.refresh.job_id ?? null;

  return {
    financialData: bootstrap.financials,
    briefData: bootstrap.brief,
    earningsSummaryData: bootstrap.earnings_summary,
    insiderData: bootstrap.insider_trades,
    institutionalData: bootstrap.institutional_holdings,
    insiderError: bootstrap.errors.insider,
    institutionalError: bootstrap.errors.institutional,
    activeJobId,
  };
}

async function loadCompanyWorkspaceDataLegacy(
  ticker: string,
  options: Pick<UseCompanyWorkspaceOptions, "includeInsiders" | "includeInstitutional" | "includeOverviewBrief" | "includeEarningsSummary" | "financialsView"> & { signal?: AbortSignal },
  financialsView: "full" | "core_segments" | "core"
): Promise<LoadCompanyWorkspaceDataResult> {
  let financialData: CompanyFinancialsResponse;
  let briefData: CompanyResearchBriefResponse | null = null;
  let earningsSummaryData: CompanyEarningsSummaryResponse | null = null;
  if (options.includeOverviewBrief && !options.includeInsiders && !options.includeInstitutional) {
    try {
      const overviewData = await getCompanyOverview(ticker, {
        financialsView,
        priceLatestN: WORKSPACE_PRICE_HISTORY_LATEST_N,
        priceMaxPoints: WORKSPACE_PRICE_HISTORY_MAX_POINTS,
        signal: options.signal,
      });
      financialData = overviewData.financials;
      briefData = overviewData.brief;
    } catch (error) {
      if (isAbortError(error)) {
        throw error;
      }
      if (!shouldUseCompatibilityFallback(error)) {
        throw error;
      }
      financialData = await getCompanyFinancials(ticker, {
        view: financialsView,
        priceLatestN: WORKSPACE_PRICE_HISTORY_LATEST_N,
        priceMaxPoints: WORKSPACE_PRICE_HISTORY_MAX_POINTS,
        signal: options.signal,
      });
    }
  } else {
    financialData = await getCompanyFinancials(ticker, {
      view: financialsView,
      priceLatestN: WORKSPACE_PRICE_HISTORY_LATEST_N,
      priceMaxPoints: WORKSPACE_PRICE_HISTORY_MAX_POINTS,
      signal: options.signal,
    });
  }
  let activeJobId = financialData.refresh.job_id ?? briefData?.refresh.job_id ?? null;
  let insiderData: CompanyInsiderTradesResponse | null = null;
  let institutionalData: CompanyInstitutionalHoldingsResponse | null = null;
  let insiderError: string | null = null;
  let institutionalError: string | null = null;

  const [institutionalResult, insiderResult, earningsSummaryResult] = await Promise.allSettled([
    options.includeInstitutional ? getCompanyInstitutionalHoldings(ticker, { signal: options.signal }) : Promise.resolve(null),
    options.includeInsiders ? getCompanyInsiderTrades(ticker, { signal: options.signal }) : Promise.resolve(null),
    options.includeEarningsSummary ? getCompanyEarningsSummary(ticker, { signal: options.signal }) : Promise.resolve(null),
  ]);

  if (isRejectedAbort(institutionalResult) || isRejectedAbort(insiderResult) || isRejectedAbort(earningsSummaryResult)) {
    throw abortError();
  }

  if (institutionalResult.status === "fulfilled") {
    institutionalData = institutionalResult.value;
    activeJobId = activeJobId ?? institutionalData?.refresh.job_id ?? null;
  } else {
    institutionalError = asErrorMessage(institutionalResult.reason, "Unable to load institutional holdings");
  }

  if (insiderResult.status === "fulfilled") {
    insiderData = insiderResult.value;
    activeJobId = activeJobId ?? insiderData?.refresh.job_id ?? null;
  } else {
    insiderError = asErrorMessage(insiderResult.reason, "Unable to load insider trades");
  }

  if (earningsSummaryResult.status === "fulfilled") {
    earningsSummaryData = earningsSummaryResult.value;
    activeJobId = activeJobId ?? earningsSummaryData?.refresh.job_id ?? null;
  }

  return {
    financialData,
    briefData,
    earningsSummaryData,
    insiderData,
    institutionalData,
    insiderError,
    institutionalError,
    activeJobId
  };
}

function asErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function shouldUseCompatibilityFallback(error: unknown): boolean {
  const status = getApiErrorStatus(error);
  return status != null && COMPATIBILITY_FALLBACK_STATUSES.has(status);
}

function isAbortError(error: unknown): boolean {
  return (
    (typeof DOMException !== "undefined" && error instanceof DOMException && error.name === "AbortError") ||
    (error instanceof Error && error.name === "AbortError")
  );
}

function isRejectedAbort<T>(result: PromiseSettledResult<T>): boolean {
  return result.status === "rejected" && isAbortError(result.reason);
}

function abortError(): DOMException | Error {
  if (typeof DOMException !== "undefined") {
    return new DOMException("The operation was aborted.", "AbortError");
  }

  const error = new Error("The operation was aborted.");
  error.name = "AbortError";
  return error;
}

function getApiErrorStatus(error: unknown): number | null {
  if (!(error instanceof Error)) {
    return null;
  }

  const match = /^API request failed: (\d{3})\b/.exec(error.message);
  if (!match) {
    return null;
  }

  const status = Number.parseInt(match[1], 10);
  return Number.isFinite(status) ? status : null;
}
