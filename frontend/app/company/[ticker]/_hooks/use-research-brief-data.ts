"use client";

import { useEffect, useState } from "react";

import {
  getCompanyActivityOverview,
  getCompanyBeneficialOwnershipSummary,
  getCompanyCapitalMarketsSummary,
  getCompanyCapitalStructure,
  getCompanyChangesSinceLastFiling,
  getCompanyEarningsSummary,
  getCompanyGovernanceSummary,
  getCompanyModels,
  getCompanyPeers,
  getCompanyResearchBrief,
} from "@/lib/api";
import { withPerformanceAuditSource } from "@/lib/performance-audit";
import type { CompanyResearchBriefResponse } from "@/lib/types";

import { INITIAL_RESEARCH_BRIEF_DATA_STATE } from "../_lib/research-brief-types";
import type { ResearchBriefDataState } from "../_lib/research-brief-types";
import { mapBriefResponseToAsyncState, resolveAsyncState } from "../_lib/research-brief-utils";

export function useResearchBriefData(
  ticker: string,
  reloadKey: string,
  retryToken: number,
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
        const settled = await Promise.allSettled([
          getCompanyActivityOverview(ticker),
          getCompanyChangesSinceLastFiling(ticker, { asOf: null }),
          getCompanyEarningsSummary(ticker),
          getCompanyCapitalStructure(ticker, { asOf: null }),
          getCompanyCapitalMarketsSummary(ticker),
          getCompanyGovernanceSummary(ticker),
          getCompanyBeneficialOwnershipSummary(ticker),
          getCompanyModels(ticker, undefined, { asOf: null }),
          getCompanyPeers(ticker, undefined, { asOf: null }),
        ] as const);

        if (cancelled) {
          return;
        }

        setState((previous) => {
          const fallbackState: ResearchBriefDataState = {
            ...INITIAL_RESEARCH_BRIEF_DATA_STATE,
            loading: false,
            buildState: "partial",
            buildStatus: "Brief endpoint unavailable. Loaded persisted section slices independently.",
            error: message,
            activityOverview: resolveAsyncState(previous.activityOverview, settled[0], "Unable to load activity overview"),
            changes: resolveAsyncState(previous.changes, settled[1], "Unable to load filing changes"),
            earningsSummary: resolveAsyncState(previous.earningsSummary, settled[2], "Unable to load earnings summary"),
            capitalStructure: resolveAsyncState(previous.capitalStructure, settled[3], "Unable to load capital structure"),
            capitalMarketsSummary: resolveAsyncState(previous.capitalMarketsSummary, settled[4], "Unable to load capital markets summary"),
            governanceSummary: resolveAsyncState(previous.governanceSummary, settled[5], "Unable to load governance summary"),
            ownershipSummary: resolveAsyncState(previous.ownershipSummary, settled[6], "Unable to load ownership summary"),
            models: resolveAsyncState(previous.models, settled[7], "Unable to load valuation models"),
            peers: resolveAsyncState(previous.peers, settled[8], "Unable to load peer snapshot"),
          };

          const hasAnyFallbackData = Boolean(
            fallbackState.activityOverview.data ||
              fallbackState.changes.data ||
              fallbackState.earningsSummary.data ||
              fallbackState.capitalStructure.data ||
              fallbackState.capitalMarketsSummary.data ||
              fallbackState.governanceSummary.data ||
              fallbackState.ownershipSummary.data ||
              fallbackState.models.data ||
              fallbackState.peers.data
          );

          if (!hasAnyFallbackData) {
            return {
              ...fallbackState,
              activityOverview: { data: null, error: message, loading: false },
              changes: { data: null, error: message, loading: false },
              earningsSummary: { data: null, error: message, loading: false },
              capitalStructure: { data: null, error: message, loading: false },
              capitalMarketsSummary: { data: null, error: message, loading: false },
              governanceSummary: { data: null, error: message, loading: false },
              ownershipSummary: { data: null, error: message, loading: false },
              models: { data: null, error: message, loading: false },
              peers: { data: null, error: message, loading: false },
            };
          }

          return fallbackState;
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
  }, [initialBrief, overviewBootstrapLoading, reloadKey, retryToken, ticker, warmupJobId]);

  return state;
}
