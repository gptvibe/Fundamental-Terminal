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
import type {
  CompanyOilScenarioOverlayResponse,
  FinancialPayload,
  ModelPayload,
  PriceHistoryPoint,
} from "@/lib/types";

interface OilScenarioOverlayPanelProps {
  ticker: string;
  overlay: CompanyOilScenarioOverlayResponse | null;
  models: ModelPayload[];
  financials: FinancialPayload[];
  priceHistory: PriceHistoryPoint[];
  strictOfficialMode: boolean;
  companySupportStatus: "supported" | "partial" | "unsupported";
  companySupportReasons: string[];
}

type SensitivitySource = "manual" | "dataset";

const EXAMPLE_BENCHMARK_ID = "__example_current_oil__";
const EXAMPLE_BASELINE_OIL_PRICE = 80;
const EXAMPLE_CURVE_YEARS = 3;

export function OilScenarioOverlayPanel({
  ticker,
  overlay,
  models,
  financials,
  priceHistory,
  strictOfficialMode,
  companySupportStatus,
  companySupportReasons,
}: OilScenarioOverlayPanelProps) {
  const baseFairValuePerShare = useMemo(() => resolveBaseFairValuePerShare(models), [models]);
  const dilutedShares = useMemo(() => resolveDilutedShares(financials), [financials]);
  const benchmarkOptions = useMemo(() => resolveBenchmarkOptions(overlay?.benchmark_series ?? []), [overlay?.benchmark_series]);
  const usingExampleBenchmark = benchmarkOptions.length === 0;
  const exampleBaseOilPrice = useMemo(() => resolveExampleBaseOilPrice(overlay?.benchmark_series ?? []), [overlay?.benchmark_series]);
  const exampleStartYear = useMemo(() => resolveExampleStartYear(overlay?.as_of), [overlay?.as_of]);
  const displayBenchmarkOptions = useMemo(
    () =>
      benchmarkOptions.length
        ? benchmarkOptions
        : [{ value: EXAMPLE_BENCHMARK_ID, label: `Example benchmark (${formatCurrency(exampleBaseOilPrice)}/bbl baseline)` }],
    [benchmarkOptions, exampleBaseOilPrice],
  );
  const defaultBenchmarkId = displayBenchmarkOptions.find((option) => option.value.toLowerCase().includes("wti"))?.value ?? displayBenchmarkOptions[0]?.value ?? "";
  const [benchmarkId, setBenchmarkId] = useState(defaultBenchmarkId);
  const selectedBenchmark = useMemo(
    () => (overlay?.benchmark_series ?? []).find((series) => series.series_id === benchmarkId) ?? null,
    [benchmarkId, overlay?.benchmark_series],
  );
  const annualBaseCurve = useMemo(() => annualizeOilCurveSeries(selectedBenchmark), [selectedBenchmark]);
  const exampleBaselineCurve = useMemo(
    () => buildExampleBaselineCurve(exampleStartYear, exampleBaseOilPrice),
    [exampleBaseOilPrice, exampleStartYear],
  );
  const examplePlusFiveCurve = useMemo(
    () => buildExampleScenarioCurve(exampleStartYear, exampleBaseOilPrice, 0.05),
    [exampleBaseOilPrice, exampleStartYear],
  );
  const activeAnnualBaseCurve = useMemo(() => {
    if (annualBaseCurve.length) {
      return annualBaseCurve;
    }
    if (usingExampleBenchmark && benchmarkId === EXAMPLE_BENCHMARK_ID) {
      return exampleBaselineCurve;
    }
    return [];
  }, [annualBaseCurve, benchmarkId, exampleBaselineCurve, usingExampleBenchmark]);
  const defaultShortTermCurve = useMemo(() => buildDefaultShortTermCurve(activeAnnualBaseCurve), [activeAnnualBaseCurve]);
  const defaultLongTermAnchor = useMemo(() => resolveDefaultLongTermAnchor(activeAnnualBaseCurve), [activeAnnualBaseCurve]);
  const latestPrice = priceHistory.at(-1)?.close ?? null;
  const supportStatus = overlay?.exposure_profile.oil_support_status === "supported" || overlay?.exposure_profile.oil_support_status === "partial"
    ? overlay.exposure_profile.oil_support_status
    : companySupportStatus;
  const supportReasons = overlay?.exposure_profile.oil_support_reasons?.length ? overlay.exposure_profile.oil_support_reasons : companySupportReasons;
  const datasetSensitivity = useMemo(() => resolveDatasetAnnualSensitivity(overlay?.sensitivity), [overlay?.sensitivity]);

  const [shortTermCurve, setShortTermCurve] = useState(defaultShortTermCurve);
  const [longTermAnchorInput, setLongTermAnchorInput] = useState(defaultLongTermAnchor == null ? "" : String(defaultLongTermAnchor));
  const [fadeYearsInput, setFadeYearsInput] = useState("2");
  const [sensitivitySource, setSensitivitySource] = useState<SensitivitySource>(datasetSensitivity == null ? "manual" : "dataset");
  const [manualSensitivityInput, setManualSensitivityInput] = useState("");
  const [currentSharePriceInput, setCurrentSharePriceInput] = useState(latestPrice == null ? "" : String(latestPrice));

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

  const activeSensitivity = sensitivitySource === "dataset" ? datasetSensitivity : parseNumber(manualSensitivityInput);
  const currentSharePrice = parseNumber(currentSharePriceInput) ?? latestPrice;
  const fadeYears = Math.max(0, Number.parseInt(fadeYearsInput || "0", 10) || 0);
  const longTermAnchor = parseNumber(longTermAnchorInput);
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
        currentSharePrice,
        annualDiscountRate: 0.1,
        oilSupportStatus: supportStatus,
        confidenceFlags: [...(overlay?.confidence_flags ?? []), ...(overlay?.sensitivity?.confidence_flags ?? [])],
      }),
    [activeAnnualBaseCurve, activeSensitivity, baseFairValuePerShare, currentSharePrice, dilutedShares, fadeYears, longTermAnchor, overlay?.confidence_flags, overlay?.sensitivity?.confidence_flags, shortTermCurve, supportStatus],
  );
  const confidenceReasons = useMemo(
    () => Array.from(new Set([...supportReasons, ...(overlay?.confidence_flags ?? []).map(humanizeFlag), ...overlayResult.confidenceFlags.map(humanizeFlag)])).filter(Boolean),
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

      <div className="workspace-pill-row">
        <span className="pill">Support {titleCase(supportStatus)}</span>
        <span className="pill">Base Fair Value {formatCurrency(baseFairValuePerShare)}</span>
        <span className="pill">Diluted Shares {formatCompact(dilutedShares)}</span>
        <button type="button" className="ticker-button financial-export-button" onClick={() => void handleExportJson()}>
          Export JSON
        </button>
        <button type="button" className="ticker-button financial-export-button" onClick={() => void handleExportCsv()}>
          Export CSV
        </button>
      </div>

      <div className="oil-overlay-controls">
        <label className="oil-overlay-field">
          <span className="metric-label">Benchmark Selector</span>
          <select aria-label="Benchmark Selector" value={benchmarkId} onChange={(event) => setBenchmarkId(event.target.value)}>
            {displayBenchmarkOptions.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          {usingExampleBenchmark ? (
            <span className="text-muted oil-overlay-help">
              No official benchmark points are cached yet. Example mode uses {formatCurrency(exampleBaseOilPrice)}/bbl as a stand-in current oil price so you can see the expected input format.
            </span>
          ) : null}
        </label>

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
            <option value="manual">Manual annual after-tax input</option>
            <option value="dataset" disabled={datasetSensitivity == null}>Overlay dataset{datasetSensitivity == null ? " (unavailable)" : ""}</option>
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
      </div>

      <div className="workspace-card-stack-tight">
        <div className="metric-label">Short-Term Curve Editor</div>
        {usingExampleBenchmark ? (
          <div className="filing-link-card workspace-card-stack-tight oil-overlay-example-card">
            <div className="metric-label">Example Input</div>
            <div>
              If current oil is {formatCurrency(exampleBaseOilPrice)}/bbl, a +5% scenario is {formatCurrency(examplePlusFiveCurve[0]?.price ?? null)}/bbl.
            </div>
            <div className="text-muted">
              Load a simple example to prefill the editable years, then replace those prices with your own path once you have a view.
            </div>
            <div className="oil-overlay-example-actions">
              <button
                type="button"
                className="ticker-button"
                onClick={() => {
                  setBenchmarkId(EXAMPLE_BENCHMARK_ID);
                  setShortTermCurve(examplePlusFiveCurve);
                  setLongTermAnchorInput(String(exampleBaseOilPrice));
                }}
              >
                Load +5% example
              </button>
            </div>
          </div>
        ) : null}
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
                <span className="text-muted">{usingExampleBenchmark ? "Example baseline" : "Official base"} {formatCurrency(activeAnnualBaseCurve[index]?.price ?? point.price)}</span>
              </div>
            ))}
            <div>
              <button type="button" className="ticker-button" onClick={() => setShortTermCurve(defaultShortTermCurve)}>
                {usingExampleBenchmark ? "Reset to example baseline" : "Reset to official curve"}
              </button>
            </div>
          </div>
        ) : (
          <div className="text-muted">No official annual benchmark points are available for the selected benchmark yet.</div>
        )}
      </div>

      <div className="oil-overlay-summary-grid">
        <SummaryCard label="Scenario Fair Value / Share" value={formatCurrency(overlayResult.scenarioFairValuePerShare)} tone="accent" />
        <SummaryCard label="Delta vs Base" value={formatSignedCurrency(overlayResult.deltaVsBasePerShare)} tone="warning" />
        <SummaryCard label="EPS Delta per $1 Oil" value={formatSignedNumber(overlayResult.epsDeltaPerDollarOil)} tone="positive" />
        <SummaryCard label="Upside / Downside" value={formatPercent(overlayResult.impliedUpsideDownside)} tone="cyan" />
      </div>

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

      {overlayResult.yearlyDeltas.length ? (
        <div className="filing-link-card workspace-card-stack-tight">
          <div className="metric-label">Per-Year Deltas</div>
          <table>
            <thead>
              <tr>
                <th>Year</th>
                <th>Oil Delta</th>
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

function resolveExampleBaseOilPrice(series: CompanyOilScenarioOverlayResponse["benchmark_series"]): number {
  for (const item of series ?? []) {
    if (item.latest_value != null && Number.isFinite(item.latest_value)) {
      return item.latest_value;
    }
    for (const point of item.points ?? []) {
      if (point.value != null && Number.isFinite(point.value)) {
        return point.value;
      }
    }
  }
  return EXAMPLE_BASELINE_OIL_PRICE;
}

function resolveExampleStartYear(asOf: string | null | undefined): number {
  const matched = asOf?.match(/(19|20)\d{2}/);
  return matched ? Number(matched[0]) : new Date().getUTCFullYear();
}

function buildExampleBaselineCurve(startYear: number, baselinePrice: number) {
  return Array.from({ length: EXAMPLE_CURVE_YEARS }, (_value, index) => ({
    year: startYear + index,
    price: roundOilPrice(baselinePrice),
  }));
}

function buildExampleScenarioCurve(startYear: number, baselinePrice: number, changePercent: number) {
  const scenarioPrice = roundOilPrice(baselinePrice * (1 + changePercent));
  return Array.from({ length: EXAMPLE_CURVE_YEARS }, (_value, index) => ({
    year: startYear + index,
    price: scenarioPrice,
  }));
}

function roundOilPrice(value: number): number {
  return Math.round(value * 100) / 100;
}