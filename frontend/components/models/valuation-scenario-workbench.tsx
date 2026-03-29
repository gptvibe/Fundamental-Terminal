"use client";

import { useEffect, useMemo, useState } from "react";

import { formatDate, formatPercent, titleCase } from "@/lib/format";
import type { FinancialPayload, ModelPayload, PriceHistoryPoint } from "@/lib/types";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);
const CASE_COLORS = {
  bear: "var(--negative)",
  base: "var(--accent)",
  bull: "var(--positive)",
  overlap: "var(--warning)",
} as const;
const RESIDUAL_LONG_RUN_ROE = 0.1;
const PROJECTION_YEARS = 5;

type ScenarioModelKey = "dcf" | "reverse_dcf" | "residual_income";
type ScenarioCaseKey = "bear" | "base" | "bull";

type RangeRow = {
  label: string;
  low: number;
  high: number;
  base: number;
  accent: string;
};

type TraceabilityRow = {
  assumption: string;
  baseValue: string;
  source: string;
  fields: string;
};

type DcfControls = {
  revenueGrowth: number;
  discountRate: number;
  terminalGrowth: number;
  operatingMargin: number;
  capexPercent: number;
};

type ReverseDcfControls = {
  freeCashFlowMargin: number;
  discountRate: number;
  terminalGrowth: number;
};

type ResidualIncomeControls = {
  averageRoe: number;
  costOfEquity: number;
  terminalGrowth: number;
  payoutRatio: number;
};

type DcfDefaults = {
  ready: boolean;
  resetKey: string;
  revenue: number | null;
  sharesOutstanding: number | null;
  cashConversion: number;
  projectionYears: number;
  periodEnd: string | null;
  latestPrice: number | null;
  controls: DcfControls;
  traceability: TraceabilityRow[];
};

type ReverseDcfDefaults = {
  ready: boolean;
  resetKey: string;
  revenue: number | null;
  sharesOutstanding: number | null;
  latestPrice: number | null;
  controls: ReverseDcfControls;
  traceability: TraceabilityRow[];
};

type ResidualIncomeDefaults = {
  ready: boolean;
  resetKey: string;
  bookEquity: number | null;
  sharesOutstanding: number | null;
  controls: ResidualIncomeControls;
  traceability: TraceabilityRow[];
};

type DcfCase = {
  perShareValue: number;
  totalValue: number;
  revenueGrowth: number;
  discountRate: number;
  terminalGrowth: number;
  operatingMargin: number;
  capexPercent: number;
};

type ReverseDcfCase = {
  impliedGrowth: number;
  freeCashFlowMargin: number;
  discountRate: number;
  terminalGrowth: number;
};

type ResidualIncomeCase = {
  intrinsicValuePerShare: number;
  bookEquityPerShare: number;
  pvResidualIncomePerShare: number;
  terminalValuePerShare: number;
  averageRoe: number;
  costOfEquity: number;
  terminalGrowth: number;
  payoutRatio: number;
};

interface ValuationScenarioWorkbenchProps {
  ticker: string;
  models: ModelPayload[];
  financials: FinancialPayload[];
  priceHistory: PriceHistoryPoint[];
  strictOfficialMode?: boolean;
}

export function ValuationScenarioWorkbench({
  ticker,
  models,
  financials,
  priceHistory,
  strictOfficialMode = false,
}: ValuationScenarioWorkbenchProps) {
  const annualFinancials = useMemo(
    () => financials.filter((statement) => ANNUAL_FORMS.has(statement.filing_type)),
    [financials]
  );
  const latestAnnual = annualFinancials[0] ?? financials[0] ?? null;
  const previousAnnual = annualFinancials[1] ?? financials[1] ?? null;
  const latestPrice = priceHistory.at(-1)?.close ?? null;
  const modelByName = useMemo(
    () => Object.fromEntries(models.map((model) => [model.model_name, model])) as Record<string, ModelPayload | undefined>,
    [models]
  );

  const dcfModel = modelByName.dcf ?? null;
  const reverseDcfModel = modelByName.reverse_dcf ?? null;
  const residualIncomeModel = modelByName.residual_income ?? null;

  const dcfDefaults = useMemo(
    () => buildDcfDefaults(ticker, dcfModel, latestAnnual, previousAnnual, latestPrice),
    [ticker, dcfModel, latestAnnual, previousAnnual, latestPrice]
  );
  const reverseDcfDefaults = useMemo(
    () => buildReverseDcfDefaults(ticker, reverseDcfModel, latestAnnual, latestPrice),
    [ticker, reverseDcfModel, latestAnnual, latestPrice]
  );
  const residualIncomeDefaults = useMemo(
    () => buildResidualIncomeDefaults(ticker, residualIncomeModel, latestAnnual),
    [ticker, residualIncomeModel, latestAnnual]
  );

  const [activeModel, setActiveModel] = useState<ScenarioModelKey>("dcf");
  const [dcfControls, setDcfControls] = useState<DcfControls>(dcfDefaults.controls);
  const [reverseDcfControls, setReverseDcfControls] = useState<ReverseDcfControls>(reverseDcfDefaults.controls);
  const [residualIncomeControls, setResidualIncomeControls] = useState<ResidualIncomeControls>(residualIncomeDefaults.controls);

  useEffect(() => {
    setDcfControls(dcfDefaults.controls);
  }, [dcfDefaults.controls, dcfDefaults.resetKey]);

  useEffect(() => {
    setReverseDcfControls(reverseDcfDefaults.controls);
  }, [reverseDcfDefaults.controls, reverseDcfDefaults.resetKey]);

  useEffect(() => {
    setResidualIncomeControls(residualIncomeDefaults.controls);
  }, [residualIncomeDefaults.controls, residualIncomeDefaults.resetKey]);

  const dcfScenarios = useMemo(() => buildDcfScenarioSet(dcfDefaults, dcfControls), [dcfDefaults, dcfControls]);
  const reverseDcfScenarios = useMemo(
    () => buildReverseDcfScenarioSet(reverseDcfDefaults, reverseDcfControls),
    [reverseDcfDefaults, reverseDcfControls]
  );
  const residualIncomeScenarios = useMemo(
    () => buildResidualIncomeScenarioSet(residualIncomeDefaults, residualIncomeControls),
    [residualIncomeDefaults, residualIncomeControls]
  );

  const availableTabs = useMemo(() => {
    const tabs: Array<{ key: ScenarioModelKey; label: string; model: ModelPayload | null }> = [];
    if (dcfModel) {
      tabs.push({ key: "dcf", label: "DCF", model: dcfModel });
    }
    if (reverseDcfModel) {
      tabs.push({ key: "reverse_dcf", label: "Reverse DCF", model: reverseDcfModel });
    }
    if (residualIncomeModel) {
      tabs.push({ key: "residual_income", label: "Residual Income", model: residualIncomeModel });
    }
    return tabs;
  }, [dcfModel, reverseDcfModel, residualIncomeModel]);

  useEffect(() => {
    if (availableTabs.some((tab) => tab.key === activeModel)) {
      return;
    }
    setActiveModel(availableTabs[0]?.key ?? "dcf");
  }, [activeModel, availableTabs]);

  const overlapRows = useMemo(() => {
    const rows: RangeRow[] = [];
    if (dcfScenarios) {
      rows.push({
        label: "DCF",
        low: dcfScenarios.bear.perShareValue,
        high: dcfScenarios.bull.perShareValue,
        base: dcfScenarios.base.perShareValue,
        accent: CASE_COLORS.base,
      });
    }
    if (residualIncomeScenarios) {
      rows.push({
        label: "Residual Income",
        low: residualIncomeScenarios.bear.intrinsicValuePerShare,
        high: residualIncomeScenarios.bull.intrinsicValuePerShare,
        base: residualIncomeScenarios.base.intrinsicValuePerShare,
        accent: CASE_COLORS.bull,
      });
    }
    return rows;
  }, [dcfScenarios, residualIncomeScenarios]);
  const overlapRange = useMemo(() => computeOverlapRange(overlapRows), [overlapRows]);

  if (!availableTabs.length) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 260 }}>
        <div className="grid-empty-kicker">Scenario engine</div>
        <div className="grid-empty-title">Valuation scenario ranges unavailable</div>
        <div className="grid-empty-copy">
          Warm the cached valuation models first, then the base, bear, and bull workbench turns interactive.
        </div>
      </div>
    );
  }

  return (
    <div className="valuation-workbench-shell">
      {strictOfficialMode ? (
        <div className="text-muted" style={{ marginBottom: 4 }}>
          Strict official mode keeps SEC and Treasury-derived scenario ranges available, but it suppresses reverse DCF and
          current-price comparison overlays unless an official closing-price source is configured.
        </div>
      ) : null}

      <div className="valuation-overlap-card">
        <div className="valuation-card-header">
          <div>
            <div className="valuation-card-kicker">Range overlap</div>
            <div className="valuation-card-title">Per-share valuation overlap</div>
          </div>
          <div className="valuation-card-subtitle">
            Range overlap highlights where independent valuation methods agree instead of anchoring the page on one point estimate.
          </div>
        </div>
        {overlapRows.length ? (
          <>
            <RangeComparison
              rows={
                overlapRange
                  ? [...overlapRows, { label: "Overlap", low: overlapRange.low, high: overlapRange.high, base: overlapRange.base, accent: CASE_COLORS.overlap }]
                  : overlapRows
              }
              formatValue={formatCurrency}
              referenceValue={strictOfficialMode ? null : latestPrice}
              referenceLabel={strictOfficialMode ? null : "Latest price"}
            />
            <div className="valuation-pill-row">
              <span className="pill">Anchored models {overlapRows.length}</span>
              <span className="pill">
                Overlap {overlapRange ? `${formatCurrency(overlapRange.low)} - ${formatCurrency(overlapRange.high)}` : "None"}
              </span>
              <span className="pill">Base range {formatCurrency(minRowBase(overlapRows))} - {formatCurrency(maxRowBase(overlapRows))}</span>
            </div>
          </>
        ) : (
          <div className="text-muted">
            Per-share overlap appears once DCF or residual income scenarios have enough SEC-backed inputs to compute a range.
          </div>
        )}
      </div>

      <div className="valuation-tab-bar" role="tablist" aria-label="Valuation scenario models">
        {availableTabs.map((tab) => {
          const status = modelStatus(tab.model?.result);
          return (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={activeModel === tab.key}
              className={`valuation-tab-button${activeModel === tab.key ? " active" : ""}`}
              onClick={() => setActiveModel(tab.key)}
            >
              <span>{tab.label}</span>
              <span className="valuation-tab-status">{statusLabel(status)}</span>
            </button>
          );
        })}
      </div>

      {activeModel === "dcf"
        ? renderDcfWorkbench({
            model: dcfModel,
            defaults: dcfDefaults,
            controls: dcfControls,
            onControlsChange: setDcfControls,
            scenarios: dcfScenarios,
            strictOfficialMode,
          })
        : null}

      {activeModel === "reverse_dcf"
        ? renderReverseDcfWorkbench({
            model: reverseDcfModel,
            defaults: reverseDcfDefaults,
            controls: reverseDcfControls,
            onControlsChange: setReverseDcfControls,
            scenarios: reverseDcfScenarios,
            strictOfficialMode,
          })
        : null}

      {activeModel === "residual_income"
        ? renderResidualIncomeWorkbench({
            model: residualIncomeModel,
            defaults: residualIncomeDefaults,
            controls: residualIncomeControls,
            onControlsChange: setResidualIncomeControls,
            scenarios: residualIncomeScenarios,
            strictOfficialMode,
          })
        : null}
    </div>
  );
}

function renderDcfWorkbench({
  model,
  defaults,
  controls,
  onControlsChange,
  scenarios,
  strictOfficialMode,
}: {
  model: ModelPayload | null;
  defaults: DcfDefaults;
  controls: DcfControls;
  onControlsChange: React.Dispatch<React.SetStateAction<DcfControls>>;
  scenarios: Record<ScenarioCaseKey, DcfCase> | null;
  strictOfficialMode: boolean;
}) {
  const result = asRecord(model?.result);
  const status = modelStatus(result);
  if (status === "unsupported") {
    return <ScenarioUnavailable title="DCF scenario analysis unsupported" copy={scenarioReason(result)} />;
  }
  if (!defaults.ready || !scenarios) {
    return <ScenarioUnavailable title="DCF scenario analysis unavailable" copy={scenarioReason(result)} />;
  }

  const basePriceGap =
    strictOfficialMode || defaults.latestPrice === null
      ? null
      : safeDivide(scenarios.base.perShareValue - defaults.latestPrice, defaults.latestPrice);

  return (
    <ScenarioWorkbenchLayout
      controls={
        <>
          <div className="valuation-card-header">
            <div>
              <div className="valuation-card-kicker">Scenario inputs</div>
              <div className="valuation-card-title">DCF sensitivities</div>
            </div>
            <div className="valuation-card-subtitle">Revenue, margin, reinvestment, and discount assumptions stay tied back to SEC filings and Treasury inputs.</div>
          </div>
          <div className="dcf-control-list">
            <SliderControl label="Revenue Growth" value={controls.revenueGrowth} min={-0.05} max={0.25} step={0.005} accent={CASE_COLORS.base} onChange={(value) => onControlsChange((current) => ({ ...current, revenueGrowth: value }))} />
            <SliderControl label="Discount Rate" value={controls.discountRate} min={0.05} max={0.18} step={0.0025} accent={CASE_COLORS.bear} onChange={(value) => onControlsChange((current) => ({ ...current, discountRate: value, terminalGrowth: Math.min(current.terminalGrowth, value - 0.01) }))} />
            <SliderControl label="Terminal Growth" value={controls.terminalGrowth} min={0} max={Math.min(0.06, Math.max(controls.discountRate - 0.01, 0))} step={0.0025} accent={CASE_COLORS.overlap} onChange={(value) => onControlsChange((current) => ({ ...current, terminalGrowth: Math.min(value, current.discountRate - 0.01) }))} />
            <SliderControl label="Operating Margin" value={controls.operatingMargin} min={0.05} max={0.5} step={0.005} accent={CASE_COLORS.bull} onChange={(value) => onControlsChange((current) => ({ ...current, operatingMargin: value }))} />
            <SliderControl label="Capex % of Revenue" value={controls.capexPercent} min={0.01} max={0.15} step={0.0025} accent="#a78bfa" onChange={(value) => onControlsChange((current) => ({ ...current, capexPercent: value }))} />
          </div>
          <TraceabilityTable rows={defaults.traceability} />
        </>
      }
      outputs={
        <>
          <div className="valuation-card-header">
            <div>
              <div className="valuation-card-kicker">Range output</div>
              <div className="valuation-card-title">DCF bear / base / bull range</div>
            </div>
            <div className="valuation-card-subtitle">The range is shown as a span with the base case centered instead of a single fair-value point.</div>
          </div>
          <RangeComparison
            rows={[
              {
                label: "DCF intrinsic value / share",
                low: scenarios.bear.perShareValue,
                high: scenarios.bull.perShareValue,
                base: scenarios.base.perShareValue,
                accent: CASE_COLORS.base,
              },
            ]}
            formatValue={formatCurrency}
            referenceValue={strictOfficialMode ? null : defaults.latestPrice}
            referenceLabel={strictOfficialMode ? null : "Latest price"}
          />
          <ScenarioSummaryStrip
            cards={[
              { label: "Bear Case", value: formatCurrency(scenarios.bear.perShareValue), accent: "bear" },
              { label: "Base Case", value: formatCurrency(scenarios.base.perShareValue), accent: "base" },
              { label: "Bull Case", value: formatCurrency(scenarios.bull.perShareValue), accent: "bull" },
              { label: "Scenario Range", value: `${formatCurrency(scenarios.bear.perShareValue)} - ${formatCurrency(scenarios.bull.perShareValue)}`, accent: "cyan" },
              { label: "Gap vs Price", value: strictOfficialMode ? "Disabled" : formatPercent(basePriceGap), accent: "gold" },
            ]}
          />
          <ModelDiagnosticsCard modelName="DCF" result={result} />
        </>
      }
    />
  );
}

function renderReverseDcfWorkbench({
  model,
  defaults,
  controls,
  onControlsChange,
  scenarios,
  strictOfficialMode,
}: {
  model: ModelPayload | null;
  defaults: ReverseDcfDefaults;
  controls: ReverseDcfControls;
  onControlsChange: React.Dispatch<React.SetStateAction<ReverseDcfControls>>;
  scenarios: Record<ScenarioCaseKey, ReverseDcfCase> | null;
  strictOfficialMode: boolean;
}) {
  const result = asRecord(model?.result);
  const status = modelStatus(result);
  if (strictOfficialMode) {
    return <ScenarioUnavailable title="Reverse DCF withheld in strict official mode" copy="Reverse DCF depends on a current equity price. This workspace hides that scenario until an official closing-price source is configured." />;
  }
  if (status === "unsupported") {
    return <ScenarioUnavailable title="Reverse DCF scenario analysis unsupported" copy={scenarioReason(result)} />;
  }
  if (!defaults.ready || !scenarios) {
    return <ScenarioUnavailable title="Reverse DCF scenario analysis unavailable" copy={scenarioReason(result)} />;
  }

  return (
    <ScenarioWorkbenchLayout
      controls={
        <>
          <div className="valuation-card-header">
            <div>
              <div className="valuation-card-kicker">Scenario inputs</div>
              <div className="valuation-card-title">Reverse DCF sensitivities</div>
            </div>
            <div className="valuation-card-subtitle">These controls change how demanding the market-implied growth hurdle becomes at the current price.</div>
          </div>
          <div className="dcf-control-list">
            <SliderControl label="Free Cash Flow Margin" value={controls.freeCashFlowMargin} min={-0.05} max={0.35} step={0.005} accent={CASE_COLORS.base} onChange={(value) => onControlsChange((current) => ({ ...current, freeCashFlowMargin: value }))} />
            <SliderControl label="Discount Rate" value={controls.discountRate} min={0.05} max={0.2} step={0.0025} accent={CASE_COLORS.bear} onChange={(value) => onControlsChange((current) => ({ ...current, discountRate: value, terminalGrowth: Math.min(current.terminalGrowth, value - 0.01) }))} />
            <SliderControl label="Terminal Growth" value={controls.terminalGrowth} min={-0.01} max={Math.min(0.06, Math.max(controls.discountRate - 0.01, -0.01))} step={0.0025} accent={CASE_COLORS.overlap} onChange={(value) => onControlsChange((current) => ({ ...current, terminalGrowth: Math.min(value, current.discountRate - 0.01) }))} />
          </div>
          <TraceabilityTable rows={defaults.traceability} />
        </>
      }
      outputs={
        <>
          <div className="valuation-card-header">
            <div>
              <div className="valuation-card-kicker">Range output</div>
              <div className="valuation-card-title">Implied growth range</div>
            </div>
            <div className="valuation-card-subtitle">Bear/base/bull scenarios show how much growth the current market cap implies under each sensitivity set.</div>
          </div>
          <RangeComparison
            rows={[
              {
                label: "Implied growth",
                low: scenarios.bear.impliedGrowth,
                high: scenarios.bull.impliedGrowth,
                base: scenarios.base.impliedGrowth,
                accent: CASE_COLORS.base,
              },
            ]}
            formatValue={formatPercent}
          />
          <ScenarioSummaryStrip
            cards={[
              { label: "Bear Case", value: formatPercent(scenarios.bear.impliedGrowth), accent: "bear" },
              { label: "Base Case", value: formatPercent(scenarios.base.impliedGrowth), accent: "base" },
              { label: "Bull Case", value: formatPercent(scenarios.bull.impliedGrowth), accent: "bull" },
              { label: "FCF Margin", value: formatPercent(scenarios.base.freeCashFlowMargin), accent: "cyan" },
              { label: "Price Anchor", value: formatCurrency(defaults.latestPrice), accent: "gold" },
            ]}
          />
          <ModelDiagnosticsCard modelName="Reverse DCF" result={result} />
        </>
      }
    />
  );
}

function renderResidualIncomeWorkbench({
  model,
  defaults,
  controls,
  onControlsChange,
  scenarios,
  strictOfficialMode,
}: {
  model: ModelPayload | null;
  defaults: ResidualIncomeDefaults;
  controls: ResidualIncomeControls;
  onControlsChange: React.Dispatch<React.SetStateAction<ResidualIncomeControls>>;
  scenarios: Record<ScenarioCaseKey, ResidualIncomeCase> | null;
  strictOfficialMode: boolean;
}) {
  const result = asRecord(model?.result);
  if (!defaults.ready || !scenarios) {
    return <ScenarioUnavailable title="Residual income scenario analysis unavailable" copy={scenarioReason(result)} />;
  }

  const priceSnapshot = asRecord(result.price_snapshot);
  const latestPrice = strictOfficialMode ? null : asNumber(priceSnapshot.latest_price);
  const priceGap = latestPrice === null ? null : safeDivide(scenarios.base.intrinsicValuePerShare - latestPrice, latestPrice);

  return (
    <ScenarioWorkbenchLayout
      controls={
        <>
          <div className="valuation-card-header">
            <div>
              <div className="valuation-card-kicker">Scenario inputs</div>
              <div className="valuation-card-title">Residual income sensitivities</div>
            </div>
            <div className="valuation-card-subtitle">Residual income stays especially useful for balance-sheet-driven firms, with SEC book equity and earnings feeding each slider.</div>
          </div>
          <div className="dcf-control-list">
            <SliderControl label="Average ROE" value={controls.averageRoe} min={-0.05} max={0.35} step={0.005} accent={CASE_COLORS.base} onChange={(value) => onControlsChange((current) => ({ ...current, averageRoe: value }))} />
            <SliderControl label="Cost of Equity" value={controls.costOfEquity} min={0.05} max={0.2} step={0.0025} accent={CASE_COLORS.bear} onChange={(value) => onControlsChange((current) => ({ ...current, costOfEquity: value, terminalGrowth: Math.min(current.terminalGrowth, value - 0.01) }))} />
            <SliderControl label="Terminal Growth" value={controls.terminalGrowth} min={0} max={Math.min(0.05, Math.max(controls.costOfEquity - 0.01, 0))} step={0.0025} accent={CASE_COLORS.overlap} onChange={(value) => onControlsChange((current) => ({ ...current, terminalGrowth: Math.min(value, current.costOfEquity - 0.01) }))} />
            <SliderControl label="Payout Ratio" value={controls.payoutRatio} min={0} max={0.8} step={0.01} accent={CASE_COLORS.bull} onChange={(value) => onControlsChange((current) => ({ ...current, payoutRatio: value }))} />
          </div>
          <TraceabilityTable rows={defaults.traceability} />
        </>
      }
      outputs={
        <>
          <div className="valuation-card-header">
            <div>
              <div className="valuation-card-kicker">Range output</div>
              <div className="valuation-card-title">Residual income bear / base / bull range</div>
            </div>
            <div className="valuation-card-subtitle">This range shows the spread between optimistic and conservative equity-value paths, not just one intrinsic-value print.</div>
          </div>
          <RangeComparison
            rows={[
              {
                label: "Intrinsic value / share",
                low: scenarios.bear.intrinsicValuePerShare,
                high: scenarios.bull.intrinsicValuePerShare,
                base: scenarios.base.intrinsicValuePerShare,
                accent: CASE_COLORS.bull,
              },
            ]}
            formatValue={formatCurrency}
            referenceValue={latestPrice}
            referenceLabel={latestPrice === null ? null : "Latest price"}
          />
          <ScenarioSummaryStrip
            cards={[
              { label: "Bear Case", value: formatCurrency(scenarios.bear.intrinsicValuePerShare), accent: "bear" },
              { label: "Base Case", value: formatCurrency(scenarios.base.intrinsicValuePerShare), accent: "base" },
              { label: "Bull Case", value: formatCurrency(scenarios.bull.intrinsicValuePerShare), accent: "bull" },
              { label: "Book Equity / Share", value: formatCurrency(scenarios.base.bookEquityPerShare), accent: "cyan" },
              { label: "Gap vs Price", value: latestPrice === null ? "Disabled" : formatPercent(priceGap), accent: "gold" },
            ]}
          />
          <ModelDiagnosticsCard modelName="Residual Income" result={result} />
        </>
      }
    />
  );
}

function ScenarioWorkbenchLayout({ controls, outputs }: { controls: React.ReactNode; outputs: React.ReactNode }) {
  return (
    <div className="valuation-workbench-grid">
      <div className="valuation-card">{controls}</div>
      <div className="valuation-card">{outputs}</div>
    </div>
  );
}

function ScenarioUnavailable({ title, copy }: { title: string; copy: string }) {
  return (
    <div className="grid-empty-state" style={{ minHeight: 260 }}>
      <div className="grid-empty-kicker">Scenario engine</div>
      <div className="grid-empty-title">{title}</div>
      <div className="grid-empty-copy">{copy}</div>
    </div>
  );
}

function SliderControl({
  label,
  value,
  min,
  max,
  step,
  accent,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  accent: string;
  onChange: (value: number) => void;
}) {
  return (
    <label className="dcf-slider-card">
      <div className="dcf-slider-top">
        <span>{label}</span>
        <span className="dcf-slider-value">{formatPercent(value)}</span>
      </div>
      <input
        aria-label={label}
        className="dcf-slider"
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        style={{ accentColor: accent }}
      />
      <div className="dcf-slider-scale">
        <span>{formatPercent(min)}</span>
        <span>{formatPercent(max)}</span>
      </div>
    </label>
  );
}

function ScenarioSummaryStrip({
  cards,
}: {
  cards: Array<{ label: string; value: string; accent: "bear" | "base" | "bull" | "gold" | "cyan" }>;
}) {
  return (
    <div className="dcf-summary-strip">
      {cards.map((card) => (
        <div key={card.label} className={`dcf-summary-card accent-${card.accent}`}>
          <div className="dcf-summary-label">{card.label}</div>
          <div className="dcf-summary-value">{card.value}</div>
        </div>
      ))}
    </div>
  );
}

function TraceabilityTable({ rows }: { rows: TraceabilityRow[] }) {
  return (
    <div className="valuation-trace-card">
      <div className="valuation-card-kicker">Traceability</div>
      <div className="valuation-card-title">Assumption lineage</div>
      <table className="valuation-trace-table">
        <thead>
          <tr>
            <th>Assumption</th>
            <th>Base</th>
            <th>Source</th>
            <th>Fields used</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.assumption}>
              <td>{row.assumption}</td>
              <td>{row.baseValue}</td>
              <td>{row.source}</td>
              <td>{row.fields}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RangeComparison({
  rows,
  formatValue,
  referenceValue,
  referenceLabel,
}: {
  rows: RangeRow[];
  formatValue: (value: number | null) => string;
  referenceValue?: number | null;
  referenceLabel?: string | null;
}) {
  const allValues = rows.flatMap((row) => [row.low, row.high, row.base]);
  if (referenceValue !== null && referenceValue !== undefined) {
    allValues.push(referenceValue);
  }
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const span = Math.max(max - min, 1e-9);
  const referencePosition = referenceValue === null || referenceValue === undefined ? null : ((referenceValue - min) / span) * 100;

  return (
    <div className="valuation-range-shell">
      <div className="valuation-range-axis">
        <span>{formatValue(min)}</span>
        <span>{formatValue(max)}</span>
      </div>
      <div className="valuation-range-list">
        {rows.map((row) => {
          const left = ((row.low - min) / span) * 100;
          const width = ((row.high - row.low) / span) * 100;
          const marker = ((row.base - min) / span) * 100;
          return (
            <div key={row.label} className="valuation-range-row">
              <div className="valuation-range-labels">
                <span>{row.label}</span>
                <span>{formatValue(row.low)} - {formatValue(row.high)}</span>
              </div>
              <div className="valuation-range-track">
                {referencePosition !== null ? (
                  <span className="valuation-range-reference" style={{ left: `${referencePosition}%` }} title={referenceLabel ?? "Reference"} />
                ) : null}
                <span className="valuation-range-fill" style={{ left: `${left}%`, width: `${Math.max(width, 1)}%`, background: row.accent }} />
                <span className="valuation-range-marker" style={{ left: `${marker}%`, borderColor: row.accent }} />
              </div>
              <div className="valuation-range-base">Base {formatValue(row.base)}</div>
            </div>
          );
        })}
      </div>
      {referencePosition !== null && referenceLabel ? (
        <div className="valuation-reference-caption">{referenceLabel}: {formatValue(referenceValue ?? null)}</div>
      ) : null}
    </div>
  );
}

function ModelDiagnosticsCard({ modelName, result }: { modelName: string; result: Record<string, unknown> }) {
  const fieldsUsed = stringArray(result.fields_used);
  const confidenceReasons = stringArray(result.confidence_reasons);
  const misleadingReasons = stringArray(result.misleading_reasons);
  const proxyUsage = asRecord(result.proxy_usage);
  const proxyItems = asObjectArray(proxyUsage.items);
  const staleInputs = asObjectArray(result.stale_inputs);
  const sectorSuitability = asRecord(result.sector_suitability);

  return (
    <div className="valuation-diagnostics-card">
      <div className="valuation-card-kicker">Model context</div>
      <div className="valuation-card-title">{modelName} caveats and evidence</div>
      <div className="valuation-chip-group">
        <span className="pill">Status {statusLabel(modelStatus(result))}</span>
        <span className="pill">Confidence {formatConfidence(result.confidence_score)}</span>
        <span className="pill">Suitability {String(sectorSuitability.reason ?? "No sector note")}</span>
      </div>

      <div className="valuation-detail-block">
        <div className="valuation-detail-label">Exact fields used</div>
        <div className="valuation-chip-group">
          {fieldsUsed.length ? fieldsUsed.map((field) => <span key={field} className="pill">{field}</span>) : <span className="text-muted">No field inventory returned.</span>}
        </div>
      </div>

      <div className="valuation-detail-block">
        <div className="valuation-detail-label">Proxy usage</div>
        {proxyItems.length ? (
          <ul className="valuation-note-list">
            {proxyItems.map((item, index) => (
              <li key={`${String(item.target ?? "proxy")}-${index}`}>
                {String(item.target ?? "proxy")}: {String(item.reason ?? "Proxy substitution used.")}
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-muted">No proxy substitutions were surfaced for this model run.</div>
        )}
      </div>

      <div className="valuation-detail-block">
        <div className="valuation-detail-label">Stale inputs</div>
        {staleInputs.length ? (
          <ul className="valuation-note-list">
            {staleInputs.map((item, index) => (
              <li key={`${String(item.input_name ?? "stale")}-${index}`}>
                {String(item.input_name ?? "Input")}: {String(item.reason ?? "Supporting input is stale.")}
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-muted">No stale-input warnings were attached to this model run.</div>
        )}
      </div>

      <div className="valuation-detail-block">
        <div className="valuation-detail-label">Confidence reasons</div>
        {confidenceReasons.length ? (
          <ul className="valuation-note-list">
            {confidenceReasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        ) : (
          <div className="text-muted">No confidence rationale returned.</div>
        )}
      </div>

      <div className="valuation-detail-block">
        <div className="valuation-detail-label">Why this can mislead</div>
        {misleadingReasons.length ? (
          <ul className="valuation-note-list">
            {misleadingReasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        ) : (
          <div className="text-muted">No model-specific warning text returned.</div>
        )}
      </div>
    </div>
  );
}

function buildDcfDefaults(
  ticker: string,
  dcfModel: ModelPayload | null,
  latestAnnual: FinancialPayload | null,
  previousAnnual: FinancialPayload | null,
  latestPrice: number | null
): DcfDefaults {
  const result = asRecord(dcfModel?.result);
  const assumptions = asRecord(result.assumptions);
  const provenance = asRecord(result.assumption_provenance);
  const riskFree = asRecord(provenance.risk_free_rate);
  const revenueGrowthDefault = growthRate(latestAnnual?.revenue ?? null, previousAnnual?.revenue ?? null) ?? 0.05;
  const discountRateDefault = asNumber(assumptions.discount_rate) ?? 0.1;
  const terminalGrowthDefault = clamp(asNumber(assumptions.terminal_growth_rate) ?? 0.025, 0, Math.max(discountRateDefault - 0.01, 0));
  const operatingMarginDefault = safeDivide(latestAnnual?.operating_income ?? null, latestAnnual?.revenue ?? null) ?? 0.18;
  const capexPercentDefault =
    safeDivide(
      latestAnnual && latestAnnual.operating_cash_flow !== null && latestAnnual.free_cash_flow !== null
        ? Math.abs(latestAnnual.operating_cash_flow - latestAnnual.free_cash_flow)
        : null,
      latestAnnual?.revenue ?? null
    ) ?? 0.05;

  return {
    ready: latestAnnual?.revenue !== null && deriveSharesOutstanding(latestAnnual) !== null,
    resetKey: [ticker, latestAnnual?.period_end ?? "none", latestPrice ?? "none", discountRateDefault].join(":"),
    revenue: latestAnnual?.revenue ?? null,
    sharesOutstanding: deriveSharesOutstanding(latestAnnual),
    cashConversion: clamp(safeDivide(latestAnnual?.operating_cash_flow ?? null, latestAnnual?.operating_income ?? null) ?? 0.9, 0.35, 2.2),
    projectionYears: asNumber(assumptions.projection_years) ?? PROJECTION_YEARS,
    periodEnd: latestAnnual?.period_end ?? null,
    latestPrice,
    controls: {
      revenueGrowth: clamp(revenueGrowthDefault, -0.05, 0.25),
      discountRate: clamp(discountRateDefault, 0.05, 0.18),
      terminalGrowth: terminalGrowthDefault,
      operatingMargin: clamp(operatingMarginDefault, 0.05, 0.5),
      capexPercent: clamp(capexPercentDefault, 0.01, 0.15),
    },
    traceability: [
      {
        assumption: "Revenue Growth",
        baseValue: formatPercent(revenueGrowthDefault),
        source: "SEC annual revenue trend",
        fields: "revenue",
      },
      {
        assumption: "Discount Rate",
        baseValue: formatPercent(discountRateDefault),
        source: `Treasury curve (${String(riskFree.source_name ?? "official risk-free")}) plus equity risk premium`,
        fields: "risk_free_rate, equity_risk_premium, sector_risk_premium",
      },
      {
        assumption: "Terminal Growth",
        baseValue: formatPercent(terminalGrowthDefault),
        source: `Treasury-backed terminal assumption as of ${formatDate(String(riskFree.observation_date ?? null))}`,
        fields: "terminal_growth_rate",
      },
      {
        assumption: "Operating Margin",
        baseValue: formatPercent(operatingMarginDefault),
        source: "SEC income statement",
        fields: "operating_income, revenue",
      },
      {
        assumption: "Capex % of Revenue",
        baseValue: formatPercent(capexPercentDefault),
        source: "SEC cash flow statement",
        fields: "operating_cash_flow, free_cash_flow, revenue",
      },
    ],
  };
}

function buildReverseDcfDefaults(
  ticker: string,
  reverseDcfModel: ModelPayload | null,
  latestAnnual: FinancialPayload | null,
  latestPrice: number | null
): ReverseDcfDefaults {
  const result = asRecord(reverseDcfModel?.result);
  const provenance = asRecord(result.assumption_provenance);
  const discountInputs = asRecord(provenance.discount_rate_inputs);
  const priceSnapshot = asRecord(result.price_snapshot);
  const resolvedPrice = asNumber(priceSnapshot.latest_price) ?? latestPrice;
  const revenue = latestAnnual?.revenue ?? null;
  const sharesOutstanding = deriveSharesOutstanding(latestAnnual);
  const freeCashFlowMarginDefault =
    asNumber(result.implied_margin) ??
    safeDivide(latestAnnual?.free_cash_flow ?? latestAnnual?.operating_cash_flow ?? null, latestAnnual?.revenue ?? null) ??
    0.1;
  const discountRateDefault = asNumber(discountInputs.discount_rate) ?? 0.11;
  const terminalGrowthDefault = clamp(asNumber(discountInputs.terminal_growth) ?? 0.025, -0.01, Math.max(discountRateDefault - 0.01, -0.01));

  return {
    ready: revenue !== null && sharesOutstanding !== null && resolvedPrice !== null,
    resetKey: [ticker, latestAnnual?.period_end ?? "none", resolvedPrice ?? "none", freeCashFlowMarginDefault].join(":"),
    revenue,
    sharesOutstanding,
    latestPrice: resolvedPrice,
    controls: {
      freeCashFlowMargin: clamp(freeCashFlowMarginDefault, -0.05, 0.35),
      discountRate: clamp(discountRateDefault, 0.05, 0.2),
      terminalGrowth: terminalGrowthDefault,
    },
    traceability: [
      {
        assumption: "Free Cash Flow Margin",
        baseValue: formatPercent(freeCashFlowMarginDefault),
        source: "SEC filing cash flow margin or normalized proxy",
        fields: "free_cash_flow, operating_cash_flow, revenue",
      },
      {
        assumption: "Discount Rate",
        baseValue: formatPercent(discountRateDefault),
        source: "Treasury curve plus reverse-DCF spread",
        fields: "risk_free_rate, discount_rate",
      },
      {
        assumption: "Terminal Growth",
        baseValue: formatPercent(terminalGrowthDefault),
        source: "Treasury-backed terminal assumption",
        fields: "terminal_growth",
      },
      {
        assumption: "Current Price Anchor",
        baseValue: formatCurrency(resolvedPrice),
        source: String(priceSnapshot.price_source ?? "Cached market price"),
        fields: "market_snapshot.latest_price",
      },
    ],
  };
}

function buildResidualIncomeDefaults(
  ticker: string,
  residualIncomeModel: ModelPayload | null,
  latestAnnual: FinancialPayload | null
): ResidualIncomeDefaults {
  const result = asRecord(residualIncomeModel?.result);
  const inputs = asRecord(result.inputs);
  const provenance = asRecord(result.assumption_provenance);
  const riskFree = asRecord(provenance.risk_free_rate);
  const bookEquity =
    asNumber(inputs.book_equity) ??
    (latestAnnual && latestAnnual.total_assets !== null && latestAnnual.total_liabilities !== null
      ? latestAnnual.total_assets - latestAnnual.total_liabilities
      : latestAnnual?.stockholders_equity ?? null);
  const sharesOutstanding = asNumber(inputs.shares_outstanding) ?? deriveSharesOutstanding(latestAnnual);
  const averageRoeDefault = asNumber(inputs.avg_roe_5y) ?? safeDivide(latestAnnual?.net_income ?? null, bookEquity) ?? 0.1;
  const costOfEquityDefault = asNumber(inputs.cost_of_equity) ?? 0.1;
  const terminalGrowthDefault = clamp(asNumber(inputs.terminal_growth_rate) ?? 0.025, 0, Math.max(costOfEquityDefault - 0.01, 0));
  const payoutRatioDefault = clamp(asNumber(inputs.payout_ratio_assumed) ?? 0.4, 0, 0.8);

  return {
    ready: bookEquity !== null && sharesOutstanding !== null,
    resetKey: [ticker, latestAnnual?.period_end ?? "none", bookEquity ?? "none", sharesOutstanding ?? "none"].join(":"),
    bookEquity,
    sharesOutstanding,
    controls: {
      averageRoe: clamp(averageRoeDefault, -0.05, 0.35),
      costOfEquity: clamp(costOfEquityDefault, 0.05, 0.2),
      terminalGrowth: terminalGrowthDefault,
      payoutRatio: payoutRatioDefault,
    },
    traceability: [
      {
        assumption: "Average ROE",
        baseValue: formatPercent(averageRoeDefault),
        source: "SEC earnings and equity history",
        fields: "net_income, total_assets, total_liabilities, stockholders_equity",
      },
      {
        assumption: "Cost of Equity",
        baseValue: formatPercent(costOfEquityDefault),
        source: `Treasury curve (${String(riskFree.source_name ?? "official risk-free")}) plus equity and financial-risk premia`,
        fields: "risk_free_rate, equity_risk_premium, financial_firm_additional_risk",
      },
      {
        assumption: "Terminal Growth",
        baseValue: formatPercent(terminalGrowthDefault),
        source: "Long-run macro growth convention",
        fields: "terminal_growth_rate",
      },
      {
        assumption: "Payout Ratio",
        baseValue: formatPercent(payoutRatioDefault),
        source: "Model retention convention derived from ROE and terminal growth",
        fields: "payout_ratio_assumed",
      },
    ],
  };
}

function buildDcfScenarioSet(
  defaults: DcfDefaults,
  controls: DcfControls
): Record<ScenarioCaseKey, DcfCase> | null {
  if (!defaults.ready || defaults.revenue === null || defaults.sharesOutstanding === null) {
    return null;
  }
  return {
    bear: buildDcfScenario(defaults, controls, -1),
    base: buildDcfScenario(defaults, controls, 0),
    bull: buildDcfScenario(defaults, controls, 1),
  };
}

function buildReverseDcfScenarioSet(
  defaults: ReverseDcfDefaults,
  controls: ReverseDcfControls
): Record<ScenarioCaseKey, ReverseDcfCase> | null {
  if (!defaults.ready || defaults.revenue === null || defaults.sharesOutstanding === null || defaults.latestPrice === null) {
    return null;
  }
  return {
    bear: buildReverseDcfScenario(defaults, controls, -1),
    base: buildReverseDcfScenario(defaults, controls, 0),
    bull: buildReverseDcfScenario(defaults, controls, 1),
  };
}

function buildResidualIncomeScenarioSet(
  defaults: ResidualIncomeDefaults,
  controls: ResidualIncomeControls
): Record<ScenarioCaseKey, ResidualIncomeCase> | null {
  if (!defaults.ready || defaults.bookEquity === null || defaults.sharesOutstanding === null) {
    return null;
  }
  return {
    bear: buildResidualIncomeScenario(defaults, controls, -1),
    base: buildResidualIncomeScenario(defaults, controls, 0),
    bull: buildResidualIncomeScenario(defaults, controls, 1),
  };
}

function buildDcfScenario(defaults: DcfDefaults, controls: DcfControls, shift: -1 | 0 | 1): DcfCase {
  const revenueGrowth = clamp(controls.revenueGrowth + shift * 0.025, -0.08, 0.3);
  const discountRate = clamp(controls.discountRate - shift * 0.0125, 0.05, 0.2);
  const terminalGrowth = clamp(controls.terminalGrowth + shift * 0.006, -0.01, discountRate - 0.01);
  const operatingMargin = clamp(controls.operatingMargin + shift * 0.03, 0.03, 0.6);
  const capexPercent = clamp(controls.capexPercent - shift * 0.01, 0.005, 0.18);

  let revenue = defaults.revenue ?? 0;
  let presentValueSum = 0;
  for (let year = 1; year <= defaults.projectionYears; year += 1) {
    revenue *= 1 + revenueGrowth;
    const operatingIncome = revenue * operatingMargin;
    const operatingCashFlow = operatingIncome * defaults.cashConversion;
    const freeCashFlow = operatingCashFlow - revenue * capexPercent;
    const presentValue = freeCashFlow / (1 + discountRate) ** year;
    presentValueSum += presentValue;
  }

  const terminalFreeCashFlow = revenue * operatingMargin * defaults.cashConversion - revenue * capexPercent;
  const terminalValue = (terminalFreeCashFlow * (1 + terminalGrowth)) / Math.max(discountRate - terminalGrowth, 0.01);
  const terminalPresentValue = terminalValue / (1 + discountRate) ** defaults.projectionYears;
  const totalValue = presentValueSum + terminalPresentValue;
  const perShareValue = totalValue / (defaults.sharesOutstanding ?? 1);

  return {
    perShareValue,
    totalValue,
    revenueGrowth,
    discountRate,
    terminalGrowth,
    operatingMargin,
    capexPercent,
  };
}

function buildReverseDcfScenario(defaults: ReverseDcfDefaults, controls: ReverseDcfControls, shift: -1 | 0 | 1): ReverseDcfCase {
  const freeCashFlowMargin = clamp(controls.freeCashFlowMargin + shift * 0.015, -0.08, 0.4);
  const discountRate = clamp(controls.discountRate - shift * 0.01, 0.05, 0.22);
  const terminalGrowth = clamp(controls.terminalGrowth + shift * 0.005, -0.01, discountRate - 0.01);
  const marketCap = (defaults.latestPrice ?? 0) * (defaults.sharesOutstanding ?? 0);
  const startingFreeCashFlow = (defaults.revenue ?? 0) * freeCashFlowMargin;

  return {
    impliedGrowth: solveImpliedGrowth(marketCap, startingFreeCashFlow, discountRate, terminalGrowth),
    freeCashFlowMargin,
    discountRate,
    terminalGrowth,
  };
}

function buildResidualIncomeScenario(
  defaults: ResidualIncomeDefaults,
  controls: ResidualIncomeControls,
  shift: -1 | 0 | 1
): ResidualIncomeCase {
  const averageRoe = clamp(controls.averageRoe + shift * 0.02, -0.08, 0.45);
  const costOfEquity = clamp(controls.costOfEquity - shift * 0.01, 0.05, 0.22);
  const terminalGrowth = clamp(controls.terminalGrowth + shift * 0.004, 0, costOfEquity - 0.01);
  const payoutRatio = clamp(controls.payoutRatio - shift * 0.06, 0, 0.85);
  const retention = 1 - payoutRatio;

  let bookEquityRoll = defaults.bookEquity ?? 0;
  let pvResidualIncome = 0;
  for (let year = 1; year <= PROJECTION_YEARS; year += 1) {
    const fadeFraction = year / PROJECTION_YEARS;
    const roe = averageRoe * (1 - fadeFraction) + costOfEquity * fadeFraction;
    const residualIncome = (roe - costOfEquity) * bookEquityRoll;
    pvResidualIncome += residualIncome / (1 + costOfEquity) ** year;
    bookEquityRoll = bookEquityRoll + roe * bookEquityRoll * retention;
  }

  const terminalResidualIncome = (RESIDUAL_LONG_RUN_ROE - costOfEquity) * bookEquityRoll;
  const terminalValue = terminalResidualIncome / Math.max(costOfEquity - terminalGrowth, 0.01) / (1 + costOfEquity) ** PROJECTION_YEARS;
  const intrinsicValue = (defaults.bookEquity ?? 0) + pvResidualIncome + terminalValue;
  const sharesOutstanding = defaults.sharesOutstanding ?? 1;

  return {
    intrinsicValuePerShare: intrinsicValue / sharesOutstanding,
    bookEquityPerShare: (defaults.bookEquity ?? 0) / sharesOutstanding,
    pvResidualIncomePerShare: pvResidualIncome / sharesOutstanding,
    terminalValuePerShare: terminalValue / sharesOutstanding,
    averageRoe,
    costOfEquity,
    terminalGrowth,
    payoutRatio,
  };
}

function solveImpliedGrowth(targetMarketCap: number, startingFreeCashFlow: number, discountRate: number, terminalGrowth: number): number {
  let low = -0.35;
  let high = 0.55;
  let lowError = reverseDcfError(low, targetMarketCap, startingFreeCashFlow, discountRate, terminalGrowth);
  let highError = reverseDcfError(high, targetMarketCap, startingFreeCashFlow, discountRate, terminalGrowth);

  if (lowError === 0) {
    return low;
  }
  if (highError === 0) {
    return high;
  }

  if (lowError * highError > 0) {
    let bestGrowth = low;
    let bestResidual = Math.abs(lowError);
    for (let index = 1; index <= 80; index += 1) {
      const candidate = low + (high - low) * (index / 80);
      const residual = Math.abs(reverseDcfError(candidate, targetMarketCap, startingFreeCashFlow, discountRate, terminalGrowth));
      if (residual < bestResidual) {
        bestGrowth = candidate;
        bestResidual = residual;
      }
    }
    return bestGrowth;
  }

  for (let iteration = 0; iteration < 100; iteration += 1) {
    const mid = (low + high) / 2;
    const midError = reverseDcfError(mid, targetMarketCap, startingFreeCashFlow, discountRate, terminalGrowth);
    if (Math.abs(midError) <= Math.max(targetMarketCap * 1e-6, 1e-6)) {
      return mid;
    }
    if (lowError * midError <= 0) {
      high = mid;
      highError = midError;
    } else {
      low = mid;
      lowError = midError;
    }
  }

  return (low + high) / 2;
}

function reverseDcfError(
  growth: number,
  targetMarketCap: number,
  startingFreeCashFlow: number,
  discountRate: number,
  terminalGrowth: number
): number {
  return reverseDcfEquityValue(growth, startingFreeCashFlow, discountRate, terminalGrowth) - targetMarketCap;
}

function reverseDcfEquityValue(growth: number, startingFreeCashFlow: number, discountRate: number, terminalGrowth: number): number {
  let projectedFreeCashFlow = startingFreeCashFlow;
  let presentValue = 0;
  for (let year = 1; year <= PROJECTION_YEARS; year += 1) {
    const taperFactor = year / PROJECTION_YEARS;
    const yearGrowth = growth + (terminalGrowth - growth) * taperFactor;
    projectedFreeCashFlow *= 1 + yearGrowth;
    presentValue += projectedFreeCashFlow / (1 + discountRate) ** year;
  }
  const terminalCashFlow = projectedFreeCashFlow * (1 + terminalGrowth);
  const terminalValue = terminalCashFlow / Math.max(discountRate - terminalGrowth, 0.01);
  return presentValue + terminalValue / (1 + discountRate) ** PROJECTION_YEARS;
}

function computeOverlapRange(rows: RangeRow[]): { low: number; high: number; base: number } | null {
  if (!rows.length) {
    return null;
  }
  const low = Math.max(...rows.map((row) => row.low));
  const high = Math.min(...rows.map((row) => row.high));
  if (low > high) {
    return null;
  }
  return { low, high, base: (low + high) / 2 };
}

function minRowBase(rows: RangeRow[]): number | null {
  if (!rows.length) {
    return null;
  }
  return Math.min(...rows.map((row) => row.base));
}

function maxRowBase(rows: RangeRow[]): number | null {
  if (!rows.length) {
    return null;
  }
  return Math.max(...rows.map((row) => row.base));
}

function modelStatus(result: unknown): string {
  const record = asRecord(result);
  return String(record.model_status ?? record.status ?? "supported");
}

function scenarioReason(result: Record<string, unknown>): string {
  return String(
    result.reason ?? result.explanation ?? "This scenario needs a cached model result plus the latest SEC-backed financial inputs."
  );
}

function statusLabel(status: string): string {
  if (status === "supported") {
    return "Supported";
  }
  if (status === "partial") {
    return "Partial";
  }
  if (status === "proxy") {
    return "Proxy";
  }
  if (status === "insufficient_data") {
    return "Insufficient data";
  }
  if (status === "unsupported") {
    return "Unsupported";
  }
  return titleCase(status || "unknown");
}

function formatConfidence(value: unknown): string {
  const score = asNumber(value);
  return score === null ? "—" : `${(score * 100).toFixed(0)}%`;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asObjectArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((entry): entry is Record<string, unknown> => Boolean(entry) && typeof entry === "object" && !Array.isArray(entry))
    : [];
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((entry): entry is string => typeof entry === "string" && Boolean(entry)) : [];
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function deriveSharesOutstanding(statement: FinancialPayload | null): number | null {
  if (!statement) {
    return null;
  }
  if (statement.shares_outstanding !== null && statement.shares_outstanding > 0) {
    return statement.shares_outstanding;
  }
  if (statement.weighted_average_diluted_shares !== null && statement.weighted_average_diluted_shares > 0) {
    return statement.weighted_average_diluted_shares;
  }
  if (statement.net_income !== null && statement.eps !== null && statement.eps !== 0) {
    const derivedShares = statement.net_income / statement.eps;
    return derivedShares > 0 ? derivedShares : null;
  }
  return null;
}

function safeDivide(numerator: number | null | undefined, denominator: number | null | undefined): number | null {
  if (numerator === null || numerator === undefined || denominator === null || denominator === undefined || denominator === 0) {
    return null;
  }
  return numerator / denominator;
}

function growthRate(current: number | null | undefined, previous: number | null | undefined): number | null {
  if (current === null || current === undefined || previous === null || previous === undefined || previous === 0) {
    return null;
  }
  return (current - previous) / Math.abs(previous);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: Math.abs(value) >= 100 ? 0 : 2,
  }).format(value);
}
