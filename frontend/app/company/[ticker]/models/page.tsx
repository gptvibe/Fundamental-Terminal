"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import dynamic from "next/dynamic";
import type { ColDef } from "ag-grid-community";

import { CapitalStructureIntelligencePanel } from "@/components/company/capital-structure-intelligence-panel";
import { useCompanyLayoutContext } from "@/components/layout/company-layout-context";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyResearchHeader } from "@/components/layout/company-research-header";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { MarketContextPanel } from "@/components/models/market-context-panel";
import { ModelEvaluationPanel } from "@/components/models/model-evaluation-panel";
import { SectorContextPanel } from "@/components/models/sector-context-panel";
import { DeferredClientSection } from "@/components/performance/deferred-client-section";
import { ForecastTrustCue } from "@/components/ui/forecast-trust-cue";
import { CommercialFallbackNotice } from "@/components/ui/commercial-fallback-notice";
import { DataQualityDiagnostics } from "@/components/ui/data-quality-diagnostics";
import { Panel } from "@/components/ui/panel";
import { SourceFreshnessSummary } from "@/components/ui/source-freshness-summary";
import { useForecastAccuracy } from "@/hooks/use-forecast-accuracy";
import { useJobStream } from "@/hooks/use-job-stream";
import { rememberActiveJob } from "@/lib/active-job";
import { showAppToast } from "@/lib/app-toast";
import { getCompanyCapitalStructure, getCompanyChartsForecastAccuracy, getCompanyFinancials, getCompanyMarketContext, getCompanyModels, getCompanyOilScenarioOverlay, getCompanySectorContext, getLatestModelEvaluation, invalidateApiReadCacheForTicker, refreshCompany } from "@/lib/api";
import { MODEL_NAMES } from "@/lib/constants";
import { downloadJsonFile, normalizeExportFileStem } from "@/lib/export";
import { FORECAST_HANDOFF_QUERY_PARAM, decodeForecastHandoffPayload, type ForecastHandoffMetric, type ForecastHandoffPayload } from "@/lib/forecast-handoff";
import { resolveForecastHandoffSourceState } from "@/lib/forecast-source-state";
import { formatCompactNumber, formatDate, formatPercent, titleCase } from "@/lib/format";
import { describeOilOverlayAvailability, describeOilSupportReason, resolveOilOverlayEvaluationSummary, supportsOilWorkspace } from "@/lib/oil-workspace";
import { withPerformanceAuditSource } from "@/lib/performance-audit";
import { formatPiotroskiDisplay, resolvePiotroskiScoreState } from "@/lib/piotroski";
import type { CompanyCapitalStructureResponse, CompanyChartsForecastAccuracyResponse, CompanyFinancialsResponse, CompanyMarketContextResponse, CompanyModelsResponse, CompanyOilScenarioResponse, CompanySectorContextResponse, ModelEvaluationResponse, ModelPayload } from "@/lib/types";
import { describeDcfDisplayCaveat, resolveDcfDisplayState } from "@/lib/valuation-models";

interface ModelsCoreData {
  modelData: CompanyModelsResponse;
  financialData: CompanyFinancialsResponse;
  activeJobId: string | null;
}

type OptionalPanelState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "unavailable" }
  | { status: "failed"; error: string }
  | { status: "disabled" };

type OptionalPanelKey = "marketContext" | "sectorContext" | "capitalStructure" | "modelEvaluation" | "oilScenarioOverlay" | "oilOverlayEvaluation";

type OptionalPanelStates = {
  marketContext: OptionalPanelState<CompanyMarketContextResponse>;
  sectorContext: OptionalPanelState<CompanySectorContextResponse>;
  capitalStructure: OptionalPanelState<CompanyCapitalStructureResponse>;
  modelEvaluation: OptionalPanelState<ModelEvaluationResponse>;
  oilScenarioOverlay: OptionalPanelState<CompanyOilScenarioResponse>;
  oilOverlayEvaluation: OptionalPanelState<ModelEvaluationResponse>;
};

type OptionalPanelActivation = Record<OptionalPanelKey, boolean>;

const OIL_OVERLAY_EVALUATION_SUITE_KEY = "oil_overlay_point_in_time_v1";

const InvestmentSummaryPanel = dynamic(
  () => import("@/components/models/investment-summary-panel").then((module) => module.InvestmentSummaryPanel),
  { ssr: false }
);
const FinancialHealthScore = dynamic(
  () => import("@/components/models/financial-health-score").then((module) => module.FinancialHealthScore),
  { ssr: false }
);
const ValuationScenarioWorkbench = dynamic(
  () => import("@/components/models/valuation-scenario-workbench").then((module) => module.ValuationScenarioWorkbench),
  { ssr: false }
);
const ModelDashboard = dynamic(
  () => import("@/components/models/model-dashboard").then((module) => module.ModelDashboard),
  { ssr: false }
);
const DenseGrid = dynamic(
  () => import("@/components/grid/dense-grid").then((module) => module.DenseGrid),
  { ssr: false, loading: () => <div className="text-muted">Initializing advanced grid...</div> }
);

type DupontMode = "auto" | "annual" | "ttm";

const INITIAL_OPTIONAL_ACTIVATION: OptionalPanelActivation = {
  marketContext: false,
  sectorContext: false,
  capitalStructure: false,
  modelEvaluation: false,
  oilScenarioOverlay: false,
  oilOverlayEvaluation: false,
};

function createInitialOptionalPanelStates(oilPanelEnabled: boolean): OptionalPanelStates {
  return {
    marketContext: { status: "idle" },
    sectorContext: { status: "idle" },
    capitalStructure: { status: "idle" },
    modelEvaluation: { status: "idle" },
    oilScenarioOverlay: oilPanelEnabled ? { status: "idle" } : { status: "disabled" },
    oilOverlayEvaluation: oilPanelEnabled ? { status: "idle" } : { status: "disabled" },
  };
}

export default function CompanyModelsPage() {
  const params = useParams<{ ticker: string }>();
  const searchParams = useSearchParams();
  const ticker = decodeURIComponent(params.ticker).toUpperCase();
  const companyLayout = useCompanyLayoutContext();
  const [data, setData] = useState<CompanyModelsResponse | null>(null);
  const [financialData, setFinancialData] = useState<CompanyFinancialsResponse | null>(null);
  const [optionalPanelStates, setOptionalPanelStates] = useState<OptionalPanelStates>(() => createInitialOptionalPanelStates(true));
  const [optionalPanelActivation, setOptionalPanelActivation] = useState<OptionalPanelActivation>(INITIAL_OPTIONAL_ACTIVATION);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [settledJobIds, setSettledJobIds] = useState<string[]>([]);
  const [dupontMode, setDupontMode] = useState<DupontMode>("auto");
  const [showModeInfo, setShowModeInfo] = useState(false);
  const [exportingModelOutputs, setExportingModelOutputs] = useState(false);
  const optionalPanelControllersRef = useRef<Partial<Record<OptionalPanelKey, AbortController>>>({});
  const { consoleEntries, connectionState, lastEvent } = useJobStream(activeJobId);
  const models = useMemo(() => data?.models ?? [], [data?.models]);
  const hasModels = models.length > 0;
  const marketContextData = optionalPanelStates.marketContext.status === "ready" ? optionalPanelStates.marketContext.data : null;
  const sectorContextData = optionalPanelStates.sectorContext.status === "ready" ? optionalPanelStates.sectorContext.data : null;
  const capitalStructureData = optionalPanelStates.capitalStructure.status === "ready" ? optionalPanelStates.capitalStructure.data : null;
  const oilScenarioOverlayData = optionalPanelStates.oilScenarioOverlay.status === "ready" ? optionalPanelStates.oilScenarioOverlay.data : null;
  const evaluationData = optionalPanelStates.modelEvaluation.status === "ready" ? optionalPanelStates.modelEvaluation.data : null;
  const oilOverlayEvaluationData = optionalPanelStates.oilOverlayEvaluation.status === "ready" ? optionalPanelStates.oilOverlayEvaluation.data : null;
  const strictOfficialMode = Boolean(data?.company?.strict_official_mode ?? financialData?.company?.strict_official_mode);
  const oilSupportStatus = data?.company?.oil_support_status ?? financialData?.company?.oil_support_status ?? "unsupported";
  const oilSupportReasons = data?.company?.oil_support_reasons ?? financialData?.company?.oil_support_reasons ?? [];
  const showOilScenarioOverlay = supportsOilWorkspace(oilSupportStatus);
  const oilWorkspaceEvaluationSummary = useMemo(() => resolveOilOverlayEvaluationSummary(ticker, oilOverlayEvaluationData), [ticker, oilOverlayEvaluationData]);
  const sharedCompany = useMemo(() => data?.company ?? financialData?.company ?? null, [data?.company, financialData?.company]);
  const forecastHandoff = useMemo(() => {
    const decoded = decodeForecastHandoffPayload(searchParams?.get(FORECAST_HANDOFF_QUERY_PARAM) ?? null);
    if (!decoded) {
      return null;
    }
    return decoded.ticker.toUpperCase() === ticker ? decoded : null;
  }, [searchParams, ticker]);
  const forecastAccuracy = useForecastAccuracy(ticker, {
    asOf: forecastHandoff?.asOf,
    enabled: Boolean(forecastHandoff),
  });

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
    companyLayout?.setCompany(sharedCompany);
  }, [companyLayout, sharedCompany]);

  const activateOptionalPanel = useCallback((panel: OptionalPanelKey) => {
    setOptionalPanelActivation((current) => {
      if (current[panel]) {
        return current;
      }
      return {
        ...current,
        [panel]: true,
      };
    });
  }, []);

  const abortOptionalPanelRequests = useCallback((panels?: OptionalPanelKey[]) => {
    const targets = panels ?? (Object.keys(optionalPanelControllersRef.current) as OptionalPanelKey[]);
    targets.forEach((panel) => {
      optionalPanelControllersRef.current[panel]?.abort();
      delete optionalPanelControllersRef.current[panel];
    });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    abortOptionalPanelRequests();

    async function load() {
      try {
        setLoading(true);
        setError(null);
        setSettledJobIds([]);
        setOptionalPanelActivation(INITIAL_OPTIONAL_ACTIVATION);
        const workspaceData = await withPerformanceAuditSource(
          {
            pageRoute: "/company/[ticker]/models",
            scenario: "models_page",
            source: "models:workspace-load",
          },
          () => loadModelsCoreData(ticker, dupontMode, controller.signal)
        );
        if (!controller.signal.aborted) {
          setData(workspaceData.modelData);
          setFinancialData(workspaceData.financialData);
          const oilPanelEnabled = supportsOilWorkspace(
            workspaceData.modelData.company?.oil_support_status ?? workspaceData.financialData.company?.oil_support_status ?? "unsupported"
          );
          setOptionalPanelStates(createInitialOptionalPanelStates(oilPanelEnabled));
          setActiveJobId(workspaceData.activeJobId);
        }
      } catch (nextError) {
        if (!isAbortError(nextError)) {
          setError(nextError instanceof Error ? nextError.message : "Unable to load models");
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      controller.abort();
    };
  }, [abortOptionalPanelRequests, ticker, dupontMode]);

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
    invalidateApiReadCacheForTicker(ticker);
    abortOptionalPanelRequests();

    void withPerformanceAuditSource(
      {
        pageRoute: "/company/[ticker]/models",
        scenario: "models_page",
        source: "models:reload-after-refresh",
      },
      () => loadModelsCoreData(ticker, dupontMode, controller.signal)
    )
      .then((workspaceData) => {
        if (controller.signal.aborted) {
          return;
        }
        setError(null);
        setData(workspaceData.modelData);
        setFinancialData(workspaceData.financialData);
        const oilPanelEnabled = supportsOilWorkspace(
          workspaceData.modelData.company?.oil_support_status ?? workspaceData.financialData.company?.oil_support_status ?? "unsupported"
        );
        setOptionalPanelStates(createInitialOptionalPanelStates(oilPanelEnabled));
        setOptionalPanelActivation(INITIAL_OPTIONAL_ACTIVATION);
        setActiveJobId(workspaceData.activeJobId);
      })
      .catch((nextError) => {
        if (!isAbortError(nextError)) {
          setError(nextError instanceof Error ? nextError.message : "Unable to reload models");
        }
      });

    return () => {
      controller.abort();
    };
  }, [abortOptionalPanelRequests, activeJobId, lastEvent, settledJobIds, ticker, dupontMode]);

  useEffect(() => {
    if (!activeJobId) {
      return;
    }

    rememberActiveJob(activeJobId, ticker);
  }, [activeJobId, ticker]);

  useEffect(() => {
    if (!data || !financialData) {
      return;
    }

    const requests: Array<() => void> = [];

    if (optionalPanelActivation.marketContext && optionalPanelStates.marketContext.status === "idle") {
      requests.push(() => {
        const controller = new AbortController();
        optionalPanelControllersRef.current.marketContext = controller;
        setOptionalPanelStates((current) => ({ ...current, marketContext: { status: "loading" } }));
        void withPerformanceAuditSource(
          {
            pageRoute: "/company/[ticker]/models",
            scenario: "models_page",
            source: "models:load-market-context",
          },
          () => getCompanyMarketContext(ticker, { signal: controller.signal })
        )
          .then((payload) => {
            if (controller.signal.aborted) {
              return;
            }
            setOptionalPanelStates((current) => ({
              ...current,
              marketContext: hasMeaningfulMarketContext(payload) ? { status: "ready", data: payload } : { status: "unavailable" },
            }));
          })
          .catch((nextError) => {
            if (isAbortError(nextError) || controller.signal.aborted) {
              return;
            }
            setOptionalPanelStates((current) => ({
              ...current,
              marketContext: { status: "failed", error: formatPanelError(nextError, "Unable to load macro exposure context.") },
            }));
          })
          .finally(() => {
            if (optionalPanelControllersRef.current.marketContext === controller) {
              delete optionalPanelControllersRef.current.marketContext;
            }
          });
      });
    }

    if (optionalPanelActivation.sectorContext && optionalPanelStates.sectorContext.status === "idle") {
      requests.push(() => {
        const controller = new AbortController();
        optionalPanelControllersRef.current.sectorContext = controller;
        setOptionalPanelStates((current) => ({ ...current, sectorContext: { status: "loading" } }));
        void withPerformanceAuditSource(
          {
            pageRoute: "/company/[ticker]/models",
            scenario: "models_page",
            source: "models:load-sector-context",
          },
          () => getCompanySectorContext(ticker, { signal: controller.signal })
        )
          .then((payload) => {
            if (controller.signal.aborted) {
              return;
            }
            setOptionalPanelStates((current) => ({
              ...current,
              sectorContext: (payload.plugins ?? []).length ? { status: "ready", data: payload } : { status: "unavailable" },
            }));
          })
          .catch((nextError) => {
            if (isAbortError(nextError) || controller.signal.aborted) {
              return;
            }
            setOptionalPanelStates((current) => ({
              ...current,
              sectorContext: { status: "failed", error: formatPanelError(nextError, "Unable to load sector exposure context.") },
            }));
          })
          .finally(() => {
            if (optionalPanelControllersRef.current.sectorContext === controller) {
              delete optionalPanelControllersRef.current.sectorContext;
            }
          });
      });
    }

    if (optionalPanelActivation.capitalStructure && optionalPanelStates.capitalStructure.status === "idle") {
      requests.push(() => {
        const controller = new AbortController();
        optionalPanelControllersRef.current.capitalStructure = controller;
        setOptionalPanelStates((current) => ({ ...current, capitalStructure: { status: "loading" } }));
        void withPerformanceAuditSource(
          {
            pageRoute: "/company/[ticker]/models",
            scenario: "models_page",
            source: "models:load-capital-structure",
          },
          () => getCompanyCapitalStructure(ticker, { maxPeriods: 6, signal: controller.signal })
        )
          .then((payload) => {
            if (controller.signal.aborted) {
              return;
            }
            setOptionalPanelStates((current) => ({
              ...current,
              capitalStructure: payload.latest ? { status: "ready", data: payload } : { status: "unavailable" },
            }));
          })
          .catch((nextError) => {
            if (isAbortError(nextError) || controller.signal.aborted) {
              return;
            }
            setOptionalPanelStates((current) => ({
              ...current,
              capitalStructure: { status: "failed", error: formatPanelError(nextError, "Unable to load capital structure intelligence.") },
            }));
          })
          .finally(() => {
            if (optionalPanelControllersRef.current.capitalStructure === controller) {
              delete optionalPanelControllersRef.current.capitalStructure;
            }
          });
      });
    }

    if (optionalPanelActivation.modelEvaluation && optionalPanelStates.modelEvaluation.status === "idle") {
      requests.push(() => {
        const controller = new AbortController();
        optionalPanelControllersRef.current.modelEvaluation = controller;
        setOptionalPanelStates((current) => ({ ...current, modelEvaluation: { status: "loading" } }));
        void withPerformanceAuditSource(
          {
            pageRoute: "/company/[ticker]/models",
            scenario: "models_page",
            source: "models:load-model-evaluation",
          },
          () => getLatestModelEvaluation(undefined, { signal: controller.signal })
        )
          .then((payload) => {
            if (controller.signal.aborted) {
              return;
            }
            setOptionalPanelStates((current) => ({ ...current, modelEvaluation: { status: "ready", data: payload } }));
          })
          .catch((nextError) => {
            if (isAbortError(nextError) || controller.signal.aborted) {
              return;
            }
            setOptionalPanelStates((current) => ({
              ...current,
              modelEvaluation: { status: "failed", error: formatPanelError(nextError, "Unable to load the model evaluation harness.") },
            }));
          })
          .finally(() => {
            if (optionalPanelControllersRef.current.modelEvaluation === controller) {
              delete optionalPanelControllersRef.current.modelEvaluation;
            }
          });
      });
    }

    const oilEnabled = supportsOilWorkspace(data.company?.oil_support_status ?? financialData.company?.oil_support_status ?? "unsupported");
    if (!oilEnabled) {
      if (optionalPanelStates.oilScenarioOverlay.status !== "disabled" || optionalPanelStates.oilOverlayEvaluation.status !== "disabled") {
        setOptionalPanelStates((current) => ({
          ...current,
          oilScenarioOverlay: { status: "disabled" },
          oilOverlayEvaluation: { status: "disabled" },
        }));
      }
    } else {
      if (optionalPanelActivation.oilScenarioOverlay && optionalPanelStates.oilScenarioOverlay.status === "idle") {
        requests.push(() => {
          const controller = new AbortController();
          optionalPanelControllersRef.current.oilScenarioOverlay = controller;
          setOptionalPanelStates((current) => ({ ...current, oilScenarioOverlay: { status: "loading" } }));
          void withPerformanceAuditSource(
            {
              pageRoute: "/company/[ticker]/models",
              scenario: "models_page",
              source: "models:load-oil-overlay",
            },
            () => getCompanyOilScenarioOverlay(ticker, { signal: controller.signal })
          )
            .then((payload) => {
              if (controller.signal.aborted) {
                return;
              }
              setOptionalPanelStates((current) => ({ ...current, oilScenarioOverlay: { status: "ready", data: payload } }));
            })
            .catch((nextError) => {
              if (isAbortError(nextError) || controller.signal.aborted) {
                return;
              }
              setOptionalPanelStates((current) => ({
                ...current,
                oilScenarioOverlay: { status: "failed", error: formatPanelError(nextError, "Unable to load oil workspace overlay inputs.") },
              }));
            })
            .finally(() => {
              if (optionalPanelControllersRef.current.oilScenarioOverlay === controller) {
                delete optionalPanelControllersRef.current.oilScenarioOverlay;
              }
            });
        });
      }

      if (optionalPanelActivation.oilOverlayEvaluation && optionalPanelStates.oilOverlayEvaluation.status === "idle") {
        requests.push(() => {
          const controller = new AbortController();
          optionalPanelControllersRef.current.oilOverlayEvaluation = controller;
          setOptionalPanelStates((current) => ({ ...current, oilOverlayEvaluation: { status: "loading" } }));
          void withPerformanceAuditSource(
            {
              pageRoute: "/company/[ticker]/models",
              scenario: "models_page",
              source: "models:load-oil-evaluation",
            },
            () => getLatestModelEvaluation(OIL_OVERLAY_EVALUATION_SUITE_KEY, { signal: controller.signal })
          )
            .then((payload) => {
              if (controller.signal.aborted) {
                return;
              }
              setOptionalPanelStates((current) => ({ ...current, oilOverlayEvaluation: { status: "ready", data: payload } }));
            })
            .catch((nextError) => {
              if (isAbortError(nextError) || controller.signal.aborted) {
                return;
              }
              setOptionalPanelStates((current) => ({
                ...current,
                oilOverlayEvaluation: { status: "failed", error: formatPanelError(nextError, "Unable to load oil overlay evaluation context.") },
              }));
            })
            .finally(() => {
              if (optionalPanelControllersRef.current.oilOverlayEvaluation === controller) {
                delete optionalPanelControllersRef.current.oilOverlayEvaluation;
              }
            });
        });
      }
    }

    requests.forEach((startRequest) => startRequest());
  }, [data, financialData, optionalPanelActivation, optionalPanelStates, ticker]);

  useEffect(() => {
    return () => {
      abortOptionalPanelRequests();
    };
  }, [abortOptionalPanelRequests]);

  const columns = useMemo<ColDef<ModelPayload>[]>(
    () => [
      { field: "model_name", headerName: "Model", minWidth: 150, valueFormatter: ({ value }) => titleCase(String(value ?? "")) },
      { field: "model_version", headerName: "Version", maxWidth: 120, cellStyle: { color: "var(--warning)", fontWeight: 700 } },
      {
        field: "created_at",
        headerName: "Computed",
        minWidth: 160,
        valueFormatter: ({ value }) => formatDate(value as string | null)
      },
      {
        field: "result.status",
        headerName: "Status",
        minWidth: 130,
        valueGetter: ({ data: row }) => row?.result?.model_status ?? row?.result?.status ?? "ready"
      }
    ],
    []
  );

  const modelSummary = useMemo(() => {
    const byName = Object.fromEntries(models.map((model) => [model.model_name, model])) as Record<string, ModelPayload | undefined>;
    const latestComputed = models
      .map((model) => model.created_at)
      .sort((left, right) => new Date(right).getTime() - new Date(left).getTime())[0] ?? null;
    const piotroskiState = resolvePiotroskiScoreState(byName.piotroski?.result);
    const dupontBasisRaw = byName.dupont?.result?.basis;
    const dcfState = resolveDcfDisplayState(byName.dcf);

    return {
      cachedCount: models.length,
      latestComputed,
      dcfEnterpriseValue: dcfState.enterpriseValue,
      dcfEnterpriseLabel: dcfState.isEnterpriseValueProxy ? "DCF EV Proxy" : "DCF EV",
      dcfCaveat: describeDcfDisplayCaveat(dcfState),
      dupontRoe: asNumber(byName.dupont?.result?.return_on_equity),
      dupontBasis: typeof dupontBasisRaw === "string" ? dupontBasisRaw.toUpperCase() : null,
      piotroskiLabel: formatPiotroskiDisplay(piotroskiState),
      altmanZ: asNumber(byName.altman_z?.result?.z_score_approximate)
    };
  }, [models]);

  async function queueRefresh() {
    try {
      setRefreshing(true);
      const response = await withPerformanceAuditSource(
        {
          pageRoute: "/company/[ticker]/models",
          scenario: "models_page",
          source: "models:queue-refresh",
        },
        () => refreshCompany(ticker, true)
      );
      setError(null);
      setSettledJobIds([]);
      setActiveJobId(response.refresh.job_id);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to start refresh");
    } finally {
      setRefreshing(false);
    }
  }

  async function handleExportModelOutputs() {
    try {
      setExportingModelOutputs(true);

      if (!data && !financialData && !marketContextData && !sectorContextData && !capitalStructureData && !evaluationData) {
        throw new Error("Model outputs are still loading.");
      }

      const exportModelData = await withPerformanceAuditSource(
        {
          pageRoute: "/company/[ticker]/models",
          scenario: "models_page",
          source: "models:export-expanded-models",
        },
        () => getCompanyModels(ticker, MODEL_NAMES, { dupontMode, expandInputPeriods: true })
      );
      const exportForecastAccuracy: CompanyChartsForecastAccuracyResponse | null = forecastHandoff
        ? (forecastAccuracy.data ?? await getCompanyChartsForecastAccuracy(ticker, { asOf: forecastHandoff.asOf }))
        : null;

      downloadJsonFile(`${normalizeExportFileStem(ticker, "company")}-model-outputs.json`, {
        exported_at: new Date().toISOString(),
        ticker,
        dupont_mode: dupontMode,
        models: exportModelData,
        financials: financialData,
        market_context: marketContextData,
        sector_context: sectorContextData,
        capital_structure: capitalStructureData,
        oil_scenario_overlay: oilScenarioOverlayData,
        latest_evaluation: evaluationData,
        forecast_context: forecastHandoff
          ? {
              handoff: forecastHandoff,
              source_state: resolveForecastHandoffSourceState(forecastHandoff),
              forecast_accuracy:
                exportForecastAccuracy == null
                  ? null
                  : {
                      status: exportForecastAccuracy.status,
                      insufficient_history_reason: exportForecastAccuracy.insufficient_history_reason,
                      aggregate: exportForecastAccuracy.status === "ok" ? exportForecastAccuracy.aggregate : null,
                    },
            }
          : null,
      });
      showAppToast({ message: "Model outputs exported as JSON.", tone: "info" });
    } catch (nextError) {
      showAppToast({
        message: nextError instanceof Error ? nextError.message : "Unable to export model outputs.",
        tone: "danger",
      });
    } finally {
      setExportingModelOutputs(false);
    }
  }

  return (
    <CompanyWorkspaceShell
      rail={
        <>
          <CompanyUtilityRail
            ticker={ticker}
            companyName={data?.company?.name ?? financialData?.company?.name ?? null}
            sector={data?.company?.sector ?? financialData?.company?.sector ?? null}
            refreshState={data?.refresh ?? financialData?.refresh ?? null}
            refreshing={refreshing}
            onRefresh={queueRefresh}
            actionTitle="Next Steps"
            actionSubtitle={
              strictOfficialMode
                ? "Refresh SEC filings and model outputs, or return to financial statements for official-source context."
                : "Refresh the latest data for this ticker or return to financial statements."
            }
            primaryActionLabel="Refresh Model Inputs"
            primaryActionDescription={
              strictOfficialMode
                ? "Updates filings, official rate inputs, and model calculations in the background without commercial price fetches."
                : "Updates filings, market prices, and model calculations in the background."
            }
            secondaryActionHref={`/company/${encodeURIComponent(ticker)}/financials`}
            secondaryActionLabel="Open Financials"
            secondaryActionDescription="Review statements, charts, and historical company results."
            extraActions={[
              {
                label: exportingModelOutputs ? "Exporting..." : "Export Model Outputs (JSON)",
                description: "Download the loaded model responses and supporting model context as JSON.",
                onClick: handleExportModelOutputs,
                disabled: exportingModelOutputs || (loading && !data && !financialData),
              },
            ]}
            statusLines={[
              `Available models: ${modelSummary.cachedCount}/${MODEL_NAMES.length}`,
              `Last updated: ${modelSummary.latestComputed ? formatDate(modelSummary.latestComputed) : loading ? "Loading..." : "Preparing data"}`,
              `Price history points available: ${(financialData?.price_history ?? []).length.toLocaleString()}`,
              `DuPont basis: ${modelSummary.dupontBasis ?? dupontMode.toUpperCase()}`
            ]}
            consoleEntries={consoleEntries}
            connectionState={connectionState}
            actionTone="gold"
          />

          <Panel title="Model Diagnostics" subtitle="Coverage, proxy fallback, and missing-field flags rolled up from cached model runs">
            <DataQualityDiagnostics diagnostics={data?.diagnostics} />
          </Panel>
        </>
      }
      mainClassName="models-page-grid"
    >
      <CompanyResearchHeader
        ticker={ticker}
        title={data?.company?.name ?? financialData?.company?.name ?? ticker}
        companyName={`${ticker} · Valuation and model workspace`}
        sector={data?.company?.sector ?? financialData?.company?.sector ?? null}
        description={
          strictOfficialMode
            ? "Valuation conclusion, confidence, and scenario context from SEC-aligned cached model outputs, with price-dependent workflows withheld in strict mode."
            : "Valuation conclusion, confidence, and scenario context from SEC fundamentals and cached market inputs, refreshed in the background as inputs age."
        }
        freshness={{
          cacheState: data?.company?.cache_state ?? financialData?.company?.cache_state ?? null,
          refreshState: data?.refresh ?? financialData?.refresh ?? null,
          loading,
          hasData: Boolean(data || financialData || models.length),
          lastChecked: data?.company?.last_checked ?? financialData?.company?.last_checked ?? null,
          errors: [error],
          detailLines: [
            `Available models: ${modelSummary.cachedCount}/${MODEL_NAMES.length}`,
            `Last updated: ${modelSummary.latestComputed ? formatDate(modelSummary.latestComputed) : loading ? "Loading..." : "Preparing data"}`,
            `Price history points available: ${(financialData?.price_history ?? []).length.toLocaleString()}`,
            `DuPont basis: ${modelSummary.dupontBasis ?? dupontMode.toUpperCase()}`,
          ],
        }}
        freshnessPlacement="subtitle"
        factsLoading={loading && !data && !financialData}
        summariesLoading={loading && !data && !financialData}
        facts={[
          { label: "Ticker", value: ticker },
          { label: "Models", value: `${modelSummary.cachedCount}/${MODEL_NAMES.length}` },
          { label: "Last Computed", value: modelSummary.latestComputed ? formatDate(modelSummary.latestComputed) : loading ? "Loading..." : "Preparing data" },
          { label: "DuPont Basis", value: modelSummary.dupontBasis ?? dupontMode.toUpperCase() }
        ]}
        ribbonItems={[
          { label: "Inputs", value: "SEC EDGAR/XBRL", tone: "green" },
          { label: strictOfficialMode ? "Price Layer" : "Prices", value: strictOfficialMode ? "Disabled" : "Cached market data", tone: strictOfficialMode ? "gold" : "cyan" },
          { label: "Refresh", value: activeJobId ? "Model update running" : "Background-first", tone: activeJobId ? "cyan" : "green" }
        ]}
        summaries={[
          { label: modelSummary.dcfEnterpriseLabel, value: formatCompactNumber(modelSummary.dcfEnterpriseValue), accent: modelSummary.dcfEnterpriseValue != null && modelSummary.dcfEnterpriseValue < 0 ? "red" : "cyan" },
          { label: "Piotroski", value: modelSummary.piotroskiLabel, accent: "cyan" },
          { label: "DuPont ROE", value: formatPercent(modelSummary.dupontRoe), accent: modelSummary.dupontRoe != null && modelSummary.dupontRoe < 0 ? "red" : "cyan" },
        { label: "Altman Z", value: formatSigned(modelSummary.altmanZ), accent: modelSummary.altmanZ != null && modelSummary.altmanZ < 0 ? "red" : "cyan" }
        ]}
        className="model-hero models-page-hero models-page-span-full"
      >
        {!strictOfficialMode ? (
          <CommercialFallbackNotice
            provenance={data?.provenance}
            sourceMix={data?.source_mix}
            subject="Price-sensitive valuation outputs on this surface"
          />
        ) : null}
        {strictOfficialMode ? (
          <div className="text-muted models-page-strict-note">
            Strict official mode disables commercial equity price inputs. Fair value gap, reverse DCF, and price-comparison workflow steps stay unavailable until an official end-of-day price source is configured.
          </div>
        ) : null}
        <div className="text-muted models-page-strict-note">
          Valuation methodology: free cash flow is treated as an FCFF proxy, the discount rate is a proxy WACC, enterprise value is bridged to equity value through net debt, and incomplete capital-structure data produces an Enterprise Value Proxy instead of a precise equity fair value.
        </div>
        {modelSummary.dcfCaveat ? <div className="text-muted models-page-strict-note">{modelSummary.dcfCaveat}</div> : null}
        <div className="dupont-mode-bar">
          <div className="dupont-mode-select-col">
            <div className="metric-label">DuPont Basis</div>
            <select
              className="dupont-mode-select"
              aria-label="DuPont basis"
              value={dupontMode}
              onChange={(event) => setDupontMode(event.target.value as DupontMode)}
            >
              <option value="auto">Auto (Annual if available)</option>
              <option value="annual">Annual filing only</option>
              <option value="ttm">Rolling TTM (4 comparable filings)</option>
            </select>
          </div>
          <button className="dupont-info-button" type="button" onClick={() => setShowModeInfo(true)}>
            DuPont basis explainer
          </button>
        </div>

        {showModeInfo ? (
          <div className="dupont-info-pop">
            <div className="dupont-info-header">
              <div>
                <div className="metric-label">How DuPont basis works</div>
                <div className="dupont-info-sub">Choose how ROE components are scaled.</div>
              </div>
              <button className="dupont-info-close" type="button" aria-label="Close" onClick={() => setShowModeInfo(false)}>
                ×
              </button>
            </div>
            <ul className="dupont-info-list">
              <li><strong>Auto</strong> – Uses the latest annual filing when present; otherwise builds TTM from the last four comparable filings.</li>
              <li><strong>Annual</strong> – Always use the latest annual filing (10-K/20-F/40-F); ROE reflects that single year.</li>
              <li><strong>TTM</strong> – Always use rolling four comparable filings (typically 10-Qs) to smooth seasonality.</li>
            </ul>
            <div className="dupont-info-footnote">Changing the basis recalculates and caches a separate DuPont run for this company.</div>
          </div>
        ) : null}

        <div className="sparkline-note">Start with Investment Summary for the conclusion view, then use Financial Health Score, scenario ranges, and model analytics for detail.</div>
      </CompanyResearchHeader>

      <Panel
        title="Investment Summary"
        subtitle={
          loading
            ? "Loading valuation, quality, and market inputs..."
            : strictOfficialMode
              ? "Quick valuation snapshot based on SEC filings, with market-price comparisons disabled in strict mode"
              : "Quick valuation snapshot based on company results and market prices"
        }
        className="models-page-span-full models-summary-panel"
        variant="hero"
      >
        <InvestmentSummaryPanel
          ticker={ticker}
          models={models}
          financials={financialData?.financials ?? []}
          priceHistory={financialData?.price_history ?? []}
          strictOfficialMode={strictOfficialMode}
        />
      </Panel>

      {forecastHandoff ? (
        <Panel
          title="Forecast-backed Valuation Impact"
          subtitle="Additive handoff from Projection Studio. Existing valuation models remain unchanged."
          className="models-page-span-full"
          variant="subtle"
        >
          <ForecastBackedValuationCard handoff={forecastHandoff} models={models} ticker={ticker} accuracy={forecastAccuracy.data} accuracyLoading={forecastAccuracy.loading} accuracyError={forecastAccuracy.error} />
        </Panel>
      ) : null}

      <Panel
        title="Financial Health Score"
        subtitle={loading ? "Loading health inputs..." : "Profitability, strength, growth, and overall health on a 0-10 scale"}
        className="models-page-span-full"
        variant="subtle"
      >
        <FinancialHealthScore models={models} financials={financialData?.financials ?? []} />
      </Panel>

      <Panel title="Valuation Scenario Ranges" subtitle={loading ? "Loading valuation scenario inputs..." : strictOfficialMode ? "Interactive DCF scenario builder and residual-income ranges, with price-linked reverse DCF withheld in strict mode" : "Interactive DCF scenario builder plus editable bear, base, and bull ranges across DCF, reverse DCF, and residual income"} className="models-page-span-full" variant="subtle">
        <DeferredClientSection placeholder={<div className="text-muted">Loading valuation scenario ranges...</div>}>
          <ValuationScenarioWorkbench
            ticker={ticker}
            models={models}
            financials={financialData?.financials ?? []}
            priceHistory={financialData?.price_history ?? []}
            strictOfficialMode={strictOfficialMode}
          />
        </DeferredClientSection>
      </Panel>

      <Panel
        title="Oil Workspace"
        subtitle={strictOfficialMode ? "Dedicated oil workspace with official benchmark curves, strict-mode-safe manual price input, and historical overlay evaluation context" : "Dedicated oil workspace with official benchmark curves, evaluation context, and an interactive overlay workbench"}
        className="models-page-span-full"
        variant="subtle"
      >
        <DeferredClientSection placeholder={<div className="text-muted">Oil workspace context loads when this panel enters view.</div>}>
          <OptionalPanelActivationMarker
            onVisible={() => {
              activateOptionalPanel("oilScenarioOverlay");
              activateOptionalPanel("oilOverlayEvaluation");
            }}
          />
          <div className="workspace-card-stack workspace-card-stack-tight">
            <div className="text-muted">
              Oil moved into its own workspace so the interactive overlay, provenance, and extension controls do not compete with the broader valuation stack on this page.
            </div>
            {optionalPanelStates.oilScenarioOverlay.status === "disabled" ? (
              <div className="text-muted">Oil workspace is disabled: {describeOilOverlayAvailability(oilSupportReasons)}</div>
            ) : optionalPanelStates.oilScenarioOverlay.status === "idle" ? (
              <div className="text-muted">Oil workspace context will load when this section becomes active.</div>
            ) : optionalPanelStates.oilScenarioOverlay.status === "loading" ? (
              <div className="text-muted">Loading oil workspace context...</div>
            ) : optionalPanelStates.oilScenarioOverlay.status === "failed" ? (
              <div className="workspace-error-state text-muted">Oil workspace context failed to load: {optionalPanelStates.oilScenarioOverlay.error}</div>
            ) : optionalPanelStates.oilScenarioOverlay.status === "unavailable" ? (
              <div className="text-muted">Oil workspace context is currently unavailable for this company.</div>
            ) : (
              <>
                <div className="workspace-pill-row">
                  <span className="pill">Support {titleCase(oilSupportStatus)}</span>
                  <span className="pill">Official Curve {(optionalPanelStates.oilScenarioOverlay.data.official_base_curve?.points?.length ?? 0) > 0 ? "Ready" : "Blocked"}</span>
                  <span className="pill">Sensitivity {optionalPanelStates.oilScenarioOverlay.data.sensitivity_source?.kind ? titleCase(String(optionalPanelStates.oilScenarioOverlay.data.sensitivity_source.kind).replaceAll("_", " ")) : "Pending"}</span>
                  {oilWorkspaceEvaluationSummary ? <span className="pill">Eval Samples {oilWorkspaceEvaluationSummary.sampleCount ?? "—"}</span> : null}
                </div>
                <div className="text-muted">
                  {oilSupportStatus === "partial"
                    ? (oilSupportReasons[0] ? describeOilSupportReason(oilSupportReasons[0]) : "Oil support is partial for this company.")
                    : "Use the dedicated workspace for the official benchmark curve, direct SEC evidence, realized-spread settings, downstream offsets, and historical PIT evaluation context."}
                </div>
                {optionalPanelStates.oilOverlayEvaluation.status === "failed" ? (
                  <div className="workspace-error-state text-muted">Oil overlay evaluation failed to load: {optionalPanelStates.oilOverlayEvaluation.error}</div>
                ) : oilWorkspaceEvaluationSummary ? (
                  <div className="filing-link-card workspace-card-stack-tight">
                    <div className="metric-label">Latest Oil Overlay Evaluation</div>
                    <div className="workspace-pill-row">
                      <span className="pill">Samples {oilWorkspaceEvaluationSummary.sampleCount ?? "—"}</span>
                      <span className="pill">MAE Lift {formatSigned(oilWorkspaceEvaluationSummary.maeLift)}</span>
                      <span className="pill">Improvement Rate {formatPercent(oilWorkspaceEvaluationSummary.improvementRate)}</span>
                      <span className="pill">As Of {oilWorkspaceEvaluationSummary.asOf ?? "—"}</span>
                    </div>
                    <div className="text-muted">{oilWorkspaceEvaluationSummary.description}</div>
                  </div>
                ) : optionalPanelStates.oilOverlayEvaluation.status === "loading" ? (
                  <div className="text-muted">Loading oil overlay evaluation context...</div>
                ) : null}
                <div>
                  <Link href={`/company/${encodeURIComponent(ticker)}/oil`} className="ticker-button utility-action-button utility-action-button-primary utility-action-link-button">
                    Open Oil Workspace
                  </Link>
                </div>
                <SourceFreshnessSummary
                  provenance={optionalPanelStates.oilScenarioOverlay.data.provenance}
                  asOf={optionalPanelStates.oilScenarioOverlay.data.as_of}
                  lastRefreshedAt={optionalPanelStates.oilScenarioOverlay.data.last_refreshed_at}
                  sourceMix={optionalPanelStates.oilScenarioOverlay.data.source_mix}
                  confidenceFlags={optionalPanelStates.oilScenarioOverlay.data.confidence_flags}
                  emptyMessage="Oil workspace provenance will appear after the official oil overlay dataset is available."
                />
              </>
            )}
          </div>
        </DeferredClientSection>
      </Panel>

      <Panel title="Model Analytics" subtitle={loading ? "Loading..." : "Charts and number tables for DCF, DuPont, Piotroski, Altman Z, and ratios"} className="models-page-span-full" variant="subtle">
        {hasModels ? (
          <DeferredClientSection placeholder={<div className="text-muted">Loading model analytics...</div>}>
            <ModelDashboard models={models} />
          </DeferredClientSection>
        ) : <div className="text-muted">No model results yet. Once financial data is ready, this page will fill in automatically.</div>}
      </Panel>

      <Panel
        variant="subtle"
        title="Model Evaluation Harness"
        subtitle="Latest persisted backtest run for calibration, stability, and error drift across the valuation stack"
        className="models-page-span-full"
      >
        <DeferredClientSection placeholder={<div className="text-muted">Model evaluation context loads when this panel enters view.</div>}>
          <OptionalPanelActivationMarker onVisible={() => activateOptionalPanel("modelEvaluation")} />
          {optionalPanelStates.modelEvaluation.status === "idle" ? (
            <div className="text-muted">Model evaluation context will load when this section becomes active.</div>
          ) : optionalPanelStates.modelEvaluation.status === "loading" ? (
            <div className="text-muted">Loading model evaluation harness...</div>
          ) : optionalPanelStates.modelEvaluation.status === "failed" ? (
            <div className="workspace-error-state text-muted">Model evaluation harness failed to load: {optionalPanelStates.modelEvaluation.error}</div>
          ) : optionalPanelStates.modelEvaluation.status === "disabled" ? (
            <div className="text-muted">Model evaluation harness is disabled.</div>
          ) : optionalPanelStates.modelEvaluation.status === "unavailable" ? (
            <div className="text-muted">Model evaluation harness is unavailable.</div>
          ) : (
            <ModelEvaluationPanel evaluation={optionalPanelStates.modelEvaluation.data} />
          )}
        </DeferredClientSection>
      </Panel>

      <Panel
        variant="subtle"
        title="Macro Exposure Context"
        subtitle="Official indicators selected from the company's mapped demand, cost, inventory, and rate exposures"
        className="models-page-span-full"
      >
        <DeferredClientSection placeholder={<div className="text-muted">Macro context loads when this panel enters view.</div>}>
          <OptionalPanelActivationMarker onVisible={() => activateOptionalPanel("marketContext")} />
          {optionalPanelStates.marketContext.status === "idle" ? (
            <div className="text-muted">Macro context will load when this section becomes active.</div>
          ) : optionalPanelStates.marketContext.status === "loading" ? (
            <div className="text-muted">Loading macro exposure context...</div>
          ) : optionalPanelStates.marketContext.status === "failed" ? (
            <div className="workspace-error-state text-muted">Macro exposure context failed to load: {optionalPanelStates.marketContext.error}</div>
          ) : optionalPanelStates.marketContext.status === "disabled" ? (
            <div className="text-muted">Macro exposure context is disabled.</div>
          ) : optionalPanelStates.marketContext.status === "unavailable" ? (
            <div className="text-muted">No macro indicators are available for this company right now.</div>
          ) : (
            <MarketContextPanel context={optionalPanelStates.marketContext.data} />
          )}
        </DeferredClientSection>
      </Panel>

      <Panel
        variant="subtle"
        title="Capital Structure Intelligence"
        subtitle="SEC-derived maturity ladders, debt roll-forwards, payout mix, SBC burden, and dilution bridges alongside the model stack"
        className="models-page-span-full"
      >
        <DeferredClientSection placeholder={<div className="text-muted">Capital structure context loads when this panel enters view.</div>}>
          <OptionalPanelActivationMarker onVisible={() => activateOptionalPanel("capitalStructure")} />
          {optionalPanelStates.capitalStructure.status === "idle" ? (
            <div className="text-muted">Capital structure intelligence will load when this section becomes active.</div>
          ) : optionalPanelStates.capitalStructure.status === "loading" ? (
            <div className="text-muted">Loading capital structure intelligence...</div>
          ) : optionalPanelStates.capitalStructure.status === "failed" ? (
            <div className="workspace-error-state text-muted">Capital structure intelligence failed to load: {optionalPanelStates.capitalStructure.error}</div>
          ) : optionalPanelStates.capitalStructure.status === "disabled" ? (
            <div className="text-muted">Capital structure intelligence is disabled.</div>
          ) : optionalPanelStates.capitalStructure.status === "unavailable" ? (
            <div className="text-muted">Capital structure intelligence is currently unavailable for this company.</div>
          ) : (
            <CapitalStructureIntelligencePanel
              ticker={ticker}
              reloadKey={data?.last_refreshed_at ?? financialData?.last_refreshed_at ?? activeJobId}
              initialPayload={optionalPanelStates.capitalStructure.data}
            />
          )}
        </DeferredClientSection>
      </Panel>

      <Panel
        variant="subtle"
        title="Sector Exposure Context"
        subtitle="Official sector plug-ins for power, housing, airlines, air cargo, and agricultural supply-demand exposures"
        className="models-page-span-full"
      >
        <DeferredClientSection placeholder={<div className="text-muted">Sector context loads when this panel enters view.</div>}>
          <OptionalPanelActivationMarker onVisible={() => activateOptionalPanel("sectorContext")} />
          {optionalPanelStates.sectorContext.status === "idle" ? (
            <div className="text-muted">Sector context will load when this section becomes active.</div>
          ) : optionalPanelStates.sectorContext.status === "loading" ? (
            <div className="text-muted">Loading sector exposure context...</div>
          ) : optionalPanelStates.sectorContext.status === "failed" ? (
            <div className="workspace-error-state text-muted">Sector exposure context failed to load: {optionalPanelStates.sectorContext.error}</div>
          ) : optionalPanelStates.sectorContext.status === "disabled" ? (
            <div className="text-muted">Sector exposure context is disabled.</div>
          ) : optionalPanelStates.sectorContext.status === "unavailable" ? (
            <div className="text-muted">No sector plug-ins are available for this company right now.</div>
          ) : (
            <SectorContextPanel context={optionalPanelStates.sectorContext.data} />
          )}
        </DeferredClientSection>
      </Panel>

      <Panel title="Source & Freshness" subtitle="Registry-backed provenance for filing inputs, rates, price overlays, and model disclosures" className="models-page-span-full" variant="subtle">
        <SourceFreshnessSummary
          provenance={data?.provenance}
          asOf={data?.as_of}
          lastRefreshedAt={data?.last_refreshed_at}
          sourceMix={data?.source_mix}
          confidenceFlags={data?.confidence_flags}
        />
      </Panel>

      <details className="subtle-details models-page-span-full">
        <summary>
          Advanced details
          <span className="pill">
            <span className="neon-green">{modelSummary.cachedCount}</span> available
          </span>
        </summary>
        <div className="subtle-details-body">
          {error ? (
            <div className="text-muted">{error}</div>
          ) : hasModels ? (
            <DeferredClientSection placeholder={<div className="text-muted">Loading advanced grid...</div>}>
              <DenseGrid rowData={models as unknown as object[]} columnDefs={columns as unknown as ColDef<object>[]} height={280} />
            </DeferredClientSection>
          ) : (
            <div className="grid-empty-state">
              <div className="grid-empty-kicker">Preparing model results</div>
              <div className="grid-empty-title">No model results yet</div>
              <div className="grid-empty-copy">
                For a new or out-of-date company, results may take a moment while data refreshes and the models finish running.
              </div>
              <div className="models-empty-actions">
                <button onClick={() => void queueRefresh()} className="ticker-button models-refresh-button">
                  {refreshing ? "Refreshing..." : "Refresh Model Data"}
                </button>
                <span className="pill">{activeJobId ? "Update in progress" : loading ? "Preparing model data" : "Waiting for first update"}</span>
              </div>
            </div>
          )}
        </div>
      </details>
    </CompanyWorkspaceShell>
  );
}

function ForecastBackedValuationCard({ handoff, models, ticker, accuracy, accuracyLoading, accuracyError }: { handoff: ForecastHandoffPayload; models: ModelPayload[]; ticker: string; accuracy: CompanyChartsForecastAccuracyResponse | null; accuracyLoading: boolean; accuracyError: string | null }) {
  const dcfModel = models.find((model) => model.model_name === "dcf") ?? null;
  const dcfState = resolveDcfDisplayState(dcfModel);
  const dcfCaveat = describeDcfDisplayCaveat(dcfState);
  const baseFairValuePerShare = dcfState.fairValuePerShare;
  const sourceState = resolveForecastHandoffSourceState(handoff) ?? "sec_default";

  const fcfMetric = findHandoffMetric(handoff.metrics, "free_cash_flow");
  const earningsMetric = findHandoffMetric(handoff.metrics, "net_income") ?? findHandoffMetric(handoff.metrics, "eps");
  const revenueMetric = findHandoffMetric(handoff.metrics, "revenue");

  const weightedChange = resolveWeightedForecastChange([fcfMetric, earningsMetric, revenueMetric]);
  const heuristicSignal = resolveHeuristicScenarioSignal(weightedChange);

  return (
    <div className="workspace-card-stack workspace-card-stack-tight" data-testid="forecast-backed-valuation-card">
      <div className="workspace-pill-row">
        <span className="pill">Source {handoff.source === "user_scenario" ? "User scenario" : "SEC-derived base forecast"}</span>
        <span className="pill">Forecast Year {handoff.forecastYear ?? "—"}</span>
        <span className="pill">Overrides {handoff.overrideCount}</span>
        {handoff.scenarioName ? <span className="pill">Scenario {handoff.scenarioName}</span> : null}
      </div>
      <ForecastTrustCue sourceState={sourceState} accuracy={accuracy} loading={accuracyLoading} error={accuracyError} />

      <div className="models-forecast-impact-grid">
        <div className="models-forecast-impact-card">
          <div className="metric-label">{baseFairValuePerShare == null ? "Current DCF fair value per share unavailable for this run" : "Current DCF fair value per share (model-derived)"}</div>
          <div className="models-forecast-impact-value">{formatCompactNumber(baseFairValuePerShare)}</div>
          <div className="text-muted">{dcfCaveat ?? "From the latest persisted DCF run already stored in Models."}</div>
        </div>
        <div className="models-forecast-impact-card">
          <div className="metric-label">Scenario impact signal (heuristic, no model rerun)</div>
          <div className="models-forecast-impact-value">{heuristicSignal.label}</div>
          <div className="text-muted">{heuristicSignal.band}</div>
          <div className="text-muted">{heuristicSignal.description}</div>
        </div>
      </div>

      <div className="models-forecast-metrics-grid">
        {handoff.metrics.map((metric) => {
          const delta =
            metric.base != null && metric.scenario != null
              ? metric.scenario - metric.base
              : null;
          return (
            <div key={metric.key} className="models-forecast-metric-row">
              <strong>{metric.label}</strong>
              <span>Base {formatForecastMetric(metric.base, metric.unit)}</span>
              <span>Handoff {formatForecastMetric(metric.scenario, metric.unit)}</span>
              <span>Delta {delta != null ? formatSignedMetric(delta, metric.unit) : "—"}</span>
            </div>
          );
        })}
      </div>

      <div className="text-muted">
        Trust boundary: Projection Studio changed scenario inputs only. Cached model outputs and persisted valuations did not change here. This surface shows a heuristic directional signal until a backend model rerun is executed.
      </div>
      <div>
        <Link href={`/company/${encodeURIComponent(ticker)}/models`} className="ticker-button utility-action-button utility-action-link-button">
          Reset to Standard Models View
        </Link>
      </div>
    </div>
  );
}

function findHandoffMetric(metrics: ForecastHandoffMetric[], key: string): ForecastHandoffMetric | null {
  return metrics.find((metric) => metric.key === key) ?? null;
}

function resolveWeightedForecastChange(metrics: Array<ForecastHandoffMetric | null>): number | null {
  const weightedDeltas = metrics
    .map((metric, index) => {
      if (!metric || metric.base == null || metric.scenario == null || metric.base === 0) {
        return null;
      }
      const weight = index === 0 ? 0.65 : index === 1 ? 0.25 : 0.1;
      return ((metric.scenario - metric.base) / Math.abs(metric.base)) * weight;
    })
    .filter((value): value is number => value != null);

  if (!weightedDeltas.length) {
    return null;
  }

  return weightedDeltas.reduce((sum, value) => sum + value, 0);
}

function resolveHeuristicScenarioSignal(weightedChange: number | null): {
  label: string;
  band: string;
  description: string;
} {
  if (weightedChange == null) {
    return {
      label: "Signal unavailable",
      band: "Heuristic band: not enough comparable deltas",
      description: "At least one comparable projected metric delta is needed to produce a directional scenario signal.",
    };
  }

  const capped = Math.max(-0.6, Math.min(0.6, weightedChange));
  const absChange = Math.abs(capped);
  const direction = capped > 0.01 ? "upside" : capped < -0.01 ? "downside" : "flat";
  const strength = absChange < 0.03 ? "slight" : absChange < 0.12 ? "moderate" : "strong";

  const halfWidth = absChange < 0.12 ? 5 : 10;
  const centerPct = capped * 100;
  const lowerPct = roundToNearestFive(centerPct - halfWidth);
  const upperPct = roundToNearestFive(centerPct + halfWidth);

  if (direction === "flat") {
    return {
      label: "Balanced / low directional tilt",
      band: "Heuristic band: approximately -5% to +5% directional impact",
      description: "Projected deltas are mixed or small, so the scenario signal is near neutral.",
    };
  }

  const titleDirection = direction === "upside" ? "Upside" : "Downside";
  return {
    label: `${strength === "strong" ? "Strong" : strength === "moderate" ? "Moderate" : "Slight"} ${titleDirection} Signal`,
    band: `Heuristic band: approximately ${formatSignedPercentRange(lowerPct, upperPct)} directional impact`,
    description: "Computed from weighted projected deltas (FCF, earnings/EPS, revenue). This is not a recomputed valuation output.",
  };
}

function roundToNearestFive(value: number): number {
  return Math.round(value / 5) * 5;
}

function formatSignedPercentRange(lower: number, upper: number): string {
  return `${formatSignedPercent(lower)} to ${formatSignedPercent(upper)}`;
}

function formatSignedPercent(value: number): string {
  const rounded = Math.round(value);
  return `${rounded > 0 ? "+" : ""}${rounded}%`;
}

function formatForecastMetric(value: number | null, unit: string): string {
  if (value == null) {
    return "—";
  }
  if (unit === "percent") {
    return formatPercent(value);
  }
  if (unit === "usd_per_share") {
    return formatCompactNumber(value);
  }
  return formatCompactNumber(value);
}

function formatSignedMetric(value: number, unit: string): string {
  const prefix = value >= 0 ? "+" : "-";
  return `${prefix}${formatForecastMetric(Math.abs(value), unit)}`;
}

async function loadModelsCoreData(ticker: string, dupontMode: DupontMode, signal?: AbortSignal): Promise<ModelsCoreData> {
  const [modelResult, financialResult] = await Promise.allSettled([
    getCompanyModels(ticker, MODEL_NAMES, { dupontMode, signal }),
    getCompanyFinancials(ticker, { view: "core", signal }),
  ]);

  if (isRejectedAbort(modelResult) || isRejectedAbort(financialResult)) {
    throw abortError();
  }

  const modelData = requireModelsWorkspacePayload(modelResult, "Unable to load models");
  const financialData = requireModelsWorkspacePayload(financialResult, "Unable to load company financials");

  return {
    modelData,
    financialData,
    activeJobId: modelData.refresh.job_id ?? financialData.refresh.job_id ?? null,
  };
}

function requireModelsWorkspacePayload<T>(result: PromiseSettledResult<T>, fallback: string): T {
  if (result.status === "fulfilled") {
    return result.value;
  }

  throw result.reason instanceof Error ? result.reason : new Error(fallback);
}

function hasMeaningfulMarketContext(context: CompanyMarketContextResponse | null): boolean {
  if (!context) {
    return false;
  }

  return Boolean(
    hasRenderableMacroItems(context.relevant_indicators) ||
      hasRenderableMacroItems(context.cyclical_demand) ||
      hasRenderableMacroItems(context.cyclical_costs) ||
      (context.sector_exposure ?? []).length
  );
}

function hasRenderableMacroItems(items: Array<{ status: string; value: number | null }> | null | undefined): boolean {
  return Boolean(items?.some((item) => item.status === "ok" && item.value != null));
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatSigned(value: number | null): string {
  if (value === null) {
    return "—";
  }

  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 2,
    signDisplay: "exceptZero"
  }).format(value);
}

function formatPanelError(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
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

function OptionalPanelActivationMarker({ onVisible }: { onVisible: () => void }) {
  useEffect(() => {
    onVisible();
  }, [onVisible]);

  return null;
}




