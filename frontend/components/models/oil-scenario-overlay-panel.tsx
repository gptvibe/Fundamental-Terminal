"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { DataQualityDiagnostics } from "@/components/ui/data-quality-diagnostics";
import { SourceFreshnessSummary } from "@/components/ui/source-freshness-summary";
import { showAppToast } from "@/lib/app-toast";
import { downloadJsonFile, exportRowsToCsv, normalizeExportFileStem } from "@/lib/export";
import { titleCase } from "@/lib/format";
import {
  annualizeOilCurveSeries,
  buildDefaultShortTermCurve,
  computeOilOverlayScenario,
  humanizeFlag,
  resolveBaseFairValuePerShare,
  resolveBenchmarkOptions,
  resolveDatasetAnnualSensitivity,
  resolveDefaultLongTermAnchor,
  resolveDilutedShares,
} from "@/lib/oil-overlay";
import { describeOilSupportReason, resolveOilOverlayEvaluationSummary } from "@/lib/oil-workspace";
import type {
  CompanyOilScenarioResponse,
  FinancialPayload,
  ModelEvaluationResponse,
  ModelPayload,
  PriceHistoryPoint,
} from "@/lib/types";

interface OilScenarioOverlayPanelProps {
  ticker: string;
  overlay: CompanyOilScenarioResponse | null;
  models: ModelPayload[];
  financials: FinancialPayload[];
  priceHistory: PriceHistoryPoint[];
  strictOfficialMode: boolean;
  companySupportStatus: "supported" | "partial" | "unsupported";
  companySupportReasons: string[];
  oilOverlayEvaluation: ModelEvaluationResponse | null;
}

type SensitivitySource = "manual" | "dataset";
type RealizedSpreadMode = "hold_current_spread" | "mean_revert" | "custom_spread" | "benchmark_only";
type OverlayMode = "simple" | "advanced";
type ScenarioPresetId = "official_base" | "bull" | "bear" | "flat" | "recession" | "custom";

const SCENARIO_PRESETS: Array<{ id: ScenarioPresetId; label: string }> = [
  { id: "official_base", label: "Official Base" },
  { id: "bull", label: "Bull" },
  { id: "bear", label: "Bear" },
  { id: "flat", label: "Flat" },
  { id: "recession", label: "Recession / lower-for-longer" },
  { id: "custom", label: "Custom" },
];

interface CurveDisplayPoint {
  year: number;
  basePrice: number;
  scenarioPrice: number;
}

export function OilScenarioOverlayPanel({
  ticker,
  overlay,
  models,
  financials,
  priceHistory,
  strictOfficialMode,
  companySupportStatus,
  companySupportReasons,
  oilOverlayEvaluation,
}: OilScenarioOverlayPanelProps) {
  const baseFairValuePerShare = useMemo(() => resolveBaseFairValuePerShare(models), [models]);
  const dilutedShares = useMemo(() => resolveDilutedShares(financials), [financials]);
  const benchmarkOptions = useMemo(
    () =>
      overlay?.user_editable_defaults?.benchmark_options?.length
        ? overlay.user_editable_defaults.benchmark_options
        : resolveBenchmarkOptions(overlay?.benchmark_series ?? []),
    [overlay?.benchmark_series, overlay?.user_editable_defaults?.benchmark_options],
  );

  const defaultBenchmarkId = useMemo(
    () =>
      resolveDefaultBenchmarkId(
        benchmarkOptions,
        overlay?.user_editable_defaults?.benchmark_id,
        overlay?.user_editable_defaults?.realized_spread_reference_benchmark,
      ),
    [benchmarkOptions, overlay?.user_editable_defaults?.benchmark_id, overlay?.user_editable_defaults?.realized_spread_reference_benchmark],
  );
  const [benchmarkId, setBenchmarkId] = useState(defaultBenchmarkId);

  const selectedBenchmark = useMemo(
    () => (overlay?.benchmark_series ?? []).find((series) => series.series_id === benchmarkId) ?? null,
    [benchmarkId, overlay?.benchmark_series],
  );
  const annualBaseCurve = useMemo(() => annualizeOilCurveSeries(selectedBenchmark), [selectedBenchmark]);
  const defaultShortTermCurve = useMemo(() => buildDefaultShortTermCurve(annualBaseCurve), [annualBaseCurve]);
  const defaultLongTermAnchor = useMemo(
    () =>
      overlay?.user_editable_defaults?.long_term_anchor ??
      resolveDefaultLongTermAnchor(annualBaseCurve) ??
      overlay?.user_editable_defaults?.current_oil_price ??
      null,
    [annualBaseCurve, overlay?.user_editable_defaults?.current_oil_price, overlay?.user_editable_defaults?.long_term_anchor],
  );

  const latestPrice = priceHistory.at(-1)?.close ?? null;
  const supportStatus =
    overlay?.exposure_profile.oil_support_status === "supported" || overlay?.exposure_profile.oil_support_status === "partial"
      ? overlay.exposure_profile.oil_support_status
      : companySupportStatus;
  const supportReasons = overlay?.exposure_profile.oil_support_reasons?.length
    ? overlay.exposure_profile.oil_support_reasons
    : companySupportReasons;
  const datasetSensitivity = useMemo(() => resolveDatasetAnnualSensitivity(overlay?.sensitivity), [overlay?.sensitivity]);
  const defaultSensitivitySource = useMemo<SensitivitySource>(() => (datasetSensitivity == null ? "manual" : "dataset"), [datasetSensitivity]);
  const realizedSpreadSupported = Boolean(overlay?.requirements?.realized_spread_supported);
  const defaultRealizedSpreadMode = useMemo<RealizedSpreadMode>(
    () => ((overlay?.user_editable_defaults?.realized_spread_mode as RealizedSpreadMode | undefined) ?? "benchmark_only"),
    [overlay?.user_editable_defaults?.realized_spread_mode],
  );
  const defaultCustomRealizedSpread = overlay?.user_editable_defaults?.custom_realized_spread;
  const defaultMeanReversionYears = overlay?.user_editable_defaults?.mean_reversion_years ?? 3;
  const defaultDownstreamOffsetPercent = overlay?.phase2_extensions?.downstream_offset_percent ?? 0;
  const hasOfficialCurve = annualBaseCurve.length > 0;
  const oilEvaluationSummary = useMemo(
    () => resolveOilOverlayEvaluationSummary(ticker, oilOverlayEvaluation),
    [ticker, oilOverlayEvaluation],
  );

  const [mode, setMode] = useState<OverlayMode>("simple");
  const [activePreset, setActivePreset] = useState<ScenarioPresetId>("official_base");
  const [shortTermCurve, setShortTermCurve] = useState(defaultShortTermCurve);
  const [longTermAnchorInput, setLongTermAnchorInput] = useState(
    defaultLongTermAnchor == null ? "" : formatNumberInput(defaultLongTermAnchor, 2),
  );
  const [fadeYearsInput, setFadeYearsInput] = useState(String(overlay?.user_editable_defaults?.fade_years ?? 2));
  const [sensitivitySource, setSensitivitySource] = useState<SensitivitySource>(defaultSensitivitySource);
  const [manualSensitivityInput, setManualSensitivityInput] = useState(overlay?.user_editable_defaults?.annual_after_tax_sensitivity == null ? "" : formatNumberInput(overlay.user_editable_defaults.annual_after_tax_sensitivity, 2));
  const [currentSharePriceInput, setCurrentSharePriceInput] = useState(latestPrice == null ? "" : formatNumberInput(latestPrice, 2));
  const [realizedSpreadMode, setRealizedSpreadMode] = useState<RealizedSpreadMode>(defaultRealizedSpreadMode);
  const [customRealizedSpreadInput, setCustomRealizedSpreadInput] = useState(
    defaultCustomRealizedSpread == null ? "" : formatNumberInput(defaultCustomRealizedSpread, 2),
  );
  const [downstreamOffsetInput, setDownstreamOffsetInput] = useState(String(defaultDownstreamOffsetPercent));

  useEffect(() => {
    setBenchmarkId(defaultBenchmarkId);
  }, [defaultBenchmarkId]);

  useEffect(() => {
    setShortTermCurve(defaultShortTermCurve);
    setLongTermAnchorInput(defaultLongTermAnchor == null ? "" : formatNumberInput(defaultLongTermAnchor, 2));
    setActivePreset("official_base");
  }, [defaultLongTermAnchor, defaultShortTermCurve, benchmarkId]);

  useEffect(() => {
    setCurrentSharePriceInput(latestPrice == null ? "" : formatNumberInput(latestPrice, 2));
  }, [latestPrice, strictOfficialMode]);

  useEffect(() => {
    setSensitivitySource(defaultSensitivitySource);
  }, [defaultSensitivitySource]);

  useEffect(() => {
    setRealizedSpreadMode(defaultRealizedSpreadMode);
    setCustomRealizedSpreadInput(defaultCustomRealizedSpread == null ? "" : formatNumberInput(defaultCustomRealizedSpread, 2));
  }, [defaultCustomRealizedSpread, defaultRealizedSpreadMode]);

  useEffect(() => {
    setDownstreamOffsetInput(String(defaultDownstreamOffsetPercent));
  }, [defaultDownstreamOffsetPercent]);

  const activeSensitivity = sensitivitySource === "dataset" ? datasetSensitivity : parseNumber(manualSensitivityInput);
  const currentSharePrice = parseNumber(currentSharePriceInput) ?? latestPrice;
  const fadeYears = Math.max(0, Number.parseInt(fadeYearsInput || "0", 10) || 0);
  const longTermAnchor = parseNumber(longTermAnchorInput);
  const customRealizedSpread = parseNumber(customRealizedSpreadInput);
  const downstreamOffsetPercent = parseNumber(downstreamOffsetInput) ?? 0;

  const overlayResult = useMemo(
    () =>
      computeOilOverlayScenario({
        baseFairValuePerShare,
        officialBaseCurve: annualBaseCurve,
        userEditedShortTermCurve: shortTermCurve,
        userLongTermAnchor: longTermAnchor,
        fadeYears,
        annualAfterTaxOilSensitivity: activeSensitivity,
        dilutedShares,
        sensitivitySourceKind:
          sensitivitySource === "dataset"
            ? overlay?.sensitivity_source?.kind === "disclosed"
              ? "disclosed"
              : "derived_from_official"
            : "manual_override",
        currentSharePrice,
        realizedSpreadMode: realizedSpreadSupported ? realizedSpreadMode : "benchmark_only",
        currentRealizedSpread: overlay?.user_editable_defaults?.current_realized_spread ?? null,
        customRealizedSpread,
        meanReversionTargetSpread: overlay?.user_editable_defaults?.mean_reversion_target_spread ?? 0,
        meanReversionYears: defaultMeanReversionYears,
        realizedSpreadReferenceBenchmark: overlay?.user_editable_defaults?.realized_spread_reference_benchmark ?? null,
        downstreamOffsetPercent,
        annualDiscountRate: 0.1,
        oilSupportStatus: supportStatus,
        confidenceFlags: [...(overlay?.confidence_flags ?? []), ...(overlay?.sensitivity?.confidence_flags ?? [])],
      }),
    [
      activeSensitivity,
      annualBaseCurve,
      baseFairValuePerShare,
      currentSharePrice,
      customRealizedSpread,
      defaultMeanReversionYears,
      dilutedShares,
      downstreamOffsetPercent,
      fadeYears,
      longTermAnchor,
      overlay?.confidence_flags,
      overlay?.sensitivity?.confidence_flags,
      overlay?.sensitivity_source?.kind,
      overlay?.user_editable_defaults?.current_realized_spread,
      overlay?.user_editable_defaults?.mean_reversion_target_spread,
      overlay?.user_editable_defaults?.realized_spread_reference_benchmark,
      realizedSpreadMode,
      realizedSpreadSupported,
      sensitivitySource,
      shortTermCurve,
      supportStatus,
    ],
  );

  const confidenceReasons = useMemo(
    () =>
      Array.from(
        new Set([
          ...supportReasons.map(describeOilSupportReason),
          ...(overlay?.confidence_flags ?? []).map(humanizeFlag),
          ...overlayResult.confidenceFlags.map(humanizeFlag),
        ]),
      ).filter(Boolean),
    [overlay?.confidence_flags, overlayResult.confidenceFlags, supportReasons],
  );

  const curvePreview = useMemo(
    () =>
      buildCurveDisplayData({
        annualBaseCurve,
        shortTermCurve,
        longTermAnchor,
        fallbackLevel: overlay?.user_editable_defaults?.current_oil_price ?? overlay?.official_base_curve?.points?.at(-1)?.price ?? null,
      }),
    [annualBaseCurve, longTermAnchor, overlay?.official_base_curve?.points, overlay?.user_editable_defaults?.current_oil_price, shortTermCurve],
  );

  const editableNodeYears = useMemo(() => {
    if (shortTermCurve.length) {
      return shortTermCurve.map((point) => point.year);
    }
    return curvePreview.slice(0, Math.min(3, curvePreview.length)).map((point) => point.year);
  }, [curvePreview, shortTermCurve]);

  const supportBanner = resolveSupportBanner(supportStatus);
  const missingSensitivityGuidance = supportStatus === "partial" && datasetSensitivity == null;
  const isLoadingShell = !overlay;
  const manualPriceRequired = Boolean(overlay?.requirements?.manual_price_required);

  const whatChangedRows = useMemo(
    () =>
      buildWhatChangedRows({
        annualBaseCurve,
        shortTermCurve,
        longTermAnchor,
        sensitivitySource,
        activeSensitivity,
        realizedSpreadMode: realizedSpreadSupported ? realizedSpreadMode : "benchmark_only",
      }),
    [activeSensitivity, annualBaseCurve, longTermAnchor, realizedSpreadMode, realizedSpreadSupported, sensitivitySource, shortTermCurve],
  );

  const blockedReasons = useMemo(() => buildOverlayBlockedReasons(overlay), [overlay]);

  function applyPreset(preset: Exclude<ScenarioPresetId, "custom">) {
    const next = buildPresetCurve(preset, annualBaseCurve, defaultShortTermCurve, parseNumber(longTermAnchorInput));
    setShortTermCurve(next.points);
    if (next.anchor != null) {
      setLongTermAnchorInput(formatNumberInput(next.anchor, 2));
    }
    setActivePreset(preset);
  }

  function handleCurveNodeChange(year: number, value: string) {
    const parsed = parseNumber(value);
    setShortTermCurve((current) => {
      const existing = current.find((point) => point.year === year);
      if (existing) {
        return current.map((point) => (point.year === year && parsed != null ? { ...point, price: parsed } : point));
      }
      if (parsed == null) {
        return current;
      }
      return [...current, { year, price: parsed }].sort((left, right) => left.year - right.year);
    });
    setActivePreset("custom");
  }

  async function handleExportJson() {
    try {
      downloadJsonFile(`${normalizeExportFileStem(ticker, "company")}-oil-scenario-overlay.json`, {
        exported_at: new Date().toISOString(),
        ticker,
        benchmark_id: benchmarkId,
        support_status: supportStatus,
        support_reasons: supportReasons,
        controls: {
          short_term_curve: shortTermCurve,
          long_term_anchor: longTermAnchor,
          fade_years: fadeYears,
          sensitivity_source: sensitivitySource,
          annual_after_tax_sensitivity: activeSensitivity,
          current_share_price: currentSharePrice,
          realized_spread_mode: realizedSpreadSupported ? realizedSpreadMode : "benchmark_only",
          current_realized_spread: overlay?.user_editable_defaults?.current_realized_spread ?? null,
          custom_realized_spread: customRealizedSpread,
          mean_reversion_target_spread: overlay?.user_editable_defaults?.mean_reversion_target_spread ?? 0,
          mean_reversion_years: defaultMeanReversionYears,
          downstream_offset_percent: downstreamOffsetPercent,
          base_fair_value_per_share: baseFairValuePerShare,
          diluted_shares: dilutedShares,
        },
        overlay_result: overlayResult,
        official_overlay_payload: overlay,
      });
      showAppToast({ message: "Oil scenario overlay exported as JSON.", tone: "info" });
    } catch (error) {
      showAppToast({ message: error instanceof Error ? error.message : "Unable to export oil overlay JSON.", tone: "danger" });
    }
  }

  async function handleExportCsv() {
    try {
      exportRowsToCsv(
        `${normalizeExportFileStem(ticker, "company")}-oil-scenario-overlay.csv`,
        overlayResult.yearlyDeltas.map((item) => ({
          year: item.year,
          base_oil_price: item.baseOilPrice,
          scenario_oil_price: item.scenarioOilPrice,
          oil_price_delta: item.oilPriceDelta,
          base_realized_price: item.baseRealizedPrice,
          scenario_realized_price: item.scenarioRealizedPrice,
          realized_price_delta: item.realizedPriceDelta,
          earnings_delta_after_tax: item.earningsDeltaAfterTax,
          per_share_delta: item.perShareDelta,
          present_value_per_share: item.presentValuePerShare,
          discount_factor: item.discountFactor,
        })),
      );
      showAppToast({ message: "Oil scenario overlay exported as CSV.", tone: "info" });
    } catch (error) {
      showAppToast({ message: error instanceof Error ? error.message : "Unable to export oil overlay CSV.", tone: "danger" });
    }
  }

  return (
    <div className="oil-workbench-shell workspace-card-stack">
      <div className="valuation-card-header">
        <div>
          <div className="valuation-card-kicker">Scenario Workbench</div>
          <div className="valuation-card-title">Oil Scenario Overlay</div>
        </div>
        <div className="valuation-card-subtitle">
          Stress-test fair value using oil-price scenarios, with confidence context and source transparency designed for investor decision-making.
        </div>
      </div>

      <div className="oil-mode-row" aria-label="Oil overlay mode">
        <button type="button" className={`oil-mode-chip${mode === "simple" ? " is-active" : ""}`} onClick={() => setMode("simple")}>
          Simple View
        </button>
        <button type="button" className={`oil-mode-chip${mode === "advanced" ? " is-active" : ""}`} onClick={() => setMode("advanced")}>
          Advanced View
        </button>
      </div>

      <TopSummaryStrip
        loading={isLoadingShell}
        baseFairValuePerShare={baseFairValuePerShare}
        scenarioFairValuePerShare={overlayResult.scenarioFairValuePerShare}
        deltaVsBasePerShare={overlayResult.deltaVsBasePerShare}
        impliedUpsideDownside={overlayResult.impliedUpsideDownside}
        epsDeltaPerDollarOil={overlayResult.epsDeltaPerDollarOil}
      />

      <div className={`oil-support-banner tone-${supportBanner.tone}`}>
        <div className="oil-support-banner-title">{supportBanner.title}</div>
        <div className="oil-support-banner-copy">{supportBanner.copy}</div>
      </div>

      {blockedReasons.length ? (
        <div className="filing-link-card workspace-card-stack-tight">
          <div className="metric-label">Input Availability</div>
          <ul className="oil-overlay-reasons">
            {blockedReasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
          <div className="text-muted oil-overlay-help">Use the Refresh Oil Inputs action from the utility rail to retry missing official inputs.</div>
        </div>
      ) : null}

      <div className="oil-workbench-grid">
        <section className="oil-workbench-primary workspace-card-stack-tight">
          <div className="filing-link-card workspace-card-stack-tight">
            <div className="metric-label">Scenario Builder (Oil Price, $/bbl)</div>

            <div className="oil-preset-row" aria-label="Scenario presets">
              {SCENARIO_PRESETS.map((preset) => (
                <button
                  key={preset.id}
                  type="button"
                  className={`oil-preset-chip${activePreset === preset.id ? " is-active" : ""}`}
                  onClick={() => {
                    if (preset.id !== "custom") {
                      applyPreset(preset.id);
                    }
                  }}
                  disabled={preset.id === "custom"}
                >
                  {preset.label}
                </button>
              ))}
            </div>

            <div className="oil-curve-chart-shell" aria-label="Oil curve preview chart">
              {isLoadingShell ? (
                <div className="oil-loading-shell" aria-label="Oil chart loading state">
                  <div className="oil-loading-line" />
                  <div className="oil-loading-line short" />
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={curvePreview} margin={{ top: 8, right: 12, left: 6, bottom: 8 }}>
                    <CartesianGrid stroke="rgba(148, 163, 184, 0.22)" vertical={false} />
                    <XAxis dataKey="year" stroke="var(--text-muted)" />
                    <YAxis
                      stroke="var(--text-muted)"
                      tickFormatter={(value) => formatDollarPerBarrel(value)}
                      domain={[
                        (dataMin: number) => Math.floor((dataMin - 2) / 5) * 5,
                        (dataMax: number) => Math.ceil((dataMax + 2) / 5) * 5,
                      ]}
                    />
                    <Tooltip
                      formatter={(value: number) => formatDollarPerBarrel(value)}
                      labelFormatter={(value) => `Year ${value}`}
                    />
                    <Line type="monotone" dataKey="basePrice" name="Official base" stroke="#38bdf8" strokeWidth={2.5} dot={{ r: 3 }} connectNulls />
                    <Line type="monotone" dataKey="scenarioPrice" name="Scenario" stroke="#f59e0b" strokeWidth={2.5} dot={{ r: 4 }} connectNulls />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>
            <div className="workspace-pill-row">
              <span className="pill">Blue: Official benchmark curve</span>
              <span className="pill">Amber: Scenario curve</span>
              <span className="pill">Units: $/bbl</span>
            </div>

            <div className="oil-node-editor-grid">
              {editableNodeYears.map((year) => {
                const value = shortTermCurve.find((point) => point.year === year)?.price ?? curvePreview.find((point) => point.year === year)?.scenarioPrice ?? null;
                return (
                  <label key={year} className="oil-compact-field">
                    <span className="metric-label">Scenario {year} ($/bbl)</span>
                    <input
                      aria-label={`Scenario node ${year}`}
                      type="number"
                      step="0.1"
                      value={value == null ? "" : formatNumberInput(value, 1)}
                      onChange={(event) => handleCurveNodeChange(year, event.target.value)}
                    />
                  </label>
                );
              })}
            </div>

            {!hasOfficialCurve ? (
              <div className="oil-guided-empty-state">
                <div className="oil-guided-empty-title">Official benchmark coverage is limited right now.</div>
                <div className="text-muted">
                  A provisional curve is shown so you can still frame upside and downside ranges. Confidence improves once official annual benchmark points are fully populated.
                </div>
              </div>
            ) : null}
          </div>

          <div className="filing-link-card workspace-card-stack-tight">
            <div className="metric-label">Fair Value Bridge</div>
            <div className="oil-bridge-grid">
              <BridgeCard label="Base Fair Value" value={formatCurrency(baseFairValuePerShare)} />
              <BridgeCard label="Oil Overlay Impact" value={formatSignedCurrency(overlayResult.deltaVsBasePerShare)} tone="impact" />
              <BridgeCard label="Scenario Fair Value" value={formatCurrency(overlayResult.scenarioFairValuePerShare)} tone="result" />
            </div>
            <div className="metric-label">What changed?</div>
            <ul className="oil-overlay-reasons">
              {whatChangedRows.map((row) => (
                <li key={row}>{row}</li>
              ))}
            </ul>
            {manualPriceRequired ? (
              <div className="oil-guided-empty-state">
                <div className="oil-guided-empty-title">Manual price check recommended</div>
                <div className="text-muted">Strict-official requirements indicate current price should be verified manually before final interpretation.</div>
              </div>
            ) : null}
          </div>
        </section>

        <aside className="oil-workbench-secondary workspace-card-stack-tight">
          <div className="filing-link-card workspace-card-stack-tight">
            <div className="metric-label">Market Assumptions</div>

            <label className="oil-compact-field">
              <span className="metric-label">Benchmark Series</span>
              <select aria-label="Benchmark Selector" value={benchmarkId} onChange={(event) => setBenchmarkId(event.target.value)}>
                {benchmarkOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <span className="text-muted oil-overlay-help">This defines the official reference curve used for scenario deltas ($/bbl).</span>
            </label>

            <label className="oil-compact-field">
              <span className="metric-label">Long-Term Anchor ($/bbl)</span>
              <input
                aria-label="Long-term anchor input"
                type="number"
                step="0.1"
                value={longTermAnchorInput}
                onChange={(event) => {
                  setLongTermAnchorInput(event.target.value);
                  setActivePreset("custom");
                }}
              />
              <span className="text-muted oil-overlay-help">Long-run oil assumption after near-term scenario years fade out.</span>
            </label>
          </div>

          <div className="filing-link-card workspace-card-stack-tight">
            <div className="metric-label">Company Sensitivity</div>
            {missingSensitivityGuidance ? (
              <div className="oil-guided-empty-state" aria-label="Sensitivity guidance">
                <div className="oil-guided-empty-title">Sensitivity input is missing for this partially supported profile.</div>
                <div className="text-muted">
                  Recommended next action: use a conservative manual after-tax sensitivity based on recent disclosures or peer context, then validate with confidence reasons below.
                </div>
              </div>
            ) : null}
            <label className="oil-compact-field">
              <span className="metric-label">Sensitivity Source</span>
              <select value={sensitivitySource} onChange={(event) => setSensitivitySource(event.target.value as SensitivitySource)}>
                <option value="manual">Manual</option>
                <option value="dataset" disabled={datasetSensitivity == null}>
                  {overlay?.sensitivity_source?.kind === "disclosed" ? "SEC disclosed" : "Derived official"}
                  {datasetSensitivity == null ? " (unavailable)" : ""}
                </option>
              </select>
              <span className="text-muted oil-overlay-help">Choose SEC/official-derived sensitivity for consistency, or manual for scenario experimentation.</span>
            </label>
            <label className="oil-compact-field">
              <span className="metric-label">Annual After-Tax Sensitivity (USD mm per $1 oil)</span>
              <input
                aria-label="Annual after-tax sensitivity input"
                type="number"
                step="0.01"
                value={
                  sensitivitySource === "manual"
                    ? manualSensitivityInput
                    : datasetSensitivity == null
                      ? ""
                      : formatNumberInput(datasetSensitivity, 2)
                }
                onChange={(event) => setManualSensitivityInput(event.target.value)}
                disabled={sensitivitySource !== "manual"}
              />
              <span className="text-muted oil-overlay-help">How much annual after-tax earnings typically change for a $1/bbl oil move.</span>
            </label>
          </div>

          <div className="filing-link-card workspace-card-stack-tight">
            <div className="metric-label">Price Context</div>
            <label className="oil-compact-field">
              <span className="metric-label">Current Share Price ($)</span>
              <input
                aria-label="Current share price input"
                type="number"
                step="0.01"
                value={currentSharePriceInput}
                onChange={(event) => setCurrentSharePriceInput(event.target.value)}
                placeholder={strictOfficialMode ? "Required in strict mode" : "Optional"}
              />
              <span className="text-muted oil-overlay-help">
                {strictOfficialMode
                  ? "Strict-official mode may require manual entry if official closing-price data is unavailable."
                  : "Auto-filled from latest cached close when available; you can override for scenario testing."}
              </span>
            </label>
            <div className="workspace-pill-row">
              <span className="pill">Diluted Shares {formatCompact(dilutedShares)}</span>
              <span className="pill">Confidence {titleCase(overlayResult.modelStatus)}</span>
            </div>
          </div>

          <details className="subtle-details" open={mode === "advanced"}>
            <summary>Advanced Modeling Controls</summary>
            <div className="workspace-card-stack-tight">
              <label className="oil-compact-field">
                <span className="metric-label">Fade Years</span>
                <input
                  aria-label="Fade years slider"
                  type="range"
                  min="0"
                  max="10"
                  value={fadeYears}
                  onChange={(event) => setFadeYearsInput(event.target.value)}
                />
                <input
                  aria-label="Fade years input"
                  type="number"
                  min="0"
                  max="10"
                  step="1"
                  value={fadeYearsInput}
                  onChange={(event) => setFadeYearsInput(event.target.value)}
                />
                <span className="text-muted oil-overlay-help">Years required to fade from edited points into the long-term anchor.</span>
              </label>

              {overlay?.phase2_extensions?.downstream_offset_supported ? (
                <label className="oil-compact-field">
                  <span className="metric-label">Downstream Offset (%)</span>
                  <input
                    aria-label="Downstream offset percent input"
                    type="number"
                    min="0"
                    max="100"
                    step="1"
                    value={downstreamOffsetInput}
                    onChange={(event) => setDownstreamOffsetInput(event.target.value)}
                    disabled={sensitivitySource === "dataset" && overlay?.sensitivity_source?.kind === "disclosed"}
                  />
                  <span className="text-muted oil-overlay-help">Use for integrated profiles when downstream businesses offset upstream oil sensitivity.</span>
                </label>
              ) : null}

              {realizedSpreadSupported ? (
                <>
                  <label className="oil-compact-field">
                    <span className="metric-label">Realized Spread Mode</span>
                    <select aria-label="Realized spread mode" value={realizedSpreadMode} onChange={(event) => setRealizedSpreadMode(event.target.value as RealizedSpreadMode)}>
                      <option value="hold_current_spread">Hold current spread</option>
                      <option value="mean_revert">Mean revert to benchmark</option>
                      <option value="custom_spread">Custom spread</option>
                    </select>
                    <span className="text-muted oil-overlay-help">Controls how company realized pricing differs from benchmark pricing over time.</span>
                  </label>

                  <label className="oil-compact-field">
                    <span className="metric-label">Custom Realized Spread ($/bbl)</span>
                    <input
                      aria-label="Custom realized spread input"
                      type="number"
                      step="0.01"
                      value={customRealizedSpreadInput}
                      onChange={(event) => setCustomRealizedSpreadInput(event.target.value)}
                      disabled={realizedSpreadMode !== "custom_spread"}
                    />
                    <span className="text-muted oil-overlay-help">Positive values imply premium-to-benchmark realization, negative implies discount.</span>
                  </label>
                </>
              ) : (
                <div className="text-muted">
                  {overlay?.requirements?.realized_spread_fallback_label ?? "Benchmark-only fallback"}.{" "}
                  {overlay?.requirements?.realized_spread_reason ?? "Realized spread controls are not available for this profile."}
                </div>
              )}

              <div className="workspace-pill-row">
                <button type="button" className="ticker-button financial-export-button" onClick={() => void handleExportJson()}>
                  Export JSON
                </button>
                <button type="button" className="ticker-button financial-export-button" onClick={() => void handleExportCsv()}>
                  Export CSV
                </button>
              </div>

              {overlayResult.yearlyDeltas.length ? (
                <div className="workspace-card-stack-tight">
                  <div className="metric-label">Detailed Yearly Impact</div>
                  <table>
                    <thead>
                      <tr>
                        <th>Year</th>
                        <th>Benchmark Delta</th>
                        <th>Realized Delta</th>
                        <th>Earnings Delta</th>
                        <th>Per Share</th>
                        <th>PV / Share</th>
                      </tr>
                    </thead>
                    <tbody>
                      {overlayResult.yearlyDeltas.map((item) => (
                        <tr key={item.year}>
                          <td>{item.year}</td>
                          <td>{formatSignedCurrency(item.oilPriceDelta)}</td>
                          <td>{formatSignedCurrency(item.realizedPriceDelta)}</td>
                          <td>{formatSignedCurrency(item.earningsDeltaAfterTax)}</td>
                          <td>{formatSignedCurrency(item.perShareDelta)}</td>
                          <td>{formatSignedCurrency(item.presentValuePerShare)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </div>
          </details>

          <details className="subtle-details">
            <summary>Sources and Confidence</summary>
            <div className="workspace-card-stack-tight">
              <div className="metric-label">Confidence Notes</div>
              {confidenceReasons.length ? (
                <ul className="oil-overlay-reasons">
                  {confidenceReasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              ) : (
                <div className="text-muted">No active confidence penalties are attached to this scenario.</div>
              )}

              {oilEvaluationSummary ? (
                <div className="workspace-card-stack-tight">
                  <div className="metric-label">Latest Oil Overlay Evaluation</div>
                  <div className="workspace-pill-row">
                    <span className="pill">Samples {oilEvaluationSummary.sampleCount ?? "-"}</span>
                    <span className="pill">MAE Lift {formatSignedNumber(oilEvaluationSummary.maeLift)}</span>
                    <span className="pill">Improvement {formatPercent1(oilEvaluationSummary.improvementRate)}</span>
                    <span className="pill">As Of {oilEvaluationSummary.asOf ?? "-"}</span>
                  </div>
                  <div className="text-muted">{oilEvaluationSummary.description}</div>
                </div>
              ) : null}

              <SourceFreshnessSummary
                provenance={overlay?.provenance}
                asOf={overlay?.as_of}
                lastRefreshedAt={overlay?.last_refreshed_at}
                sourceMix={overlay?.source_mix}
                confidenceFlags={overlay?.confidence_flags}
                emptyMessage="Source provenance appears once official oil scenario data has been cached for this company."
              />
              <DataQualityDiagnostics diagnostics={overlay?.diagnostics} emptyMessage="Diagnostics appear once the official oil overlay dataset is populated." />
            </div>
          </details>
        </aside>
      </div>
    </div>
  );
}

function TopSummaryStrip({
  loading,
  baseFairValuePerShare,
  scenarioFairValuePerShare,
  deltaVsBasePerShare,
  impliedUpsideDownside,
  epsDeltaPerDollarOil,
}: {
  loading: boolean;
  baseFairValuePerShare: number | null;
  scenarioFairValuePerShare: number | null;
  deltaVsBasePerShare: number | null;
  impliedUpsideDownside: number | null;
  epsDeltaPerDollarOil: number | null;
}) {
  const cards = [
    { label: "Base Fair Value", value: formatCurrency(baseFairValuePerShare), tone: "neutral" },
    { label: "Scenario Fair Value", value: formatCurrency(scenarioFairValuePerShare), tone: "result" },
    { label: "Delta vs Base", value: formatSignedCurrency(deltaVsBasePerShare), tone: "impact" },
    { label: "Upside / Downside vs Current Price", value: formatPercent1(impliedUpsideDownside), tone: "accent" },
    { label: "EPS Delta per $1 Oil", value: formatSignedNumber(epsDeltaPerDollarOil), tone: "positive" },
  ];

  return (
    <div className="oil-top-summary-grid" aria-label="Oil top summary strip">
      {cards.map((card) => (
        <div key={card.label} className={`filing-link-card oil-top-summary-card tone-${card.tone}`}>
          <div className="metric-label">{card.label}</div>
          <div className="oil-top-summary-value">{loading ? <span className="oil-inline-skeleton" /> : card.value}</div>
        </div>
      ))}
    </div>
  );
}

function BridgeCard({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "neutral" | "impact" | "result" }) {
  return (
    <div className={`oil-bridge-card tone-${tone}`}>
      <div className="metric-label">{label}</div>
      <div className="oil-bridge-value">{value}</div>
    </div>
  );
}

function resolveSupportBanner(status: string): { title: string; copy: string; tone: "positive" | "warning" | "danger" } {
  if (status === "supported") {
    return {
      title: "Supported: direct company evidence is available.",
      copy: "Benchmark and company-level evidence align, so scenario outputs are generally more decision-ready.",
      tone: "positive",
    };
  }
  if (status === "partial") {
    return {
      title: "Partial support: benchmark is official, but some company inputs are estimated or manual.",
      copy: "Treat this as directional analysis. Confidence notes below explain where assumptions, not direct evidence, drive results.",
      tone: "warning",
    };
  }
  return {
    title: "Unsupported: company type is not yet modeled by this overlay.",
    copy: "Use this page for context only. Overlay fair-value outputs are not investment-grade for this profile yet.",
    tone: "danger",
  };
}

function buildCurveDisplayData({
  annualBaseCurve,
  shortTermCurve,
  longTermAnchor,
  fallbackLevel,
}: {
  annualBaseCurve: Array<{ year: number; price: number }>;
  shortTermCurve: Array<{ year: number; price: number }>;
  longTermAnchor: number | null;
  fallbackLevel: number | null;
}): CurveDisplayPoint[] {
  const currentYear = new Date().getUTCFullYear();
  const level = fallbackLevel ?? longTermAnchor ?? 70;
  const seededBase = annualBaseCurve.length
    ? annualBaseCurve
    : [
        { year: currentYear, price: level },
        { year: currentYear + 1, price: level },
        { year: currentYear + 2, price: level },
      ];

  const years = new Set<number>([
    ...seededBase.map((point) => point.year),
    ...shortTermCurve.map((point) => point.year),
  ]);

  if (years.size < 3) {
    const start = Math.min(...Array.from(years));
    years.add(start + 1);
    years.add(start + 2);
  }

  const sortedYears = Array.from(years).sort((left, right) => left - right);
  const lastEditedYear = shortTermCurve.length ? Math.max(...shortTermCurve.map((point) => point.year)) : sortedYears[0] ?? currentYear;
  const lastEditedValue = shortTermCurve.find((point) => point.year === lastEditedYear)?.price ?? interpolateCurve(seededBase, lastEditedYear);
  const anchor = longTermAnchor ?? lastEditedValue;

  return sortedYears.map((year) => {
    const basePrice = interpolateCurve(seededBase, year);
    const scenarioPrice = resolveScenarioPreviewPrice({
      year,
      shortTermCurve,
      baseCurve: seededBase,
      lastEditedYear,
      lastEditedValue,
      anchor,
    });
    return { year, basePrice, scenarioPrice };
  });
}

function resolveScenarioPreviewPrice({
  year,
  shortTermCurve,
  baseCurve,
  lastEditedYear,
  lastEditedValue,
  anchor,
}: {
  year: number;
  shortTermCurve: Array<{ year: number; price: number }>;
  baseCurve: Array<{ year: number; price: number }>;
  lastEditedYear: number;
  lastEditedValue: number;
  anchor: number;
}): number {
  const explicit = shortTermCurve.find((point) => point.year === year);
  if (explicit) {
    return explicit.price;
  }
  if (year <= lastEditedYear) {
    return interpolateCurve(baseCurve, year);
  }
  const yearsAfterEdit = year - lastEditedYear;
  const fadeYears = 3;
  const progress = Math.min(1, yearsAfterEdit / fadeYears);
  return lastEditedValue + (anchor - lastEditedValue) * progress;
}

function buildPresetCurve(
  preset: Exclude<ScenarioPresetId, "custom">,
  annualBaseCurve: Array<{ year: number; price: number }>,
  defaultShortTermCurve: Array<{ year: number; price: number }>,
  currentAnchor: number | null,
): { points: Array<{ year: number; price: number }>; anchor: number | null } {
  const source = defaultShortTermCurve.length
    ? defaultShortTermCurve
    : annualBaseCurve.slice(0, Math.min(3, annualBaseCurve.length));
  if (!source.length) {
    return { points: [], anchor: currentAnchor };
  }

  const first = source[0]?.price ?? 70;
  const baseAnchor = currentAnchor ?? source[source.length - 1]?.price ?? first;

  if (preset === "official_base") {
    return { points: source.map((point) => ({ ...point })), anchor: baseAnchor };
  }
  if (preset === "bull") {
    return {
      points: source.map((point, index) => ({
        ...point,
        price: roundTo(point.price * (1 + 0.05 + index * 0.01), 1),
      })),
      anchor: roundTo(baseAnchor * 1.08, 1),
    };
  }
  if (preset === "bear") {
    return {
      points: source.map((point, index) => ({
        ...point,
        price: roundTo(point.price * (1 - 0.05 - index * 0.01), 1),
      })),
      anchor: roundTo(baseAnchor * 0.9, 1),
    };
  }
  if (preset === "flat") {
    return {
      points: source.map((point) => ({ ...point, price: roundTo(first, 1) })),
      anchor: roundTo(first, 1),
    };
  }
  return {
    points: source.map((point, index) => ({
      ...point,
      price: roundTo(point.price * (1 - 0.08 - Math.min(index, 2) * 0.03), 1),
    })),
    anchor: roundTo(baseAnchor * 0.82, 1),
  };
}

function resolveDefaultBenchmarkId(
  benchmarkOptions: Array<{ value: string; label: string }>,
  explicitDefault: string | null | undefined,
  spreadReferenceBenchmark: string | null | undefined,
): string {
  if (explicitDefault && benchmarkOptions.some((option) => option.value === explicitDefault)) {
    return explicitDefault;
  }
  const reference = spreadReferenceBenchmark?.toLowerCase();
  if (reference) {
    const byReference = benchmarkOptions.find((option) => option.value.toLowerCase().includes(reference) || option.label.toLowerCase().includes(reference));
    if (byReference) {
      return byReference.value;
    }
  }
  const preferredWti = benchmarkOptions.find((option) => option.value.toLowerCase().includes("wti") || option.label.toLowerCase().includes("wti"));
  if (preferredWti) {
    return preferredWti.value;
  }
  return benchmarkOptions[0]?.value ?? "";
}

function buildWhatChangedRows({
  annualBaseCurve,
  shortTermCurve,
  longTermAnchor,
  sensitivitySource,
  activeSensitivity,
  realizedSpreadMode,
}: {
  annualBaseCurve: Array<{ year: number; price: number }>;
  shortTermCurve: Array<{ year: number; price: number }>;
  longTermAnchor: number | null;
  sensitivitySource: SensitivitySource;
  activeSensitivity: number | null;
  realizedSpreadMode: RealizedSpreadMode;
}): string[] {
  const baseAvg = mean(annualBaseCurve.map((point) => point.price));
  const scenarioAvg = mean(shortTermCurve.map((point) => point.price));
  const rows = [
    `Scenario oil path averages ${formatSignedCurrencyShort((scenarioAvg ?? 0) - (baseAvg ?? 0))} versus the official benchmark across edited years.`,
    `Long-term oil anchor is ${formatDollarPerBarrel(longTermAnchor)} per barrel.`,
    `Sensitivity uses ${sensitivitySource === "dataset" ? "dataset-derived" : "manual"} input${activeSensitivity == null ? " (currently missing)" : ` at ${formatSignedNumber(activeSensitivity)}`}.`,
    `Realized-pricing assumption uses ${humanizeFlag(realizedSpreadMode)} behavior.`,
  ];
  return rows;
}

function buildOverlayBlockedReasons(overlay: CompanyOilScenarioResponse | null): string[] {
  if (!overlay) {
    return ["Official oil overlay data has not been cached for this company yet."];
  }
  const reasons: string[] = [];
  const availableSeries = (overlay.benchmark_series ?? []).filter((series) => series.status === "ok");
  if (!availableSeries.length) {
    reasons.push("Official EIA benchmark curves are not cached yet for the selected oil benchmark.");
  }
  if (overlay.requirements?.manual_sensitivity_required) {
    reasons.push(overlay.requirements.manual_sensitivity_reason ?? "An annual after-tax oil sensitivity is still required.");
  }
  if (overlay.exposure_profile.oil_support_status === "partial") {
    reasons.push(...(overlay.exposure_profile.oil_support_reasons ?? []).map(describeOilSupportReason));
  }
  if (overlay.requirements?.realized_spread_supported === false && overlay.requirements.realized_spread_reason) {
    reasons.push(overlay.requirements.realized_spread_reason);
  }
  return Array.from(new Set(reasons.filter(Boolean)));
}

function interpolateCurve(points: Array<{ year: number; price: number }>, year: number): number {
  if (!points.length) {
    return 0;
  }
  const sorted = points.slice().sort((left, right) => left.year - right.year);
  const direct = sorted.find((point) => point.year === year);
  if (direct) {
    return direct.price;
  }
  if (year <= sorted[0].year) {
    return sorted[0].price;
  }
  if (year >= sorted[sorted.length - 1].year) {
    return sorted[sorted.length - 1].price;
  }

  let previous = sorted[0];
  let next = sorted[sorted.length - 1];
  for (const candidate of sorted) {
    if (candidate.year < year) {
      previous = candidate;
      continue;
    }
    next = candidate;
    break;
  }

  const progress = (year - previous.year) / (next.year - previous.year);
  return previous.price + (next.price - previous.price) * progress;
}

function mean(values: number[]): number | null {
  if (!values.length) {
    return null;
  }
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function parseNumber(value: string): number | null {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function roundTo(value: number, decimals: number): number {
  const scale = 10 ** decimals;
  return Math.round(value * scale) / scale;
}

function formatNumberInput(value: number, decimals: number): string {
  return roundTo(value, decimals).toFixed(decimals);
}

function formatCurrency(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  }).format(value);
}

function formatSignedCurrency(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
    signDisplay: "exceptZero",
  }).format(value);
}

function formatSignedCurrencyShort(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 1,
    minimumFractionDigits: 1,
    signDisplay: "exceptZero",
  }).format(value);
}

function formatDollarPerBarrel(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  return `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 1, minimumFractionDigits: 1 }).format(value)}`;
}

function formatSignedNumber(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
    signDisplay: "exceptZero",
  }).format(value);
}

function formatPercent1(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  return new Intl.NumberFormat("en-US", {
    style: "percent",
    maximumFractionDigits: 1,
    minimumFractionDigits: 1,
    signDisplay: "exceptZero",
  }).format(value);
}

function formatCompact(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 }).format(value);
}
