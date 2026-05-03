"use client";

import { useEffect, useState } from "react";

import { getCompanyResearchBrief } from "@/lib/api";
import { withPerformanceAuditSource } from "@/lib/performance-audit";
import type { CompanyResearchBriefResponse } from "@/lib/types";

import { INITIAL_RESEARCH_BRIEF_DATA_STATE } from "../_lib/research-brief-types";
import type { ResearchBriefDataState } from "../_lib/research-brief-types";
import { mapBriefResponseToAsyncState } from "../_lib/research-brief-utils";

export function useResearchBriefData(
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
