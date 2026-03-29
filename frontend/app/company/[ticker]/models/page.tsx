"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";
import type { ColDef } from "ag-grid-community";

import { CapitalStructureIntelligencePanel } from "@/components/company/capital-structure-intelligence-panel";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyResearchHeader } from "@/components/layout/company-research-header";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { MarketContextPanel } from "@/components/models/market-context-panel";
import { ModelEvaluationPanel } from "@/components/models/model-evaluation-panel";
import { SectorContextPanel } from "@/components/models/sector-context-panel";
import { DeferredClientSection } from "@/components/performance/deferred-client-section";
import { CommercialFallbackNotice } from "@/components/ui/commercial-fallback-notice";
import { DataQualityDiagnostics } from "@/components/ui/data-quality-diagnostics";
import { Panel } from "@/components/ui/panel";
import { SourceFreshnessSummary } from "@/components/ui/source-freshness-summary";
import { StatusPill } from "@/components/ui/status-pill";
import { useJobStream } from "@/hooks/use-job-stream";
import { rememberActiveJob } from "@/lib/active-job";
import { getCompanyFinancials, getCompanyMarketContext, getCompanyModels, getCompanySectorContext, getLatestModelEvaluation, refreshCompany } from "@/lib/api";
import { MODEL_NAMES } from "@/lib/constants";
import { formatCompactNumber, formatDate, formatPercent, titleCase } from "@/lib/format";
import { formatPiotroskiDisplay, resolvePiotroskiScoreState } from "@/lib/piotroski";
import type { CompanyFinancialsResponse, CompanyMarketContextResponse, CompanyModelsResponse, CompanySectorContextResponse, ModelEvaluationResponse, ModelPayload } from "@/lib/types";

interface ModelsWorkspaceData {
  modelData: CompanyModelsResponse;
  financialData: CompanyFinancialsResponse;
  marketContextData: CompanyMarketContextResponse;
  sectorContextData: CompanySectorContextResponse;
  evaluationData: ModelEvaluationResponse;
  activeJobId: string | null;
}

const REFRESH_POLL_INTERVAL_MS = 3000;

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

export default function CompanyModelsPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(params.ticker).toUpperCase();
  const [data, setData] = useState<CompanyModelsResponse | null>(null);
  const [financialData, setFinancialData] = useState<CompanyFinancialsResponse | null>(null);
  const [marketContextData, setMarketContextData] = useState<CompanyMarketContextResponse | null>(null);
  const [sectorContextData, setSectorContextData] = useState<CompanySectorContextResponse | null>(null);
  const [evaluationData, setEvaluationData] = useState<ModelEvaluationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [settledJobIds, setSettledJobIds] = useState<string[]>([]);
  const [dupontMode, setDupontMode] = useState<DupontMode>("auto");
  const [showModeInfo, setShowModeInfo] = useState(false);
  const { consoleEntries, connectionState, lastEvent } = useJobStream(activeJobId);
  const models = useMemo(() => data?.models ?? [], [data?.models]);
  const hasModels = models.length > 0;
  const strictOfficialMode = Boolean(data?.company?.strict_official_mode ?? financialData?.company?.strict_official_mode);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        setSettledJobIds([]);
        const workspaceData = await loadModelsWorkspaceData(ticker, dupontMode);
        if (!cancelled) {
          setData(workspaceData.modelData);
          setFinancialData(workspaceData.financialData);
          setMarketContextData(workspaceData.marketContextData);
          setSectorContextData(workspaceData.sectorContextData);
          setEvaluationData(workspaceData.evaluationData);
          setActiveJobId(workspaceData.activeJobId);
        }
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError instanceof Error ? nextError.message : "Unable to load models");
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
  }, [ticker, dupontMode]);

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

    void loadModelsWorkspaceData(ticker, dupontMode)
      .then((workspaceData) => {
        if (cancelled) {
          return;
        }
        setError(null);
        setData(workspaceData.modelData);
        setFinancialData(workspaceData.financialData);
        setMarketContextData(workspaceData.marketContextData);
        setSectorContextData(workspaceData.sectorContextData);
        setEvaluationData(workspaceData.evaluationData);
        setActiveJobId(workspaceData.activeJobId);
      })
      .catch((nextError) => {
        if (!cancelled) {
          setError(nextError instanceof Error ? nextError.message : "Unable to reload models");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [activeJobId, lastEvent, settledJobIds, ticker, dupontMode]);

  useEffect(() => {
    if (!activeJobId || settledJobIds.includes(activeJobId)) {
      return;
    }

    let cancelled = false;
    let pending = false;

    const poll = async () => {
      if (pending) {
        return;
      }

      pending = true;
      try {
        const workspaceData = await loadModelsWorkspaceData(ticker, dupontMode);
        if (cancelled) {
          return;
        }

        setError(null);
        setData(workspaceData.modelData);
        setFinancialData(workspaceData.financialData);
        setMarketContextData(workspaceData.marketContextData);
        setSectorContextData(workspaceData.sectorContextData);
        setEvaluationData(workspaceData.evaluationData);
        setActiveJobId(workspaceData.activeJobId);

        if (workspaceData.activeJobId !== activeJobId) {
          setSettledJobIds((current) => (current.includes(activeJobId) ? current : [...current, activeJobId]));
        }
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError instanceof Error ? nextError.message : "Unable to refresh models");
        }
      } finally {
        pending = false;
      }
    };

    const intervalId = window.setInterval(() => {
      void poll();
    }, REFRESH_POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [activeJobId, dupontMode, settledJobIds, ticker]);

  useEffect(() => {
    if (!activeJobId) {
      return;
    }

    rememberActiveJob(activeJobId, ticker);
  }, [activeJobId, ticker]);

  const columns = useMemo<ColDef<ModelPayload>[]>(
    () => [
      { field: "model_name", headerName: "Model", minWidth: 150, valueFormatter: ({ value }) => titleCase(String(value ?? "")) },
      { field: "model_version", headerName: "Version", maxWidth: 120, cellStyle: { color: "#FFD700", fontWeight: 700 } },
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

    return {
      cachedCount: models.length,
      latestComputed,
      dcfEnterpriseValue: asNumber(byName.dcf?.result?.enterprise_value_proxy),
      dupontRoe: asNumber(byName.dupont?.result?.return_on_equity),
      dupontBasis: typeof dupontBasisRaw === "string" ? dupontBasisRaw.toUpperCase() : null,
      piotroskiLabel: formatPiotroskiDisplay(piotroskiState),
      altmanZ: asNumber(byName.altman_z?.result?.z_score_approximate)
    };
  }, [models]);

  async function queueRefresh() {
    try {
      setRefreshing(true);
      const response = await refreshCompany(ticker, true);
      setError(null);
      setSettledJobIds([]);
      setActiveJobId(response.refresh.job_id);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to start refresh");
    } finally {
      setRefreshing(false);
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
      <Panel
        title="Investment Summary"
        subtitle={
          loading
            ? "Loading valuation, quality, and market inputs..."
            : strictOfficialMode
              ? "Quick valuation snapshot based on SEC filings, with market-price comparisons disabled in strict mode"
              : "Quick valuation snapshot based on company results and market prices"
        }
        className="models-page-span-full"
      >
        <InvestmentSummaryPanel
          ticker={ticker}
          models={models}
          financials={financialData?.financials ?? []}
          priceHistory={financialData?.price_history ?? []}
          strictOfficialMode={strictOfficialMode}
        />
      </Panel>

      <Panel title="Financial Health Score" subtitle={loading ? "Loading health inputs..." : "Profitability, strength, growth, and overall health on a 0-10 scale"} className="models-page-span-full">
        <FinancialHealthScore models={models} financials={financialData?.financials ?? []} />
      </Panel>

      <CompanyResearchHeader
        ticker={ticker}
        title="Valuation Models"
        companyName={data?.company?.name ?? financialData?.company?.name ?? ticker}
        sector={data?.company?.sector ?? financialData?.company?.sector ?? null}
        cacheState={data?.company?.cache_state ?? financialData?.company?.cache_state ?? null}
        description={
          strictOfficialMode
            ? "Cached model outputs stay aligned with SEC fundamentals and official macro rates, while commercial price-dependent valuation features are withheld."
            : "Cached model outputs stay aligned with SEC fundamentals and cached price inputs, with refreshes queued in the background when inputs are stale."
        }
        aside={data ? <StatusPill state={data.refresh} /> : undefined}
        facts={[
          { label: "Ticker", value: ticker },
          { label: "Available Models", value: `${modelSummary.cachedCount}/${MODEL_NAMES.length}` },
          { label: "Last Computed", value: modelSummary.latestComputed ? formatDate(modelSummary.latestComputed) : loading ? "Loading..." : "Preparing data" },
          { label: "DuPont Basis", value: modelSummary.dupontBasis ?? dupontMode.toUpperCase() }
        ]}
        ribbonItems={[
          { label: "Financial Inputs", value: "SEC EDGAR/XBRL", tone: "green" },
          { label: strictOfficialMode ? "Market Classification" : "Price Inputs", value: strictOfficialMode ? "SEC SIC mapping" : "Yahoo Finance", tone: strictOfficialMode ? "green" : "cyan" },
          { label: "Financials Checked", value: financialData?.company?.last_checked_financials ? formatDate(financialData.company.last_checked_financials) : "Pending", tone: "green" },
          { label: "Refresh", value: activeJobId ? "Model update running" : "Background-first", tone: activeJobId ? "gold" : "cyan" }
        ]}
        summaries={[
          { label: "Last Updated", value: modelSummary.latestComputed ? formatDate(modelSummary.latestComputed) : loading ? "Loading..." : "Preparing data", accent: "cyan" },
          { label: "DCF EV", value: formatCompactNumber(modelSummary.dcfEnterpriseValue), accent: "green" },
          { label: "DuPont ROE", value: formatPercent(modelSummary.dupontRoe), accent: "gold" },
          { label: "Piotroski", value: modelSummary.piotroskiLabel, accent: "green" },
          { label: "Altman Proxy", value: formatSigned(modelSummary.altmanZ), accent: "cyan" }
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
            <div className="text-muted" style={{ marginBottom: 12 }}>
              Strict official mode disables commercial equity price inputs. Fair value gap, reverse DCF, and price-comparison workflow steps stay unavailable until an official end-of-day price source is configured.
            </div>
          ) : null}
          <div className="dupont-mode-bar">
            <div className="dupont-mode-select-col">
              <div className="metric-label">DuPont Basis</div>
              <select
                className="dupont-mode-select"
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

            <div className="sparkline-note">Start with Investment Summary for the headline view, then use Financial Health Score, Valuation Scenario Ranges, and Model Analytics for the full model output.</div>
      </CompanyResearchHeader>

      <Panel title="Source & Freshness" subtitle="Registry-backed provenance for filing inputs, rates, price overlays, and model disclosures" className="models-page-span-full">
        <SourceFreshnessSummary
          provenance={data?.provenance}
          asOf={data?.as_of}
          lastRefreshedAt={data?.last_refreshed_at}
          sourceMix={data?.source_mix}
          confidenceFlags={data?.confidence_flags}
        />
      </Panel>

      <Panel
        title="Model Evaluation Harness"
        subtitle="Latest persisted backtest run for calibration, stability, and error drift across the valuation stack"
        className="models-page-span-full"
      >
        <ModelEvaluationPanel evaluation={evaluationData} />
      </Panel>

      <Panel
        title="Macro Demand & Cost Context"
        subtitle="Company-relevant official Census, BEA, and BLS indicators for cyclical demand, cost pressure, and labor tightness"
        className="models-page-span-full"
      >
        <MarketContextPanel context={marketContextData} />
      </Panel>

      <Panel
        title="Sector Exposure Context"
        subtitle="Official sector plug-ins for power, housing, airlines, air cargo, and agricultural supply-demand exposures"
        className="models-page-span-full"
      >
        <SectorContextPanel context={sectorContextData} />
      </Panel>

      <Panel
        title="Capital Structure Intelligence"
        subtitle="SEC-derived maturity ladders, debt roll-forwards, payout mix, SBC burden, and dilution bridges alongside the model stack"
        className="models-page-span-full"
      >
        <CapitalStructureIntelligencePanel
          ticker={ticker}
          reloadKey={data?.last_refreshed_at ?? financialData?.last_refreshed_at ?? activeJobId}
        />
      </Panel>

      <Panel title="Valuation Scenario Ranges" subtitle={loading ? "Loading valuation scenario inputs..." : strictOfficialMode ? "Interactive DCF and residual-income ranges with price-linked reverse DCF withheld in strict mode" : "Editable bear, base, and bull ranges across DCF, reverse DCF, and residual income"} className="models-page-span-full">
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

      <Panel title="Model Analytics" subtitle={loading ? "Loading..." : "Charts and number tables for DCF, DuPont, Piotroski, the Altman proxy, and ratios"} className="models-page-span-full">
        {hasModels ? (
          <DeferredClientSection placeholder={<div className="text-muted">Loading model analytics...</div>}>
            <ModelDashboard models={models} />
          </DeferredClientSection>
        ) : <div className="text-muted">No model results yet. Once financial data is ready, this page will fill in automatically.</div>}
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
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", justifyContent: "center" }}>
                <button onClick={() => void queueRefresh()} className="ticker-button" style={{ borderColor: "rgba(0,255,65,0.35)", color: "#00FF41" }}>
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

async function loadModelsWorkspaceData(ticker: string, dupontMode: DupontMode): Promise<ModelsWorkspaceData> {
  const [modelData, financialData, marketContextData, sectorContextData, evaluationData] = await Promise.all([
    getCompanyModels(ticker, MODEL_NAMES, { dupontMode }),
    getCompanyFinancials(ticker),
    getCompanyMarketContext(ticker),
    getCompanySectorContext(ticker),
    getLatestModelEvaluation(),
  ]);

  return {
    modelData,
    financialData,
    marketContextData,
    sectorContextData,
    evaluationData,
    activeJobId: modelData.refresh.job_id ?? financialData.refresh.job_id
  };
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



