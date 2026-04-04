"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyResearchHeader } from "@/components/layout/company-research-header";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { OilScenarioOverlayPanel } from "@/components/models/oil-scenario-overlay-panel";
import { DataQualityDiagnostics } from "@/components/ui/data-quality-diagnostics";
import { Panel } from "@/components/ui/panel";
import { SourceFreshnessSummary } from "@/components/ui/source-freshness-summary";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { getCompanyModels, getCompanyOilScenarioOverlay, getLatestModelEvaluation } from "@/lib/api";
import { formatPercent, titleCase } from "@/lib/format";
import { describeOilOverlayAvailability, describeOilSupportReason, resolveOilOverlayEvaluationSummary, supportsOilWorkspace } from "@/lib/oil-workspace";
import type { CompanyModelsResponse, CompanyOilScenarioResponse, ModelEvaluationResponse } from "@/lib/types";

const OIL_OVERLAY_EVALUATION_SUITE_KEY = "oil_overlay_point_in_time_v1";
const OIL_MODEL_NAMES = ["dcf", "residual_income"];

interface OilWorkspaceData {
  modelsData: CompanyModelsResponse | null;
  oilScenarioData: CompanyOilScenarioResponse | null;
  oilEvaluationData: ModelEvaluationResponse | null;
  error: string | null;
}

const SECTION_OPTIONS = [
  { id: "oil-overview", label: "Overview" },
  { id: "oil-workbench", label: "Workbench" },
  { id: "oil-provenance", label: "Provenance" },
];

export default function CompanyOilPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(params.ticker).toUpperCase();
  const {
    company,
    financials = [],
    priceHistory = [],
    loading: workspaceLoading,
    error: workspaceError,
    refreshing,
    refreshState,
    consoleEntries,
    connectionState,
    queueRefresh,
    reloadKey,
  } = useCompanyWorkspace(ticker);
  const [workspaceData, setWorkspaceData] = useState<OilWorkspaceData>({
    modelsData: null,
    oilScenarioData: null,
    oilEvaluationData: null,
    error: null,
  });
  const [loading, setLoading] = useState(true);

  const loadOilWorkspace = useCallback(async () => {
    setLoading(true);
    const [modelsResult, oilScenarioResult, oilEvaluationResult] = await Promise.allSettled([
      getCompanyModels(ticker, OIL_MODEL_NAMES),
      getCompanyOilScenarioOverlay(ticker),
      getLatestModelEvaluation(OIL_OVERLAY_EVALUATION_SUITE_KEY),
    ]);

    const errors: string[] = [];
    const nextWorkspaceData: OilWorkspaceData = {
      modelsData: modelsResult.status === "fulfilled" ? modelsResult.value : null,
      oilScenarioData: oilScenarioResult.status === "fulfilled" ? oilScenarioResult.value : null,
      oilEvaluationData: oilEvaluationResult.status === "fulfilled" ? oilEvaluationResult.value : null,
      error: null,
    };

    if (modelsResult.status === "rejected") {
      errors.push(asErrorMessage(modelsResult.reason, "Unable to load oil base models"));
    }
    if (oilScenarioResult.status === "rejected") {
      errors.push(asErrorMessage(oilScenarioResult.reason, "Unable to load oil scenario workspace"));
    }
    if (oilEvaluationResult.status === "rejected") {
      errors.push(asErrorMessage(oilEvaluationResult.reason, "Unable to load oil evaluation summary"));
    }

    nextWorkspaceData.error = errors.length ? errors.join(" · ") : null;
    setWorkspaceData(nextWorkspaceData);
    setLoading(false);
  }, [ticker]);

  useEffect(() => {
    void loadOilWorkspace();
  }, [loadOilWorkspace, reloadKey]);

  const pageCompany = company ?? workspaceData.modelsData?.company ?? workspaceData.oilScenarioData?.company ?? null;
  const oilSupportStatus = workspaceData.oilScenarioData?.exposure_profile.oil_support_status ?? pageCompany?.oil_support_status ?? "unsupported";
  const oilSupportReasons = workspaceData.oilScenarioData?.exposure_profile.oil_support_reasons ?? pageCompany?.oil_support_reasons ?? [];
  const showOilWorkspace = supportsOilWorkspace(oilSupportStatus);
  const evaluationSummary = useMemo(
    () => resolveOilOverlayEvaluationSummary(ticker, workspaceData.oilEvaluationData),
    [ticker, workspaceData.oilEvaluationData],
  );
  const exposureType = workspaceData.oilScenarioData?.exposure_profile.oil_exposure_type ?? pageCompany?.oil_exposure_type ?? "non_oil";
  const benchmarkLabel = workspaceData.oilScenarioData?.official_base_curve?.label ?? "Pending";
  const sensitivityLabel = workspaceData.oilScenarioData?.sensitivity_source?.kind
    ? titleCase(workspaceData.oilScenarioData.sensitivity_source.kind.replaceAll("_", " "))
    : "Pending";
  const combinedError = [workspaceError, workspaceData.error].filter(Boolean).join(" · ") || null;

  return (
    <CompanyWorkspaceShell
      rail={
        <CompanyUtilityRail
          ticker={ticker}
          companyName={pageCompany?.name ?? null}
          sector={pageCompany?.sector ?? null}
          refreshState={refreshState}
          refreshing={refreshing}
          onRefresh={() => queueRefresh()}
          actionTitle="Oil Workspace Actions"
          actionSubtitle="Refresh company data, return to the main models workspace, or review the latest oil-input provenance."
          primaryActionLabel="Refresh Oil Inputs"
          primaryActionDescription="Queues a company refresh so the latest SEC evidence, benchmark curves, and oil overlay payloads are reloaded."
          secondaryActionHref={`/company/${encodeURIComponent(ticker)}/models`}
          secondaryActionLabel="Back to Models"
          secondaryActionDescription="Return to the valuation stack summary and broader model analytics."
          statusLines={[
            `Support: ${titleCase(oilSupportStatus)}`,
            `Exposure: ${titleCase(exposureType.replaceAll("_", " "))}`,
            `Benchmark: ${benchmarkLabel}`,
          ]}
          consoleEntries={consoleEntries}
          connectionState={connectionState}
        />
      }
    >
      <CompanyResearchHeader
        ticker={ticker}
        title="Oil"
        companyName={pageCompany?.name ?? null}
        sector={pageCompany?.sector ?? null}
        cacheState={pageCompany?.cache_state ?? null}
        description="Dedicated oil workspace for official benchmark curves, direct SEC oil evidence, scenario controls, and point-in-time overlay evaluation."
        facts={[
          { label: "Support", value: titleCase(oilSupportStatus) },
          { label: "Exposure", value: titleCase(exposureType.replaceAll("_", " ")) },
          { label: "Benchmark", value: benchmarkLabel },
          { label: "Sensitivity", value: sensitivityLabel },
        ]}
        summaries={[
          { label: "Curve Points", value: String(workspaceData.oilScenarioData?.official_base_curve?.points?.length ?? 0), accent: "cyan" },
          { label: "Eval Samples", value: evaluationSummary?.sampleCount != null ? String(evaluationSummary.sampleCount) : "—", accent: "gold" },
          { label: "MAE Lift", value: formatSigned(evaluationSummary?.maeLift ?? null), accent: "green" },
          { label: "Improvement Rate", value: formatPercent(evaluationSummary?.improvementRate ?? null), accent: "cyan" },
        ]}
        factsLoading={workspaceLoading || loading}
        summariesLoading={workspaceLoading || loading}
        freshness={{
          cacheState: pageCompany?.cache_state ?? null,
          refreshState,
          loading: workspaceLoading || loading,
          hasData: Boolean(workspaceData.oilScenarioData),
          lastChecked: pageCompany?.last_checked ?? null,
          errors: [combinedError],
        }}
      >
        <OilSectionPicker />
      </CompanyResearchHeader>

      <Panel
        title="Workspace Overview"
        subtitle={showOilWorkspace ? "Quick status, evaluation, and extension readiness before you move into the interactive workbench." : "This company does not currently qualify for the interactive oil workspace."}
        className="models-page-span-full"
        variant="hero"
        bodyId="oil-overview"
      >
        <div className="workspace-card-stack workspace-card-stack-tight">
          {combinedError ? <div className="text-muted">{combinedError}</div> : null}
          <div className="workspace-pill-row">
            <span className="pill">Support {titleCase(oilSupportStatus)}</span>
            <span className="pill">Official Curve {(workspaceData.oilScenarioData?.official_base_curve?.points?.length ?? 0) > 0 ? "Ready" : "Blocked"}</span>
            <span className="pill">Sensitivity {sensitivityLabel}</span>
            {workspaceData.oilScenarioData?.phase2_extensions?.downstream_offset_supported ? <span className="pill">Downstream Offset Active</span> : null}
          </div>
          <div className="text-muted">
            {showOilWorkspace
              ? oilSupportStatus === "partial"
                ? oilSupportReasons.map(describeOilSupportReason).join(" ")
                : "The interactive workbench below combines official oil benchmarks, SEC evidence, realized-spread controls, and PIT evaluation context in one workspace."
              : `Oil workspace unavailable: ${describeOilOverlayAvailability(oilSupportReasons)}`}
          </div>
          {evaluationSummary ? (
            <div className="filing-link-card workspace-card-stack-tight">
              <div className="metric-label">Latest Oil Overlay Evaluation</div>
              <div className="workspace-pill-row">
                <span className="pill">Samples {evaluationSummary.sampleCount ?? "—"}</span>
                <span className="pill">MAE Lift {formatSigned(evaluationSummary.maeLift)}</span>
                <span className="pill">Improvement Rate {formatPercent(evaluationSummary.improvementRate)}</span>
                <span className="pill">As Of {evaluationSummary.asOf ?? "—"}</span>
              </div>
              <div className="text-muted">{evaluationSummary.description}</div>
            </div>
          ) : null}
          <div className="workspace-pill-row">
            <span className="pill">Refiner RAC {workspaceData.oilScenarioData?.phase2_extensions?.refiner_rac_supported ? "Ready" : "Pending"}</span>
            <span className="pill">AEO Presets {workspaceData.oilScenarioData?.phase2_extensions?.aeo_presets_supported ? "Ready" : "Pending"}</span>
          </div>
          {showOilWorkspace ? null : (
            <div>
              <Link href={`/company/${encodeURIComponent(ticker)}/models`} className="ticker-button utility-action-button utility-action-button-secondary utility-action-link-button">
                Return to Models
              </Link>
            </div>
          )}
        </div>
      </Panel>

      <Panel
        title="Oil Workbench"
        subtitle={showOilWorkspace ? "Interactive official-benchmark overlay with scenario controls and direct company evidence." : "Interactive controls stay hidden until the company is at least partially supported for oil modeling."}
        className="models-page-span-full"
        variant="subtle"
        bodyId="oil-workbench"
      >
        {showOilWorkspace ? (
          <OilScenarioOverlayPanel
            ticker={ticker}
            overlay={workspaceData.oilScenarioData}
            models={workspaceData.modelsData?.models ?? []}
            financials={financials}
            priceHistory={priceHistory}
            strictOfficialMode={Boolean(pageCompany?.strict_official_mode)}
            companySupportStatus={oilSupportStatus}
            companySupportReasons={oilSupportReasons}
            oilOverlayEvaluation={workspaceData.oilEvaluationData}
          />
        ) : (
          <div className="text-muted">Oil workspace unavailable: {describeOilOverlayAvailability(oilSupportReasons)}</div>
        )}
      </Panel>

      <Panel
        title="Method & Provenance"
        subtitle="Separate the current overlay inputs from their provenance and from the historical evaluation harness used to judge recent overlay quality."
        className="models-page-span-full"
        variant="subtle"
        bodyId="oil-provenance"
      >
        <div className="workspace-card-stack workspace-card-stack-tight">
          <div className="filing-link-card workspace-card-stack-tight">
            <div className="metric-label">Overlay Provenance</div>
            <SourceFreshnessSummary
              provenance={workspaceData.oilScenarioData?.provenance}
              asOf={workspaceData.oilScenarioData?.as_of}
              lastRefreshedAt={workspaceData.oilScenarioData?.last_refreshed_at}
              sourceMix={workspaceData.oilScenarioData?.source_mix}
              confidenceFlags={workspaceData.oilScenarioData?.confidence_flags}
              emptyMessage="Oil overlay provenance will appear after the official dataset is available."
            />
          </div>
          <div className="filing-link-card workspace-card-stack-tight">
            <div className="metric-label">Overlay Diagnostics</div>
            <DataQualityDiagnostics diagnostics={workspaceData.oilScenarioData?.diagnostics} emptyMessage="Oil overlay diagnostics will appear after the official dataset is populated." />
          </div>
          <div className="filing-link-card workspace-card-stack-tight">
            <div className="metric-label">Phase 2 Readiness</div>
            <div className="workspace-pill-row">
              {(workspaceData.oilScenarioData?.phase2_extensions?.aeo_preset_options ?? []).map((option) => (
                <span key={option.preset_id} className="pill">{option.label} {titleCase(option.status.replaceAll("_", " "))}</span>
              ))}
            </div>
            <div className="text-muted">{workspaceData.oilScenarioData?.phase2_extensions?.refiner_rac_reason ?? workspaceData.oilScenarioData?.phase2_extensions?.aeo_presets_reason ?? "No phase-2 extension notes are attached yet."}</div>
          </div>
        </div>
      </Panel>
    </CompanyWorkspaceShell>
  );
}

function OilSectionPicker() {
  const [selectedSection, setSelectedSection] = useState(SECTION_OPTIONS[0]?.id ?? "oil-overview");

  function jumpToSection(sectionId: string) {
    setSelectedSection(sectionId);
    document.getElementById(sectionId)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div className="oil-section-picker" aria-label="Oil workspace section picker">
      <div className="oil-section-chip-row" aria-label="Oil workspace sections">
        {SECTION_OPTIONS.map((option) => (
          <button
            key={option.id}
            type="button"
            className={`oil-section-chip${selectedSection === option.id ? " is-active" : ""}`}
            onClick={() => jumpToSection(option.id)}
          >
            {option.label}
          </button>
        ))}
      </div>
      <label className="oil-section-select-shell">
        <span className="metric-label">Section</span>
        <select value={selectedSection} onChange={(event) => jumpToSection(event.target.value)} aria-label="Oil workspace section picker">
          {SECTION_OPTIONS.map((option) => (
            <option key={option.id} value={option.id}>{option.label}</option>
          ))}
        </select>
      </label>
    </div>
  );
}

function formatSigned(value: number | null): string {
  if (value == null) {
    return "—";
  }
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2, signDisplay: "exceptZero" }).format(value);
}

function asErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}