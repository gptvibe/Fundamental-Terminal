"use client";

import { useEffect, useMemo, useState } from "react";

import { useJobStream } from "@/hooks/use-job-stream";
import { getCompanyFinancials, getCompanyInsiderTrades, getCompanyInstitutionalHoldings, refreshCompany } from "@/lib/api";
import type {
  CompanyFinancialsResponse,
  CompanyInsiderTradesResponse,
  CompanyInstitutionalHoldingsResponse,
  ConsoleEntry,
  FundamentalsTrendPoint
} from "@/lib/types";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);

interface UseCompanyWorkspaceOptions {
  includeInsiders?: boolean;
  includeInstitutional?: boolean;
  includeChartConsole?: boolean;
}

interface LoadCompanyWorkspaceDataResult {
  financialData: CompanyFinancialsResponse;
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
    includeChartConsole = false
  }: UseCompanyWorkspaceOptions = {}
) {
  const [data, setData] = useState<CompanyFinancialsResponse | null>(null);
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
  const { consoleEntries: streamEntries, connectionState, lastEvent } = useJobStream(activeJobId);

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

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        setInsiderError(null);
        setInstitutionalError(null);
        setInsiderData(null);
        setInstitutionalData(null);
        setActiveJobId(null);
        setChartConsoleEntries([]);
        setLastChartKey(null);
        setSettledJobIds([]);

        const result = await loadCompanyWorkspaceData(ticker, { includeInsiders, includeInstitutional });
        if (cancelled) {
          return;
        }

        setData(result.financialData);
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
  }, [includeInsiders, includeInstitutional, ticker]);

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

    void loadCompanyWorkspaceData(ticker, { includeInsiders, includeInstitutional })
      .then((result) => {
        if (cancelled) {
          return;
        }

        setData(result.financialData);
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
  }, [activeJobId, includeInsiders, includeInstitutional, lastEvent, settledJobIds, ticker]);

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

  async function queueRefresh(force = false) {
    try {
      setRefreshing(true);
      const response = await refreshCompany(ticker, force);
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

  return {
    data,
    company: data?.company ?? institutionalData?.company ?? insiderData?.company ?? null,
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
    refreshState: data?.refresh ?? institutionalData?.refresh ?? insiderData?.refresh ?? null,
    activeJobId,
    consoleEntries,
    connectionState,
    queueRefresh,
    reloadKey: `${data?.company?.last_checked ?? "none"}:${financials.length}:${priceHistory.length}`
  };
}

async function loadCompanyWorkspaceData(
  ticker: string,
  options: Pick<UseCompanyWorkspaceOptions, "includeInsiders" | "includeInstitutional">
): Promise<LoadCompanyWorkspaceDataResult> {
  const financialData = await getCompanyFinancials(ticker);
  let activeJobId = financialData.refresh.job_id;
  let insiderData: CompanyInsiderTradesResponse | null = null;
  let institutionalData: CompanyInstitutionalHoldingsResponse | null = null;
  let insiderError: string | null = null;
  let institutionalError: string | null = null;

  if (!activeJobId && options.includeInstitutional) {
    try {
      institutionalData = await getCompanyInstitutionalHoldings(ticker);
      activeJobId = institutionalData.refresh.job_id;
    } catch (nextError) {
      institutionalError = asErrorMessage(nextError, "Unable to load institutional holdings");
    }
  }

  if (!activeJobId && options.includeInsiders) {
    try {
      insiderData = await getCompanyInsiderTrades(ticker);
      activeJobId = insiderData.refresh.job_id;
    } catch (nextError) {
      insiderError = asErrorMessage(nextError, "Unable to load insider trades");
    }
  }

  return {
    financialData,
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
