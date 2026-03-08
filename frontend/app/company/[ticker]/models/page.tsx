"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import type { ColDef } from "ag-grid-community";

import { DenseGrid } from "@/components/grid/dense-grid";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { DcfScenarioAnalysis } from "@/components/models/dcf-scenario-analysis";
import { FinancialHealthScore } from "@/components/models/financial-health-score";
import { InvestmentSummaryPanel } from "@/components/models/investment-summary-panel";
import { ModelDashboard } from "@/components/models/model-dashboard";
import { Panel } from "@/components/ui/panel";
import { StatusPill } from "@/components/ui/status-pill";
import { useJobStream } from "@/hooks/use-job-stream";
import { getCompanyFinancials, getCompanyModels, refreshCompany } from "@/lib/api";
import { MODEL_NAMES } from "@/lib/constants";
import { formatCompactNumber, formatDate, formatPercent, titleCase } from "@/lib/format";
import { formatPiotroskiDisplay, resolvePiotroskiScoreState } from "@/lib/piotroski";
import type { CompanyFinancialsResponse, CompanyModelsResponse, ModelPayload } from "@/lib/types";

interface ModelsWorkspaceData {
  modelData: CompanyModelsResponse;
  financialData: CompanyFinancialsResponse;
  activeJobId: string | null;
}

export default function CompanyModelsPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(params.ticker).toUpperCase();
  const [data, setData] = useState<CompanyModelsResponse | null>(null);
  const [financialData, setFinancialData] = useState<CompanyFinancialsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [settledJobIds, setSettledJobIds] = useState<string[]>([]);
  const { consoleEntries, connectionState, lastEvent } = useJobStream(activeJobId);
  const models = useMemo(() => data?.models ?? [], [data?.models]);
  const hasModels = models.length > 0;
  const dcfModel = useMemo(() => models.find((model) => model.model_name === "dcf") ?? null, [models]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        setSettledJobIds([]);
        const workspaceData = await loadModelsWorkspaceData(ticker);
        if (!cancelled) {
          setData(workspaceData.modelData);
          setFinancialData(workspaceData.financialData);
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
  }, [ticker]);

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

    void loadModelsWorkspaceData(ticker)
      .then((workspaceData) => {
        if (cancelled) {
          return;
        }
        setError(null);
        setData(workspaceData.modelData);
        setFinancialData(workspaceData.financialData);
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
  }, [activeJobId, lastEvent, settledJobIds, ticker]);

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
        valueGetter: ({ data: row }) => row?.result?.status ?? "ready"
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

    return {
      cachedCount: models.length,
      latestComputed,
      dcfEnterpriseValue: asNumber(byName.dcf?.result?.enterprise_value_proxy),
      dupontRoe: asNumber(byName.dupont?.result?.return_on_equity),
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
        <CompanyUtilityRail
          ticker={ticker}
          refreshState={data?.refresh ?? financialData?.refresh ?? null}
          refreshing={refreshing}
          onRefresh={queueRefresh}
          actionTitle="Next Steps"
          actionSubtitle="Refresh the latest data for this ticker or return to financial statements."
          primaryActionLabel="Refresh Model Inputs"
          primaryActionDescription="Updates filings, market prices, and model calculations in the background."
          secondaryActionHref={`/company/${encodeURIComponent(ticker)}/financials`}
          secondaryActionLabel="Open Financials"
          secondaryActionDescription="Review statements, charts, and historical company results."
          statusLines={[
            `Available models: ${modelSummary.cachedCount}/${MODEL_NAMES.length}`,
            `Last updated: ${modelSummary.latestComputed ? formatDate(modelSummary.latestComputed) : loading ? "Loading..." : "Preparing data"}`,
            `Price history points available: ${(financialData?.price_history ?? []).length.toLocaleString()}`
          ]}
          consoleEntries={consoleEntries}
          connectionState={connectionState}
          actionTone="gold"
        />
      }
      mainClassName="models-page-grid"
    >
      <Panel title="Valuation Models" subtitle={data?.company?.name ?? ticker} aside={data ? <StatusPill state={data.refresh} /> : undefined} className="model-hero models-page-hero">
        <div style={{ display: "grid", gap: 14 }}>
          <div className="metric-grid">
            <div className="metric-card">
              <div className="metric-label">Ticker</div>
              <div className="metric-value neon-green">{ticker}</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Available Models</div>
              <div className="metric-value neon-cyan">{modelSummary.cachedCount}/{MODEL_NAMES.length}</div>
            </div>
          </div>

          <div className="model-summary-strip">
            <SummaryCard label="Last Updated" value={modelSummary.latestComputed ? formatDate(modelSummary.latestComputed) : loading ? "Loading..." : "Preparing data"} accent="cyan" />
            <SummaryCard label="DCF EV" value={formatCompactNumber(modelSummary.dcfEnterpriseValue)} accent="green" />
            <SummaryCard label="DuPont ROE" value={formatPercent(modelSummary.dupontRoe)} accent="gold" />
            <SummaryCard label="Piotroski" value={modelSummary.piotroskiLabel} accent="green" />
            <SummaryCard label="Altman Proxy" value={formatSigned(modelSummary.altmanZ)} accent="cyan" />
          </div>

          <div className="sparkline-note">Start with Investment Summary for the headline view, then use Financial Health Score, DCF Scenario Analysis, and Model Analytics for the full model output.</div>
        </div>
      </Panel>


      <Panel
        title="Investment Summary"
        subtitle={
          loading
            ? "Loading valuation, quality, and market inputs..."
            : "Quick valuation snapshot based on company results and market prices"
        }
        className="models-page-span-full"
      >
        <InvestmentSummaryPanel ticker={ticker} models={models} financials={financialData?.financials ?? []} priceHistory={financialData?.price_history ?? []} />
      </Panel>

      <Panel title="Financial Health Score" subtitle={loading ? "Loading health inputs..." : "Profitability, strength, growth, and overall health on a 0-10 scale"} className="models-page-span-full">
        <FinancialHealthScore models={models} financials={financialData?.financials ?? []} />
      </Panel>

      <Panel title="DCF Scenario Analysis" subtitle={loading ? "Loading DCF inputs..." : "Interactive bear, base, and bull valuation range"} className="models-page-span-full">
        <DcfScenarioAnalysis ticker={ticker} dcfModel={dcfModel} financials={financialData?.financials ?? []} priceHistory={financialData?.price_history ?? []} />
      </Panel>

      <Panel title="Model Analytics" subtitle={loading ? "Loading..." : "Charts and number tables for DCF, DuPont, Piotroski, the Altman proxy, and ratios"} className="models-page-span-full">
        {hasModels ? <ModelDashboard models={models} /> : <div className="text-muted">No model results yet. Once financial data is ready, this page will fill in automatically.</div>}
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
            <DenseGrid rowData={models} columnDefs={columns} height={280} />
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

async function loadModelsWorkspaceData(ticker: string): Promise<ModelsWorkspaceData> {
  const [modelData, financialData] = await Promise.all([getCompanyModels(ticker, MODEL_NAMES), getCompanyFinancials(ticker)]);

  return {
    modelData,
    financialData,
    activeJobId: modelData.refresh.job_id ?? financialData.refresh.job_id
  };
}

function SummaryCard({ label, value, accent }: { label: string; value: string; accent: "green" | "cyan" | "gold" }) {
  return (
    <div className={`summary-card accent-${accent}`}>
      <div className="summary-card-label">{label}</div>
      <div className="summary-card-value">{value}</div>
    </div>
  );
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



