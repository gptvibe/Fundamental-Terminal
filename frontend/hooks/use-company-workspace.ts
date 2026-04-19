"use client";

import { useEffect, useMemo, useState } from "react";

import { useCompanyLayoutContext } from "@/components/layout/company-layout-context";
import { useJobStream } from "@/hooks/use-job-stream";
import { rememberActiveJob } from "@/lib/active-job";
import {
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
  auditPageRoute?: string;
  auditScenario?: string;
}

interface LoadCompanyWorkspaceDataResult {
  financialData: CompanyFinancialsResponse;
  briefData: CompanyResearchBriefResponse | null;
  earningsSummaryData: CompanyEarningsSummaryResponse | null;
  insiderData: CompanyInsiderTradesResponse | null;
  institutionalData: CompanyInstitutionalHoldingsResponse | null;
  insiderError: string | null;
  institutionalError: string | null;
  activeJobId: string | null;
}

export function useCompanyWorkspace(
  ticker: string,
  {
    includeInsiders = false,
    includeInstitutional = false,
    includeOverviewBrief = false,
    includeEarningsSummary = false,
    includeChartConsole = false,
    financialsView,
    auditPageRoute,
    auditScenario,
  }: UseCompanyWorkspaceOptions = {}
) {
  const [data, setData] = useState<CompanyFinancialsResponse | null>(null);
  const [briefData, setBriefData] = useState<CompanyResearchBriefResponse | null>(null);
  const [earningsSummaryData, setEarningsSummaryData] = useState<CompanyEarningsSummaryResponse | null>(null);
  const [insiderData, setInsiderData] = useState<CompanyInsiderTradesResponse | null>(null);
  const [institutionalData, setInstitutionalData] = useState<CompanyInstitutionalHoldingsResponse | null>(null);
  const [insiderError, setInsiderError] = useState<string | null>(null);
  const [institutionalError, setInstitutionalError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [chartConsoleEntries, setChartConsoleEntries] = useState<ConsoleEntry[]>([]);
  const [lastChartKey, setLastChartKey] = useState<string | null>(null);
  const [settledJobIds, setSettledJobIds] = useState<string[]>([]);
  const [refreshTick, setRefreshTick] = useState(0);
  const companyLayout = useCompanyLayoutContext();

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

  async function runWithAudit<T>(source: string, work: () => Promise<T>): Promise<T> {
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
  }

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        setBriefData(null);
        setEarningsSummaryData(null);
        setInsiderError(null);
        setInstitutionalError(null);
        setInsiderData(null);
        setInstitutionalData(null);
        setActiveJobId(null);
        setChartConsoleEntries([]);
        setLastChartKey(null);
        setSettledJobIds([]);
        setRefreshTick(0);

        const result = await runWithAudit("company-workspace:initial-load", () =>
          loadCompanyWorkspaceData(ticker, {
            includeInsiders,
            includeInstitutional,
            includeOverviewBrief,
            includeEarningsSummary,
            financialsView,
          })
        );
        if (cancelled) {
          return;
        }

        setData(result.financialData);
        setBriefData(result.briefData);
        setEarningsSummaryData(result.earningsSummaryData);
        setInsiderData(result.insiderData);
        setInstitutionalData(result.institutionalData);
        setInsiderError(result.insiderError);
        setInstitutionalError(result.institutionalError);
        setActiveJobId(result.activeJobId);
      } catch (nextError) {
        if (!cancelled) {
          setError(asErrorMessage(nextError, "Unable to load company workspace"));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [financialsView, includeEarningsSummary, includeInsiders, includeInstitutional, includeOverviewBrief, ticker]);

  useEffect(() => {
    if (!activeJobId || !lastEvent) {
      return;
    }

    const isTerminal = lastEvent.status === "completed" || lastEvent.status === "failed";
    if (!isTerminal || settledJobIds.includes(activeJobId)) {
      return;
    }

    let cancelled = false;
    setSettledJobIds((current) => (current.includes(activeJobId) ? current : [...current, activeJobId]));
    setRefreshTick((current) => current + 1);
    invalidateApiReadCacheForTicker(ticker);

    void runWithAudit("company-workspace:reload-after-refresh", () =>
      loadCompanyWorkspaceData(ticker, {
        includeInsiders,
        includeInstitutional,
        includeOverviewBrief,
        includeEarningsSummary,
        financialsView,
      })
    )
      .then((result) => {
        if (cancelled) {
          return;
        }

        setError(null);
        setData(result.financialData);
        setBriefData(result.briefData);
        setEarningsSummaryData(result.earningsSummaryData);
        setInsiderData(result.insiderData);
        setInstitutionalData(result.institutionalData);
        setInsiderError(result.insiderError);
        setInstitutionalError(result.institutionalError);
        setActiveJobId(result.activeJobId);
      })
      .catch((nextError) => {
        if (!cancelled) {
          setError(asErrorMessage(nextError, "Unable to reload company workspace"));
        }
      });

    return () => {
      cancelled = true;
    };
  }, [activeJobId, financialsView, includeEarningsSummary, includeInsiders, includeInstitutional, includeOverviewBrief, lastEvent, settledJobIds, ticker]);

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

  async function queueRefresh(force = true) {
    try {
      setRefreshing(true);
      invalidateApiReadCacheForTicker(ticker);
      const response = await runWithAudit("company-workspace:queue-refresh", () => refreshCompany(ticker, force));
      setError(null);
      setActiveJobId(response.refresh.job_id);
      setChartConsoleEntries([]);
      setSettledJobIds([]);
    } catch (nextError) {
      setError(asErrorMessage(nextError, "Unable to start refresh"));
    } finally {
      setRefreshing(false);
    }
  }

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
    companyLayout?.setCompany(null);
  }, [companyLayout, ticker]);

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

async function loadCompanyWorkspaceData(
  ticker: string,
  options: Pick<UseCompanyWorkspaceOptions, "includeInsiders" | "includeInstitutional" | "includeOverviewBrief" | "includeEarningsSummary" | "financialsView">
): Promise<LoadCompanyWorkspaceDataResult> {
  const financialsView = options.financialsView ?? (options.includeOverviewBrief && !options.includeInsiders && !options.includeInstitutional ? "core_segments" : "full");
  let financialData: CompanyFinancialsResponse;
  let briefData: CompanyResearchBriefResponse | null = null;
  let earningsSummaryData: CompanyEarningsSummaryResponse | null = null;
  if (options.includeOverviewBrief && !options.includeInsiders && !options.includeInstitutional) {
    try {
      const overviewData = await getCompanyOverview(ticker, { financialsView });
      financialData = overviewData.financials;
      briefData = overviewData.brief;
    } catch {
      financialData = await getCompanyFinancials(ticker, { view: financialsView });
    }
  } else {
    financialData = await getCompanyFinancials(ticker, { view: financialsView });
  }
  let activeJobId = financialData.refresh.job_id ?? briefData?.refresh.job_id ?? null;
  let insiderData: CompanyInsiderTradesResponse | null = null;
  let institutionalData: CompanyInstitutionalHoldingsResponse | null = null;
  let insiderError: string | null = null;
  let institutionalError: string | null = null;

  const [institutionalResult, insiderResult, earningsSummaryResult] = await Promise.allSettled([
    options.includeInstitutional ? getCompanyInstitutionalHoldings(ticker) : Promise.resolve(null),
    options.includeInsiders ? getCompanyInsiderTrades(ticker) : Promise.resolve(null),
    options.includeEarningsSummary ? getCompanyEarningsSummary(ticker) : Promise.resolve(null),
  ]);

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
