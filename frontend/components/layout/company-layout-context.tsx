"use client";

import { createContext, useCallback, useContext, useMemo, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";

import type {
  CompanyEarningsSummaryResponse,
  CompanyFinancialsResponse,
  CompanyInsiderTradesResponse,
  CompanyInstitutionalHoldingsResponse,
  CompanyPayload,
  CompanyResearchBriefResponse,
} from "@/lib/types";

interface CompanyWorkspaceCachePayload {
  financialData: CompanyFinancialsResponse;
  briefData: CompanyResearchBriefResponse | null;
  earningsSummaryData: CompanyEarningsSummaryResponse | null;
  insiderData: CompanyInsiderTradesResponse | null;
  institutionalData: CompanyInstitutionalHoldingsResponse | null;
  insiderError: string | null;
  institutionalError: string | null;
  activeJobId: string | null;
}

type CompanyWorkspaceCacheEntry = {
  cacheKey: string;
  ticker: string;
  asOf: string | null;
  updatedAt: number;
  payload: CompanyWorkspaceCachePayload;
};

type CompanyWorkspaceCacheKeyInput = {
  ticker: string;
  financialsView: "full" | "core_segments" | "core";
  includeInsiders: boolean;
  includeInstitutional: boolean;
  includeOverviewBrief: boolean;
  includeEarningsSummary: boolean;
  asOf?: string | null;
};

interface CompanyLayoutContextValue {
  company: CompanyPayload | null;
  publisherCount: number;
  registerPublisher: () => () => void;
  setCompany: Dispatch<SetStateAction<CompanyPayload | null>>;
  getWorkspaceCacheEntry: (cacheKey: string) => CompanyWorkspaceCacheEntry | null;
  setWorkspaceCacheEntry: (entry: CompanyWorkspaceCacheEntry) => void;
  invalidateWorkspaceCacheForTicker: (ticker: string) => void;
}

const CompanyLayoutContext = createContext<CompanyLayoutContextValue | null>(null);

export function buildCompanyWorkspaceCacheKey({
  ticker,
  financialsView,
  includeInsiders,
  includeInstitutional,
  includeOverviewBrief,
  includeEarningsSummary,
  asOf,
}: CompanyWorkspaceCacheKeyInput): string {
  return [
    ticker.toUpperCase(),
    `view=${financialsView}`,
    `insiders=${includeInsiders ? "1" : "0"}`,
    `institutional=${includeInstitutional ? "1" : "0"}`,
    `overviewBrief=${includeOverviewBrief ? "1" : "0"}`,
    `earningsSummary=${includeEarningsSummary ? "1" : "0"}`,
    `asOf=${asOf ?? "latest"}`,
  ].join("|");
}

export function CompanyLayoutProvider({ children }: { children: ReactNode }) {
  const [company, setCompany] = useState<CompanyPayload | null>(null);
  const [publisherCount, setPublisherCount] = useState(0);
  const [workspaceCache, setWorkspaceCache] = useState<Map<string, CompanyWorkspaceCacheEntry>>(() => new Map());

  const registerPublisher = useCallback(() => {
    setPublisherCount((current) => current + 1);
    return () => {
      setPublisherCount((current) => Math.max(0, current - 1));
    };
  }, []);

  const getWorkspaceCacheEntry = useCallback(
    (cacheKey: string) => workspaceCache.get(cacheKey) ?? null,
    [workspaceCache]
  );

  const setWorkspaceCacheEntry = useCallback((entry: CompanyWorkspaceCacheEntry) => {
    setWorkspaceCache((current) => {
      const next = new Map(current);
      next.set(entry.cacheKey, entry);
      return next;
    });
  }, []);

  const invalidateWorkspaceCacheForTicker = useCallback((ticker: string) => {
    const normalizedTicker = ticker.toUpperCase();
    setWorkspaceCache((current) => {
      let removedAny = false;
      const next = new Map<string, CompanyWorkspaceCacheEntry>();
      for (const [cacheKey, entry] of current.entries()) {
        if (entry.ticker === normalizedTicker) {
          removedAny = true;
          continue;
        }
        next.set(cacheKey, entry);
      }
      return removedAny ? next : current;
    });
  }, []);

  const value = useMemo(
    () => ({
      company,
      publisherCount,
      registerPublisher,
      setCompany,
      getWorkspaceCacheEntry,
      setWorkspaceCacheEntry,
      invalidateWorkspaceCacheForTicker,
    }),
    [
      company,
      getWorkspaceCacheEntry,
      invalidateWorkspaceCacheForTicker,
      publisherCount,
      registerPublisher,
      setWorkspaceCacheEntry,
    ]
  );

  return <CompanyLayoutContext.Provider value={value}>{children}</CompanyLayoutContext.Provider>;
}

export function useCompanyLayoutContext(): CompanyLayoutContextValue | null {
  return useContext(CompanyLayoutContext);
}
