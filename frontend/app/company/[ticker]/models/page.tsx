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
import { OilScenarioOverlayPanel } from "@/components/models/oil-scenario-overlay-panel";
import { SectorContextPanel } from "@/components/models/sector-context-panel";
import { DeferredClientSection } from "@/components/performance/deferred-client-section";
import { CommercialFallbackNotice } from "@/components/ui/commercial-fallback-notice";
import { DataQualityDiagnostics } from "@/components/ui/data-quality-diagnostics";
import { Panel } from "@/components/ui/panel";
import { SourceFreshnessSummary } from "@/components/ui/source-freshness-summary";
import { useJobStream } from "@/hooks/use-job-stream";
import { rememberActiveJob } from "@/lib/active-job";
import { showAppToast } from "@/lib/app-toast";
import { getCompanyCapitalStructure, getCompanyFinancials, getCompanyMarketContext, getCompanyModels, getCompanyOilScenarioOverlay, getCompanySectorContext, getLatestModelEvaluation, refreshCompany } from "@/lib/api";
import { MODEL_NAMES } from "@/lib/constants";
import { downloadJsonFile, normalizeExportFileStem } from "@/lib/export";
import { formatCompactNumber, formatDate, formatPercent, titleCase } from "@/lib/format";
import { formatPiotroskiDisplay, resolvePiotroskiScoreState } from "@/lib/piotroski";
import type { CompanyCapitalStructureResponse, CompanyFinancialsResponse, CompanyMarketContextResponse, CompanyModelsResponse, CompanyOilScenarioOverlayResponse, CompanySectorContextResponse, ModelEvaluationResponse, ModelPayload } from "@/lib/types";

interface ModelsWorkspaceData {
  modelData: CompanyModelsResponse;
  financialData: CompanyFinancialsResponse;
  marketContextData: CompanyMarketContextResponse | null;
  sectorContextData: CompanySectorContextResponse | null;
  capitalStructureData: CompanyCapitalStructureResponse | null;
  oilScenarioOverlayData: CompanyOilScenarioOverlayResponse | null;
  evaluationData: ModelEvaluationResponse | null;
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
  const [capitalStructureData, setCapitalStructureData] = useState<CompanyCapitalStructureResponse | null>(null);
  const [oilScenarioOverlayData, setOilScenarioOverlayData] = useState<CompanyOilScenarioOverlayResponse | null>(null);
  const [evaluationData, setEvaluationData] = useState<ModelEvaluationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [settledJobIds, setSettledJobIds] = useState<string[]>([]);
  const [dupontMode, setDupontMode] = useState<DupontMode>("auto");
  const [showModeInfo, setShowModeInfo] = useState(false);
  const [exportingModelOutputs, setExportingModelOutputs] = useState(false);
  const { consoleEntries, connectionState, lastEvent } = useJobStream(activeJobId);
  const models = useMemo(() => data?.models ?? [], [data?.models]);
  const hasModels = models.length > 0;
  const strictOfficialMode = Boolean(data?.company?.strict_official_mode ?? financialData?.company?.strict_official_mode);
  const showMarketContext = hasMeaningfulMarketContext(marketContextData);
  const showSectorContext = Boolean((sectorContextData?.plugins ?? []).length);
  const showCapitalStructure = Boolean(capitalStructureData?.latest);
  const oilSupportStatus = data?.company?.oil_support_status ?? financialData?.company?.oil_support_status ?? "unsupported";
  const oilSupportReasons = data?.company?.oil_support_reasons ?? financialData?.company?.oil_support_reasons ?? [];
  const showOilScenarioOverlay = oilSupportStatus === "supported" || oilSupportStatus === "partial";

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
          setCapitalStructureData(workspaceData.capitalStructureData);
          setOilScenarioOverlayData(workspaceData.oilScenarioOverlayData);
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
        setCapitalStructureData(workspaceData.capitalStructureData);
        setOilScenarioOverlayData(workspaceData.oilScenarioOverlayData);
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
        setCapitalStructureData(workspaceData.capitalStructureData);
        setOilScenarioOverlayData(workspaceData.oilScenarioOverlayData);
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

  async function handleExportModelOutputs() {
    try {
      setExportingModelOutputs(true);

      if (!data && !financialData && !marketContextData && !sectorContextData && !capitalStructureData && !evaluationData) {
        throw new Error("Model outputs are still loading.");
      }

      downloadJsonFile(`${normalizeExportFileStem(ticker, "company")}-model-outputs.json`, {
        exported_at: new Date().toISOString(),
        ticker,
        dupont_mode: dupontMode,
        models: data,
        financials: financialData,
        market_context: marketContextData,
        sector_context: sectorContextData,
        capital_structure: capitalStructureData,
        oil_scenario_overlay: oilScenarioOverlayData,
        latest_evaluation: evaluationData,
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
          { label: "DCF EV", value: formatCompactNumber(modelSummary.dcfEnterpriseValue), accent: modelSummary.dcfEnterpriseValue != null && modelSummary.dcfEnterpriseValue < 0 ? "red" : "cyan" },
          { label: "Piotroski", value: modelSummary.piotroskiLabel, accent: "cyan" },
          { label: "DuPont ROE", value: formatPercent(modelSummary.dupontRoe), accent: modelSummary.dupontRoe != null && modelSummary.dupontRoe < 0 ? "red" : "cyan" },
          { label: "Altman Proxy", value: formatSigned(modelSummary.altmanZ), accent: modelSummary.altmanZ != null && modelSummary.altmanZ < 0 ? "red" : "cyan" }
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

      {showOilScenarioOverlay ? (
        <Panel
          title="Oil Scenario Overlay"
          subtitle={strictOfficialMode ? "Official oil benchmark overlay with manual price entry support when strict mode suppresses cached market prices" : "Fair-value overlay using official oil benchmarks and user-edited scenario inputs on top of the current model base"}
          className="models-page-span-full"
          variant="subtle"
        >
          <OilScenarioOverlayPanel
            ticker={ticker}
            overlay={oilScenarioOverlayData}
            models={models}
            financials={financialData?.financials ?? []}
            priceHistory={financialData?.price_history ?? []}
            strictOfficialMode={strictOfficialMode}
            companySupportStatus={oilSupportStatus}
            companySupportReasons={oilSupportReasons}
          />
        </Panel>
      ) : (
        <div className="models-page-span-full text-muted">
          Oil scenario overlay unavailable: {describeOilOverlayAvailability(oilSupportReasons)}
        </div>
      )}

      <Panel title="Model Analytics" subtitle={loading ? "Loading..." : "Charts and number tables for DCF, DuPont, Piotroski, the Altman proxy, and ratios"} className="models-page-span-full" variant="subtle">
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
        <ModelEvaluationPanel evaluation={evaluationData} />
      </Panel>

      {showMarketContext ? (
        <Panel
          variant="subtle"
          title="Macro Exposure Context"
          subtitle="Official indicators selected from the company's mapped demand, cost, inventory, and rate exposures"
          className="models-page-span-full"
        >
          <MarketContextPanel context={marketContextData} />
        </Panel>
      ) : null}

      {showCapitalStructure ? (
        <Panel
          variant="subtle"
          title="Capital Structure Intelligence"
          subtitle="SEC-derived maturity ladders, debt roll-forwards, payout mix, SBC burden, and dilution bridges alongside the model stack"
          className="models-page-span-full"
        >
          <CapitalStructureIntelligencePanel
            ticker={ticker}
            reloadKey={data?.last_refreshed_at ?? financialData?.last_refreshed_at ?? activeJobId}
            initialPayload={capitalStructureData}
          />
        </Panel>
      ) : null}

      {showSectorContext ? (
        <Panel
          variant="subtle"
          title="Sector Exposure Context"
          subtitle="Official sector plug-ins for power, housing, airlines, air cargo, and agricultural supply-demand exposures"
          className="models-page-span-full"
        >
          <SectorContextPanel context={sectorContextData} />
        </Panel>
      ) : null}

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

async function loadModelsWorkspaceData(ticker: string, dupontMode: DupontMode): Promise<ModelsWorkspaceData> {
  const [modelResult, financialResult, marketContextResult, sectorContextResult, capitalStructureResult, oilScenarioOverlayResult, evaluationResult] = await Promise.allSettled([
    getCompanyModels(ticker, MODEL_NAMES, { dupontMode }),
    getCompanyFinancials(ticker),
    getCompanyMarketContext(ticker),
    getCompanySectorContext(ticker),
    getCompanyCapitalStructure(ticker, { maxPeriods: 6 }),
    getCompanyOilScenarioOverlay(ticker),
    getLatestModelEvaluation(),
  ]);

  const modelData = requireModelsWorkspacePayload(modelResult, "Unable to load models");
  const financialData = requireModelsWorkspacePayload(financialResult, "Unable to load company financials");
  const marketContextData = optionalModelsWorkspacePayload(marketContextResult);
  const sectorContextData = optionalModelsWorkspacePayload(sectorContextResult);
  const capitalStructureData = optionalModelsWorkspacePayload(capitalStructureResult);
  const oilScenarioOverlayData = optionalModelsWorkspacePayload(oilScenarioOverlayResult);
  const evaluationData = optionalModelsWorkspacePayload(evaluationResult);

  return {
    modelData,
    financialData,
    marketContextData,
    sectorContextData,
    capitalStructureData,
    oilScenarioOverlayData,
    evaluationData,
    activeJobId:
      modelData.refresh.job_id ??
      financialData.refresh.job_id ??
      capitalStructureData?.refresh.job_id ??
      oilScenarioOverlayData?.refresh.job_id ??
      marketContextData?.refresh.job_id ??
      sectorContextData?.refresh.job_id ??
      evaluationData?.run?.id?.toString() ?? null
  };
}

function requireModelsWorkspacePayload<T>(result: PromiseSettledResult<T>, fallback: string): T {
  if (result.status === "fulfilled") {
    return result.value;
  }

  throw result.reason instanceof Error ? result.reason : new Error(fallback);
}

function optionalModelsWorkspacePayload<T>(result: PromiseSettledResult<T>): T | null {
  return result.status === "fulfilled" ? result.value : null;
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



function describeOilOverlayAvailability(reasons: string[]): string {
  if (reasons.includes("non_energy_classification")) {
    return "the issuer is not currently classified as an energy or oil-exposed company.";
  }
  if (reasons.includes("oilfield_services_not_supported_v1")) {
    return "v1 does not model oilfield-services economics yet.";
  }
  if (reasons.includes("midstream_not_supported_v1")) {
    return "v1 does not model midstream or pipeline oil economics yet.";
  }
  if (reasons.includes("oil_taxonomy_unresolved_v1")) {
    return "the issuer's oil exposure could not be resolved from the current classification signals.";
  }
  return "this issuer is not currently supported by the oil scenario overlay.";
}



