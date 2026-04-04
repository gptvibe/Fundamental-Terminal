"use client";

import { useEffect, useMemo, useState } from "react";

import { DataQualityDiagnostics } from "@/components/ui/data-quality-diagnostics";
import { SourceFreshnessSummary } from "@/components/ui/source-freshness-summary";
import { showAppToast } from "@/lib/app-toast";
import { downloadJsonFile, exportRowsToCsv, normalizeExportFileStem } from "@/lib/export";
import { formatPercent, titleCase } from "@/lib/format";
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
    () => (overlay?.user_editable_defaults?.benchmark_options?.length ? overlay.user_editable_defaults.benchmark_options : resolveBenchmarkOptions(overlay?.benchmark_series ?? [])),
    [overlay?.benchmark_series, overlay?.user_editable_defaults?.benchmark_options],
  );
  const defaultBenchmarkId = overlay?.user_editable_defaults?.benchmark_id ?? benchmarkOptions[0]?.value ?? "";
  const [benchmarkId, setBenchmarkId] = useState(defaultBenchmarkId);
  const selectedBenchmark = useMemo(
    () => (overlay?.benchmark_series ?? []).find((series) => series.series_id === benchmarkId) ?? null,
    [benchmarkId, overlay?.benchmark_series],
  );
  const annualBaseCurve = useMemo(() => annualizeOilCurveSeries(selectedBenchmark), [selectedBenchmark]);
  const activeAnnualBaseCurve = annualBaseCurve;
  const defaultShortTermCurve = useMemo(() => buildDefaultShortTermCurve(activeAnnualBaseCurve), [activeAnnualBaseCurve]);
  const defaultLongTermAnchor = useMemo(() => resolveDefaultLongTermAnchor(activeAnnualBaseCurve), [activeAnnualBaseCurve]);
  const latestPrice = priceHistory.at(-1)?.close ?? null;
  const supportStatus = overlay?.exposure_profile.oil_support_status === "supported" || overlay?.exposure_profile.oil_support_status === "partial"
    ? overlay.exposure_profile.oil_support_status
    : companySupportStatus;
  const supportReasons = overlay?.exposure_profile.oil_support_reasons?.length ? overlay.exposure_profile.oil_support_reasons : companySupportReasons;
  const datasetSensitivity = useMemo(() => resolveDatasetAnnualSensitivity(overlay?.sensitivity), [overlay?.sensitivity]);
  const directEvidence = overlay?.direct_company_evidence ?? null;
  const defaultSensitivitySource = useMemo<SensitivitySource>(
    () => (datasetSensitivity == null ? "manual" : "dataset"),
    [datasetSensitivity],
  );
  const realizedSpreadSupported = Boolean(overlay?.requirements?.realized_spread_supported);
  const defaultRealizedSpreadMode = useMemo<RealizedSpreadMode>(
    () => ((overlay?.user_editable_defaults?.realized_spread_mode as RealizedSpreadMode | undefined) ?? "benchmark_only"),
    [overlay?.user_editable_defaults?.realized_spread_mode],
  );
  const defaultCustomRealizedSpread = overlay?.user_editable_defaults?.custom_realized_spread;
  const defaultMeanReversionYears = overlay?.user_editable_defaults?.mean_reversion_years ?? 3;
  const defaultDownstreamOffsetPercent = overlay?.phase2_extensions?.downstream_offset_percent ?? 0;
  const hasOfficialCurve = activeAnnualBaseCurve.length > 0;
  const blockedReasons = useMemo(() => buildOverlayBlockedReasons(overlay), [overlay]);
  const availabilityCards = useMemo(() => buildAvailabilityCards(overlay, hasOfficialCurve, datasetSensitivity, dilutedShares), [overlay, hasOfficialCurve, datasetSensitivity, dilutedShares]);
  const oilEvaluationSummary = useMemo(() => resolveOilOverlayEvaluationSummary(ticker, oilOverlayEvaluation), [ticker, oilOverlayEvaluation]);

  const [shortTermCurve, setShortTermCurve] = useState(defaultShortTermCurve);
  const [longTermAnchorInput, setLongTermAnchorInput] = useState(defaultLongTermAnchor == null ? "" : String(defaultLongTermAnchor));
  const [fadeYearsInput, setFadeYearsInput] = useState("2");
  const [sensitivitySource, setSensitivitySource] = useState<SensitivitySource>(defaultSensitivitySource);
  const [manualSensitivityInput, setManualSensitivityInput] = useState("");
  const [currentSharePriceInput, setCurrentSharePriceInput] = useState(latestPrice == null ? "" : String(latestPrice));
  const [realizedSpreadMode, setRealizedSpreadMode] = useState<RealizedSpreadMode>(defaultRealizedSpreadMode);
  const [customRealizedSpreadInput, setCustomRealizedSpreadInput] = useState(defaultCustomRealizedSpread == null ? "" : String(defaultCustomRealizedSpread));
  const [downstreamOffsetInput, setDownstreamOffsetInput] = useState(String(defaultDownstreamOffsetPercent));

  useEffect(() => {
    setBenchmarkId(defaultBenchmarkId);
  }, [defaultBenchmarkId]);

  useEffect(() => {
    setShortTermCurve(defaultShortTermCurve);
    setLongTermAnchorInput(defaultLongTermAnchor == null ? "" : String(defaultLongTermAnchor));
  }, [defaultLongTermAnchor, defaultShortTermCurve, benchmarkId]);

  useEffect(() => {
    setCurrentSharePriceInput(latestPrice == null ? "" : String(latestPrice));
  }, [latestPrice, strictOfficialMode]);

  useEffect(() => {
    setSensitivitySource(defaultSensitivitySource);
  }, [defaultSensitivitySource]);

  useEffect(() => {
    setRealizedSpreadMode(defaultRealizedSpreadMode);
    setCustomRealizedSpreadInput(defaultCustomRealizedSpread == null ? "" : String(defaultCustomRealizedSpread));
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
        officialBaseCurve: activeAnnualBaseCurve,
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
    [activeAnnualBaseCurve, activeSensitivity, baseFairValuePerShare, currentSharePrice, customRealizedSpread, defaultMeanReversionYears, dilutedShares, downstreamOffsetPercent, fadeYears, longTermAnchor, overlay?.confidence_flags, overlay?.sensitivity?.confidence_flags, overlay?.sensitivity_source?.kind, overlay?.user_editable_defaults?.current_realized_spread, overlay?.user_editable_defaults?.mean_reversion_target_spread, overlay?.user_editable_defaults?.realized_spread_reference_benchmark, realizedSpreadMode, realizedSpreadSupported, sensitivitySource, shortTermCurve, supportStatus],
  );
  const confidenceReasons = useMemo(
    () => Array.from(new Set([...supportReasons.map(describeOilSupportReason), ...(overlay?.confidence_flags ?? []).map(humanizeFlag), ...overlayResult.confidenceFlags.map(humanizeFlag)])).filter(Boolean),
    [overlay?.confidence_flags, overlayResult.confidenceFlags, supportReasons],
  );

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

  if (!overlay && !benchmarkOptions.length) {
    return <div className="text-muted">Official oil overlay data is not available yet for this company.</div>;
  }

  return (
    <div className="workspace-card-stack workspace-card-stack-lg">
      <div className="valuation-card-header">
        <div>
          <div className="valuation-card-kicker">Fair-Value Overlay</div>
          <div className="valuation-card-title">Oil Scenario Overlay</div>
        </div>
        <div className="valuation-card-subtitle">
          Reprices the current base fair value with an official benchmark curve, user-edited short-term path, user long-term anchor, and discounted after-tax sensitivity assumptions.
        </div>
      </div>

      <div className="filing-link-card workspace-card-stack-tight">
        <div className="metric-label">v1 Scope</div>
        <div>
          v1 models realized-vs-benchmark economics for producers and integrated upstream names. It does not claim to know the exact company purchase price of oil.
        </div>
      </div>

      {oilEvaluationSummary ? (
        <div className="filing-link-card workspace-card-stack-tight">
          <div className="metric-label">Latest Oil Overlay Evaluation</div>
          <div className="workspace-pill-row">
            <span className="pill">Samples {oilEvaluationSummary.sampleCount ?? "—"}</span>
            <span className="pill">MAE Lift {formatSignedNumber(oilEvaluationSummary.maeLift)}</span>
            <span className="pill">Improvement Rate {formatPercent(oilEvaluationSummary.improvementRate)}</span>
            <span className="pill">As Of {oilEvaluationSummary.asOf ?? "—"}</span>
          </div>
          <div className="text-muted">
            {oilEvaluationSummary.description}
          </div>
          <SourceFreshnessSummary
            provenance={oilOverlayEvaluation?.provenance}
            asOf={oilOverlayEvaluation?.as_of}
            lastRefreshedAt={oilOverlayEvaluation?.last_refreshed_at}
            sourceMix={oilOverlayEvaluation?.source_mix}
            confidenceFlags={oilOverlayEvaluation?.confidence_flags}
            emptyMessage="No persisted oil overlay evaluation summary is available yet."
          />
        </div>
      ) : null}

      <div className="oil-overlay-summary-grid">
        {availabilityCards.map((card) => (
          <SummaryCard key={card.label} label={card.label} value={card.value} tone={card.tone} />
        ))}
      </div>

      <div className="filing-link-card workspace-card-stack-tight">
        <div className="metric-label">Input Availability</div>
        {blockedReasons.length ? (
          <ul className="oil-overlay-reasons">
            {blockedReasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        ) : (
          <div className="text-muted">The required overlay inputs are available for interactive modeling.</div>
        )}
      </div>

      <div className="filing-link-card workspace-card-stack-tight">
        <div className="metric-label">Direct Company Evidence</div>
        <div className="workspace-pill-row">
          <span className="pill">Disclosed Sensitivity {formatEvidenceStatus(directEvidence?.disclosed_sensitivity?.status)}</span>
          <span className="pill">Diluted Shares {formatEvidenceStatus(directEvidence?.diluted_shares?.status)}</span>
          <span className="pill">Realized Spread {formatEvidenceStatus(directEvidence?.realized_price_comparison?.status)}</span>
        </div>
        <div className="text-muted">
          {directEvidence?.disclosed_sensitivity?.status === "available"
            ? `${String(directEvidence.disclosed_sensitivity.benchmark ?? "benchmark").toUpperCase()} sensitivity is disclosed directly in SEC filings.`
            : directEvidence?.disclosed_sensitivity?.reason ?? "No disclosed oil sensitivity is cached yet."}
        </div>
        {directEvidence?.realized_price_comparison?.rows?.length ? (
          <table>
            <thead>
              <tr>
                <th>Period</th>
                <th>Realized Price</th>
                <th>Benchmark Price</th>
                <th>% of Benchmark</th>
                <th>Spread</th>
              </tr>
            </thead>
            <tbody>
              {directEvidence.realized_price_comparison.rows.slice(0, 3).map((row) => (
                <tr key={row.period_label}>
                  <td>{row.period_label}</td>
                  <td>{formatCurrency(row.realized_price)}</td>
                  <td>{formatCurrency(row.benchmark_price)}</td>
                  <td>{formatPercent(row.realized_percent_of_benchmark != null ? row.realized_percent_of_benchmark / 100 : null)}</td>
                  <td>{formatSignedCurrency(row.premium_discount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="text-muted">{directEvidence?.realized_price_comparison?.reason ?? "No realized-price-versus-benchmark table is cached yet."}</div>
        )}
      </div>

      <div className="filing-link-card workspace-card-stack-tight">
        <div className="metric-label">Phase 2 Extensions</div>
        <div className="workspace-pill-row">
          <span className="pill">Downstream Offset {overlay?.phase2_extensions?.downstream_offset_supported ? "Active" : "N/A"}</span>
          <span className="pill">Refiner RAC {overlay?.phase2_extensions?.refiner_rac_supported ? "Ready" : "Pending"}</span>
          <span className="pill">AEO Presets {overlay?.phase2_extensions?.aeo_presets_supported ? "Ready" : "Pending"}</span>
        </div>
        <div className="text-muted">
          {overlay?.phase2_extensions?.downstream_offset_supported
            ? "Integrated names can reduce upstream-only sensitivity with a downstream offset. Refiner RAC inputs and official AEO preset decks stay pending until those EIA feeds are wired."
            : overlay?.phase2_extensions?.downstream_offset_reason ?? "Phase-2 controls are only shown when the company profile supports them."}
        </div>
        {(overlay?.phase2_extensions?.aeo_preset_options?.length ?? 0) > 0 ? (
          <div className="workspace-pill-row">
            {overlay?.phase2_extensions?.aeo_preset_options?.map((option) => (
              <span key={option.preset_id} className="pill">{option.label} {titleCase(option.status.replaceAll("_", " "))}</span>
            ))}
          </div>
        ) : null}
      </div>

      {hasOfficialCurve ? (
        <div className="filing-link-card workspace-card-stack-tight">
          <div className="metric-label">Benchmark Curve View</div>
          <BenchmarkCurveChart baseCurve={activeAnnualBaseCurve} scenarioCurve={shortTermCurve} />
        </div>
      ) : (
        <div className="filing-link-card workspace-card-stack-tight">
          <div className="metric-label">Benchmark Curve View</div>
          <div className="text-muted">No official annual benchmark curve is cached yet, so the interactive overlay stays blocked until EIA inputs are available.</div>
        </div>
      )}

      <div className="workspace-pill-row">
        <span className="pill">Support {titleCase(supportStatus)}</span>
        <span className="pill">Base Fair Value {formatCurrency(baseFairValuePerShare)}</span>
        <span className="pill">Diluted Shares {formatCompact(dilutedShares)}</span>
        {overlay?.phase2_extensions?.downstream_offset_supported ? <span className="pill">Downstream Offset {formatPercent(downstreamOffsetPercent / 100)}</span> : null}
        <button type="button" className="ticker-button financial-export-button" onClick={() => void handleExportJson()}>
          Export JSON
        </button>
        <button type="button" className="ticker-button financial-export-button" onClick={() => void handleExportCsv()}>
          Export CSV
        </button>
      </div>

      {hasOfficialCurve ? (
      <div className="oil-overlay-controls">
        {benchmarkOptions.length ? (
          <label className="oil-overlay-field">
            <span className="metric-label">Benchmark Selector</span>
            <select aria-label="Benchmark Selector" value={benchmarkId} onChange={(event) => setBenchmarkId(event.target.value)}>
              {benchmarkOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
        ) : (
          <div className="oil-overlay-field">
            <span className="metric-label">Benchmark Selector</span>
            <div className="text-muted oil-overlay-help">No official benchmark curve is cached yet for this company.</div>
          </div>
        )}

        <label className="oil-overlay-field">
          <span className="metric-label">Long-Term Anchor</span>
          <input aria-label="Long-term anchor input" type="number" step="0.01" value={longTermAnchorInput} onChange={(event) => setLongTermAnchorInput(event.target.value)} />
        </label>

        <label className="oil-overlay-field">
          <span className="metric-label">Fade Years</span>
          <input aria-label="Fade years input" type="number" min="0" step="1" value={fadeYearsInput} onChange={(event) => setFadeYearsInput(event.target.value)} />
        </label>

        <label className="oil-overlay-field">
          <span className="metric-label">Sensitivity Source</span>
          <select value={sensitivitySource} onChange={(event) => setSensitivitySource(event.target.value as SensitivitySource)}>
            <option value="manual">Manual override</option>
            <option value="dataset" disabled={datasetSensitivity == null}>
              {overlay?.sensitivity_source?.kind === "disclosed" ? "SEC disclosed sensitivity" : "Derived official estimate"}
              {datasetSensitivity == null ? " (unavailable)" : ""}
            </option>
          </select>
        </label>

        <label className="oil-overlay-field">
          <span className="metric-label">Annual After-Tax Sensitivity</span>
          <input
            aria-label="Annual after-tax sensitivity input"
            type="number"
            step="0.01"
            value={sensitivitySource === "manual" ? manualSensitivityInput : datasetSensitivity == null ? "" : String(datasetSensitivity)}
            onChange={(event) => setManualSensitivityInput(event.target.value)}
            disabled={sensitivitySource !== "manual"}
          />
        </label>

        <label className="oil-overlay-field">
          <span className="metric-label">Current Share Price</span>
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
              ? "Strict official mode requires manual price entry when no official closing-price feed is configured."
              : "Defaults to the latest cached share price when market data is available."}
          </span>
        </label>

        {overlay?.phase2_extensions?.downstream_offset_supported ? (
          <label className="oil-overlay-field">
            <span className="metric-label">Downstream Offset</span>
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
            <span className="text-muted oil-overlay-help">
              {sensitivitySource === "dataset" && overlay?.sensitivity_source?.kind === "disclosed"
                ? "SEC disclosed company-level sensitivity already captures net economics, so the downstream offset stays disabled in disclosed mode."
                : "Reduces upstream-only oil sensitivity for integrated majors by the selected percent to reflect downstream offsets."}
            </span>
          </label>
        ) : null}

        {realizedSpreadSupported ? (
          <>
            <label className="oil-overlay-field">
              <span className="metric-label">Realized Spread Mode</span>
              <select aria-label="Realized spread mode" value={realizedSpreadMode} onChange={(event) => setRealizedSpreadMode(event.target.value as RealizedSpreadMode)}>
                <option value="hold_current_spread">Hold current spread</option>
                <option value="mean_revert">Mean revert to benchmark</option>
                <option value="custom_spread">Custom spread</option>
              </select>
              <span className="text-muted oil-overlay-help">
                Current SEC-derived spread: {formatSignedCurrency(overlay?.user_editable_defaults?.current_realized_spread)} versus {String(overlay?.user_editable_defaults?.realized_spread_reference_benchmark ?? overlay?.direct_company_evidence?.realized_price_comparison?.benchmark ?? "benchmark").toUpperCase()}. Mean reversion fades that spread to $0.00 over {defaultMeanReversionYears} years.
              </span>
            </label>

            <label className="oil-overlay-field">
              <span className="metric-label">Custom Realized Spread</span>
              <input
                aria-label="Custom realized spread input"
                type="number"
                step="0.01"
                value={customRealizedSpreadInput}
                onChange={(event) => setCustomRealizedSpreadInput(event.target.value)}
                disabled={realizedSpreadMode !== "custom_spread"}
              />
            </label>
          </>
        ) : (
          <div className="oil-overlay-field">
            <span className="metric-label">Realized Spread Controls</span>
            <div>{overlay?.requirements?.realized_spread_fallback_label ?? "Benchmark-only fallback"}</div>
            <div className="text-muted oil-overlay-help">
              {overlay?.requirements?.realized_spread_reason ?? "No SEC realized-price-versus-benchmark spread is cached yet, so the overlay stays benchmark-only."}
            </div>
          </div>
        )}
      </div>
      ) : null}

      {hasOfficialCurve && overlay?.sensitivity_source?.kind === "disclosed" ? (
        <div className="text-muted oil-overlay-help">
          SEC disclosed sensitivity is benchmark-linked. Realized-spread controls remain visible for context, but benchmark-linked earnings deltas stay anchored to the disclosed benchmark sensitivity unless you switch to manual override.
        </div>
      ) : null}

      {hasOfficialCurve ? (
      <div className="workspace-card-stack-tight">
        <div className="metric-label">Short-Term Curve Editor</div>
        {shortTermCurve.length ? (
          <div className="workspace-card-stack-tight">
            {shortTermCurve.map((point, index) => (
              <div key={point.year} className="oil-overlay-curve-row">
                <div className="pill">{point.year}</div>
                <input
                  aria-label={`Short-term curve ${point.year}`}
                  type="number"
                  step="0.01"
                  value={String(point.price)}
                  onChange={(event) => {
                    const nextValue = Number.parseFloat(event.target.value);
                    setShortTermCurve((current) => current.map((item, currentIndex) => (currentIndex === index && Number.isFinite(nextValue) ? { ...item, price: nextValue } : item)));
                  }}
                />
                <span className="text-muted">Official base {formatCurrency(activeAnnualBaseCurve[index]?.price ?? point.price)}</span>
              </div>
            ))}
            <div>
              <button type="button" className="ticker-button" onClick={() => setShortTermCurve(defaultShortTermCurve)}>
                Reset to official curve
              </button>
            </div>
          </div>
        ) : (
          <div className="text-muted">No official annual benchmark points are available for the selected benchmark yet.</div>
        )}
      </div>
      ) : null}

      {hasOfficialCurve ? (
      <div className="oil-overlay-summary-grid">
        <SummaryCard label="Scenario Fair Value / Share" value={formatCurrency(overlayResult.scenarioFairValuePerShare)} tone="accent" />
        <SummaryCard label="Delta vs Base" value={formatSignedCurrency(overlayResult.deltaVsBasePerShare)} tone="warning" />
        <SummaryCard label="EPS Delta per $1 Oil" value={formatSignedNumber(overlayResult.epsDeltaPerDollarOil)} tone="positive" />
        <SummaryCard label="Upside / Downside" value={formatPercent(overlayResult.impliedUpsideDownside)} tone="cyan" />
      </div>
      ) : null}

      <div className="filing-link-card workspace-card-stack-tight">
        <div className="metric-label">Overlay Status</div>
        <div>{titleCase(overlayResult.modelStatus)}</div>
        <div className="text-muted">{overlayResult.reason}</div>
      </div>

      <div className="filing-link-card workspace-card-stack-tight">
        <div className="metric-label">Confidence Reasons</div>
        {confidenceReasons.length ? (
          <ul className="oil-overlay-reasons">
            {confidenceReasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        ) : (
          <div className="text-muted">No confidence penalties are currently attached to this overlay.</div>
        )}
      </div>

      {hasOfficialCurve && overlayResult.yearlyDeltas.length ? (
        <div className="filing-link-card workspace-card-stack-tight">
          <div className="metric-label">Per-Year Deltas</div>
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

      <div className="oil-overlay-footer-grid">
        <div className="filing-link-card workspace-card-stack-tight">
          <div className="metric-label">Provenance</div>
          <SourceFreshnessSummary
            provenance={overlay?.provenance}
            asOf={overlay?.as_of}
            lastRefreshedAt={overlay?.last_refreshed_at}
            sourceMix={overlay?.source_mix}
            confidenceFlags={overlay?.confidence_flags}
            emptyMessage="Oil overlay provenance will appear after the official dataset is available."
          />
        </div>
        <div className="filing-link-card workspace-card-stack-tight">
          <div className="metric-label">Diagnostics</div>
          <DataQualityDiagnostics diagnostics={overlay?.diagnostics} emptyMessage="Diagnostics will appear after the official oil overlay dataset is populated." />
        </div>
      </div>
    </div>
  );
}

function SummaryCard({ label, value, tone }: { label: string; value: string; tone: "accent" | "warning" | "positive" | "cyan" }) {
  return (
    <div className="filing-link-card oil-overlay-summary-card">
      <div className="metric-label">{label}</div>
      <div className={`oil-overlay-summary-value tone-${tone}`}>{value}</div>
    </div>
  );
}

function parseNumber(value: string): number | null {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatCurrency(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(value);
}

function formatSignedCurrency(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2, signDisplay: "exceptZero" }).format(value);
}

function formatSignedNumber(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2, signDisplay: "exceptZero" }).format(value);
}

function formatCompact(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 }).format(value);
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

function buildAvailabilityCards(
  overlay: CompanyOilScenarioResponse | null,
  hasOfficialCurve: boolean,
  datasetSensitivity: number | null,
  dilutedShares: number | null,
): Array<{ label: string; value: string; tone: "accent" | "warning" | "positive" | "cyan" }> {
  return [
    {
      label: "Support Status",
      value: overlay ? titleCase(overlay.exposure_profile.oil_support_status) : "Unavailable",
      tone: overlay?.exposure_profile.oil_support_status === "supported" ? "positive" : "warning",
    },
    {
      label: "Official Curve",
      value: hasOfficialCurve ? "Ready" : "Blocked",
      tone: hasOfficialCurve ? "positive" : "warning",
    },
    {
      label: "Sensitivity Input",
      value: datasetSensitivity != null ? formatSignedNumber(datasetSensitivity) : overlay?.requirements?.manual_sensitivity_required ? "Manual Required" : "Pending",
      tone: datasetSensitivity != null ? "accent" : "warning",
    },
    {
      label: "Diluted Shares",
      value: formatCompact(dilutedShares),
      tone: dilutedShares != null ? "cyan" : "warning",
    },
  ];
}

function BenchmarkCurveChart({
  baseCurve,
  scenarioCurve,
}: {
  baseCurve: Array<{ year: number; price: number }>;
  scenarioCurve: Array<{ year: number; price: number }>;
}) {
  if (!baseCurve.length) {
    return <div className="text-muted">No benchmark curve points are available yet.</div>;
  }

  const width = 680;
  const height = 220;
  const padding = 24;
  const points = [...baseCurve, ...scenarioCurve].map((point) => point.price);
  const minPrice = Math.min(...points);
  const maxPrice = Math.max(...points);
  const span = Math.max(maxPrice - minPrice, 1);
  const xForIndex = (index: number, count: number) => padding + (index * (width - padding * 2)) / Math.max(count - 1, 1);
  const yForPrice = (price: number) => height - padding - ((price - minPrice) / span) * (height - padding * 2);
  const linePath = (curve: Array<{ year: number; price: number }>) => curve.map((point, index) => `${index === 0 ? "M" : "L"} ${xForIndex(index, curve.length)} ${yForPrice(point.price)}`).join(" ");

  return (
    <div className="workspace-card-stack-tight">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Benchmark curve chart" width="100%" height={height}>
        <rect x="0" y="0" width={width} height={height} fill="rgba(148, 163, 184, 0.08)" rx="16" />
        {[0, 1, 2, 3].map((step) => {
          const y = padding + ((height - padding * 2) * step) / 3;
          return <line key={step} x1={padding} y1={y} x2={width - padding} y2={y} stroke="rgba(148, 163, 184, 0.18)" strokeWidth="1" />;
        })}
        <path d={linePath(baseCurve)} fill="none" stroke="#38bdf8" strokeWidth="3" />
        <path d={linePath(scenarioCurve)} fill="none" stroke="#f59e0b" strokeWidth="3" strokeDasharray="8 6" />
        {baseCurve.map((point, index) => (
          <g key={`base-${point.year}`}>
            <circle cx={xForIndex(index, baseCurve.length)} cy={yForPrice(point.price)} r="4" fill="#38bdf8" />
            <text x={xForIndex(index, baseCurve.length)} y={height - 6} textAnchor="middle" fontSize="11" fill="currentColor">
              {point.year}
            </text>
          </g>
        ))}
      </svg>
      <div className="workspace-pill-row">
        <span className="pill">Blue: Official annual benchmark</span>
        <span className="pill">Amber: Your scenario path</span>
      </div>
    </div>
  );
}

function formatEvidenceStatus(status: string | null | undefined): string {
  if (!status) {
    return "Unavailable";
  }
  return humanizeFlag(status).replace(/\b\w/g, (match) => match.toUpperCase());
}

