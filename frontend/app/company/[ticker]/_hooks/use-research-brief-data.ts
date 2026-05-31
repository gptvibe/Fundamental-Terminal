"use client";

import { useEffect, useRef, useState } from "react";

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

type FallbackSectionLoader = {
  key: keyof Pick<ResearchBriefDataState, "activityOverview" | "changes" | "earningsSummary" | "capitalStructure" | "capitalMarketsSummary" | "governanceSummary" | "ownershipSummary" | "models" | "peers">;
  fallbackMessage: string;
  load: () => Promise<unknown>;
};

function buildFallbackSectionLoaders(ticker: string, asOf: string | null): FallbackSectionLoader[] {
  return [
    {
      key: "activityOverview",
      fallbackMessage: "Unable to load activity overview",
      load: () => getCompanyActivityOverview(ticker),
    },
    {
      key: "changes",
      fallbackMessage: "Unable to load filing changes",
      load: () => getCompanyChangesSinceLastFiling(ticker, { asOf }),
    },
    {
      key: "earningsSummary",
      fallbackMessage: "Unable to load earnings summary",
      load: () => getCompanyEarningsSummary(ticker),
    },
    {
      key: "capitalStructure",
      fallbackMessage: "Unable to load capital structure",
      load: () => getCompanyCapitalStructure(ticker, { asOf }),
    },
    {
      key: "capitalMarketsSummary",
      fallbackMessage: "Unable to load capital markets summary",
      load: () => getCompanyCapitalMarketsSummary(ticker),
    },
    {
      key: "governanceSummary",
      fallbackMessage: "Unable to load governance summary",
      load: () => getCompanyGovernanceSummary(ticker),
    },
    {
      key: "ownershipSummary",
      fallbackMessage: "Unable to load ownership summary",
      load: () => getCompanyBeneficialOwnershipSummary(ticker),
    },
    {
      key: "models",
      fallbackMessage: "Unable to load valuation models",
      load: () => getCompanyModels(ticker, undefined, { asOf }),
    },
    {
      key: "peers",
      fallbackMessage: "Unable to load peer snapshot",
      load: () => getCompanyPeers(ticker, undefined, { asOf }),
    },
  ];
}

export function useResearchBriefData(
  ticker: string,
  reloadKey: string,
  retryToken: number,
  initialBrief: CompanyResearchBriefResponse | null,
  overviewBootstrapLoading: boolean,
  asOf: string | null,
  warmupJobId: string | null
): ResearchBriefDataState {
  const [state, setState] = useState<ResearchBriefDataState>(() =>
    initialBrief ? mapBriefResponseToAsyncState(initialBrief) : INITIAL_RESEARCH_BRIEF_DATA_STATE
  );
  const stateRef = useRef(state);

  stateRef.current = state;

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
          () => getCompanyResearchBrief(ticker, { asOf })
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
        const fallbackPlan = buildFallbackSectionLoaders(ticker, asOf);
        const pendingFallbacks = fallbackPlan.filter((loader) => previousStateNeedsData(stateRef.current, loader.key));

        if (pendingFallbacks.length === 0) {
          setState((previous) => ({
            ...previous,
            loading: false,
            error: message,
            buildState: previous.buildState === "ready" ? "ready" : "partial",
            buildStatus: previous.buildStatus ?? "Brief endpoint unavailable. Reusing persisted bootstrap data.",
          }));
          return;
        }

        const settled = await Promise.allSettled(pendingFallbacks.map((loader) => loader.load()));

        if (cancelled) {
          return;
        }

        setState((previous) => {
          const fallbackState: ResearchBriefDataState = {
            ...INITIAL_RESEARCH_BRIEF_DATA_STATE,
            ...previous,
            loading: false,
            buildState: "partial",
            buildStatus: "Brief endpoint unavailable. Loaded only the missing persisted section slices.",
            error: message,
          };

          pendingFallbacks.forEach((loader, index) => {
            const result = settled[index];
            if (!result) {
              return;
            }
            fallbackState[loader.key] = resolveAsyncState(previous[loader.key], result, loader.fallbackMessage) as never;
          });

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
  }, [asOf, initialBrief, overviewBootstrapLoading, reloadKey, retryToken, ticker, warmupJobId]);

  return state;
}

function previousStateNeedsData(
  state: ResearchBriefDataState,
  key: keyof Pick<ResearchBriefDataState, "activityOverview" | "changes" | "earningsSummary" | "capitalStructure" | "capitalMarketsSummary" | "governanceSummary" | "ownershipSummary" | "models" | "peers">
): boolean {
  const sectionState = state[key];
  return sectionState.data == null;
}
