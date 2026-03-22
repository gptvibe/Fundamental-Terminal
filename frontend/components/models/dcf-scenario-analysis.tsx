"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { CHART_AXIS_COLOR, CHART_GRID_COLOR, chartTick } from "@/lib/chart-theme";
import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import type { FinancialPayload, ModelPayload, PriceHistoryPoint } from "@/lib/types";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);
const CASE_COLORS = {
  bear: "#FF6B6B",
  base: "#00E5FF",
  bull: "#00FF41"
} as const;

type ScenarioControls = {
  revenueGrowth: number;
  discountRate: number;
  terminalGrowth: number;
  operatingMargin: number;
  capexPercent: number;
};

interface DcfScenarioAnalysisProps {
  ticker: string;
  dcfModel: ModelPayload | null;
  financials: FinancialPayload[];
  priceHistory: PriceHistoryPoint[];
}

export function DcfScenarioAnalysis({ ticker, dcfModel, financials, priceHistory }: DcfScenarioAnalysisProps) {
  const annualFinancials = useMemo(
    () => financials.filter((statement) => ANNUAL_FORMS.has(statement.filing_type)),
    [financials]
  );
  const latestAnnual = annualFinancials[0] ?? financials[0] ?? null;
  const previousAnnual = annualFinancials[1] ?? financials[1] ?? null;
  const latestPrice = priceHistory.at(-1)?.close ?? null;

  const defaults = useMemo(() => {
    const dcfResult = asRecord(dcfModel?.result);
    const assumptions = asRecord(dcfResult.assumptions);
    const revenueGrowthDefault = growthRate(latestAnnual?.revenue ?? null, previousAnnual?.revenue ?? null) ?? 0.05;
    const discountRateDefault = safeNumber(assumptions.discount_rate) ?? 0.1;
    const terminalGrowthDefault = safeNumber(assumptions.terminal_growth_rate) ?? 0.025;
    const terminalGrowthCap = Math.max(discountRateDefault - 0.01, 0);
    const operatingMarginDefault = safeDivide(latestAnnual?.operating_income ?? null, latestAnnual?.revenue ?? null) ?? 0.18;
    const capexPercentDefault =
      safeDivide(
        latestAnnual && latestAnnual.operating_cash_flow !== null && latestAnnual.free_cash_flow !== null
          ? Math.abs(latestAnnual.operating_cash_flow - latestAnnual.free_cash_flow)
          : null,
        latestAnnual?.revenue ?? null
      ) ?? 0.05;

    return {
      revenueGrowth: clamp(revenueGrowthDefault, -0.05, 0.25),
      discountRate: clamp(discountRateDefault, 0.05, 0.18),
      terminalGrowth: clamp(terminalGrowthDefault, 0.0, Math.min(0.06, terminalGrowthCap)),
      operatingMargin: clamp(operatingMarginDefault, 0.05, 0.5),
      capexPercent: clamp(capexPercentDefault, 0.01, 0.15),
      projectionYears: safeNumber(assumptions.projection_years) ?? 5,
      cashConversion:
        clamp(safeDivide(latestAnnual?.operating_cash_flow ?? null, latestAnnual?.operating_income ?? null) ?? 0.9, 0.35, 2.2),
      revenue: latestAnnual?.revenue ?? null,
      sharesOutstanding: deriveSharesOutstanding(latestAnnual),
      periodEnd: latestAnnual?.period_end ?? null,
      resetKey: [
        ticker,
        latestAnnual?.period_end ?? "none",
        latestPrice ?? "none",
        latestAnnual?.revenue ?? "none",
        previousAnnual?.revenue ?? "none",
        safeNumber(assumptions.discount_rate) ?? "none"
      ].join(":")
    };
  }, [dcfModel, latestAnnual, latestPrice, previousAnnual, ticker]);

  const [controls, setControls] = useState<ScenarioControls>({
    revenueGrowth: defaults.revenueGrowth,
    discountRate: defaults.discountRate,
    terminalGrowth: Math.min(defaults.terminalGrowth, defaults.discountRate - 0.01),
    operatingMargin: defaults.operatingMargin,
    capexPercent: defaults.capexPercent
  });

  useEffect(() => {
    setControls({
      revenueGrowth: defaults.revenueGrowth,
      discountRate: defaults.discountRate,
      terminalGrowth: Math.min(defaults.terminalGrowth, defaults.discountRate - 0.01),
      operatingMargin: defaults.operatingMargin,
      capexPercent: defaults.capexPercent
    });
  }, [defaults]);

  const scenario = useMemo(() => {
    if (defaults.revenue === null || defaults.sharesOutstanding === null) {
      return null;
    }

    const cases = {
      bear: buildDcfScenario(defaults, controls, -1),
      base: buildDcfScenario(defaults, controls, 0),
      bull: buildDcfScenario(defaults, controls, 1)
    };

    const fanSeries = buildFanSeries(cases, defaults.projectionYears);
    const comparisonSeries = [
      { label: "Bear", value: cases.bear.perShareValue, fill: CASE_COLORS.bear },
      { label: "Base", value: cases.base.perShareValue, fill: CASE_COLORS.base },
      { label: "Bull", value: cases.bull.perShareValue, fill: CASE_COLORS.bull }
    ];

    const marginOfSafety =
      latestPrice === null || cases.base.perShareValue <= 0
        ? null
        : safeDivide(cases.base.perShareValue - latestPrice, cases.base.perShareValue);
    return {
      cases,
      fanSeries,
      comparisonSeries,
      marginOfSafety,
      valuationRange: [cases.bear.perShareValue, cases.bull.perShareValue] as const
    };
  }, [controls, defaults, latestPrice]);

  const dcfStatus = typeof dcfModel?.result?.model_status === "string" ? dcfModel.result.model_status : dcfModel?.result?.status;

  if (!dcfModel || !latestAnnual || !scenario) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 260 }}>
        <div className="grid-empty-kicker">Scenario engine</div>
        <div className="grid-empty-title">DCF scenario analysis unavailable</div>
        <div className="grid-empty-copy">Warm the DCF model and cached annual financials first, then this panel turns interactive.</div>
      </div>
    );
  }

  return (
    <div className="dcf-scenario-shell">
      {dcfStatus === "partial" || dcfStatus === "proxy" ? (
        <div className="text-muted" style={{ marginBottom: 10 }}>
          {dcfStatus === "partial"
            ? "Partial inputs: This model used incomplete financial inputs; results are directional only."
            : "Proxy output: This model used approximation logic where direct inputs were unavailable."}
        </div>
      ) : null}
      <div className="dcf-scenario-grid">
        <div className="dcf-control-panel">
          <div className="dcf-control-header">
            <div className="dcf-section-title">Scenario Inputs</div>
            <div className="dcf-section-subtitle">Slide assumptions and the valuation range updates instantly.</div>
          </div>

          <div className="dcf-control-list">
            <SliderControl
              label="Revenue Growth"
              value={controls.revenueGrowth}
              min={-0.05}
              max={0.25}
              step={0.005}
              accent="#00E5FF"
              onChange={(value) => setControls((current) => ({ ...current, revenueGrowth: value }))}
            />
            <SliderControl
              label="Discount Rate"
              value={controls.discountRate}
              min={0.05}
              max={0.18}
              step={0.0025}
              accent="#FF6B6B"
              onChange={(value) =>
                setControls((current) => ({
                  ...current,
                  discountRate: value,
                  terminalGrowth: Math.min(current.terminalGrowth, value - 0.01)
                }))
              }
            />
            <SliderControl
              label="Terminal Growth"
              value={controls.terminalGrowth}
              min={0}
              max={Math.min(0.06, Math.max(controls.discountRate - 0.01, 0))}
              step={0.0025}
              accent="#FFD700"
              onChange={(value) => setControls((current) => ({ ...current, terminalGrowth: Math.min(value, current.discountRate - 0.01) }))}
            />
            <SliderControl
              label="Operating Margin"
              value={controls.operatingMargin}
              min={0.05}
              max={0.5}
              step={0.005}
              accent="#00FF41"
              onChange={(value) => setControls((current) => ({ ...current, operatingMargin: value }))}
            />
            <SliderControl
              label="Capex %"
              value={controls.capexPercent}
              min={0.01}
              max={0.15}
              step={0.0025}
              accent="#A855F7"
              onChange={(value) => setControls((current) => ({ ...current, capexPercent: value }))}
            />
          </div>

          <div className="dcf-control-meta">
            <span className="pill">Current Price {formatCurrency(latestPrice)}</span>
            <span className="pill">Base Period {formatDate(defaults.periodEnd)}</span>
          </div>
        </div>

        <div className="dcf-visual-panel">
          <div className="dcf-chart-card">
            <div className="dcf-section-title">Valuation Fan</div>
            <div className="dcf-section-subtitle">
              Bear/base/bull cumulative intrinsic value per share through the forecast horizon and terminal value.
            </div>
            <div className="dcf-chart-shell dcf-chart-large">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={scenario.fanSeries} margin={{ top: 12, right: 20, left: 4, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_COLOR} />
                  <XAxis dataKey="label" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
                  <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={formatAxisCurrency} width={64} />
                  <Tooltip content={<FanTooltip />} />
                  <Area type="monotone" dataKey="lower" stackId="fan" stroke="transparent" fill="transparent" />
                  <Area type="monotone" dataKey="range" stackId="fan" stroke="transparent" fill="rgba(0,229,255,0.18)" />
                  <Area type="monotone" dataKey="base" stroke={CASE_COLORS.base} fill="rgba(0,229,255,0.08)" strokeWidth={2.6} />
                  <Area type="monotone" dataKey="bull" stroke={CASE_COLORS.bull} fill="rgba(0,255,65,0.04)" strokeWidth={2} />
                  <Area type="monotone" dataKey="bear" stroke={CASE_COLORS.bear} fill="rgba(255,107,107,0.04)" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="dcf-chart-card">
            <div className="dcf-section-title">Intrinsic Value vs Current Price</div>
            <div className="dcf-section-subtitle">Per-share value range against the latest cached close.</div>
            <div className="dcf-chart-shell dcf-chart-small">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={scenario.comparisonSeries} margin={{ top: 8, right: 18, left: 4, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_COLOR} vertical={false} />
                  <XAxis dataKey="label" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
                  <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={formatAxisCurrency} width={64} />
                  {latestPrice !== null ? (
                    <ReferenceLine y={latestPrice} stroke="#FFD700" strokeDasharray="6 6" label={{ value: `Price ${formatCurrency(latestPrice)}`, fill: "#FFD700", position: "insideTopRight" }} />
                  ) : null}
                  <Tooltip content={<ValueTooltip currentPrice={latestPrice} />} />
                  <Bar dataKey="value" radius={[10, 10, 0, 0]}>
                    {scenario.comparisonSeries.map((entry) => (
                      <Cell key={entry.label} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>

      <div className="dcf-summary-strip">
        <SummaryCard label="Bear Case" value={formatCurrency(scenario.cases.bear.perShareValue)} accent="bear" />
        <SummaryCard label="Base Case" value={formatCurrency(scenario.cases.base.perShareValue)} accent="base" />
        <SummaryCard label="Bull Case" value={formatCurrency(scenario.cases.bull.perShareValue)} accent="bull" />
        <SummaryCard label="Margin of Safety" value={formatPercent(scenario.marginOfSafety)} accent="gold" />
        <SummaryCard
          label="Valuation Range"
          value={`${formatCurrency(scenario.valuationRange[0])} - ${formatCurrency(scenario.valuationRange[1])}`}
          accent="cyan"
        />
      </div>
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
  onChange
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

function SummaryCard({ label, value, accent }: { label: string; value: string; accent: "bear" | "base" | "bull" | "gold" | "cyan" }) {
  return (
    <div className={`dcf-summary-card accent-${accent}`}>
      <div className="dcf-summary-label">{label}</div>
      <div className="dcf-summary-value">{value}</div>
    </div>
  );
}

function FanTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ dataKey?: string; value?: number }>; label?: string }) {
  if (!active || !payload?.length) {
    return null;
  }

  const values = Object.fromEntries(payload.map((entry) => [entry.dataKey ?? "", safeNumber(entry.value)]));
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{label}</div>
      <TooltipRow label="Bear" value={formatCurrency(values.bear)} color={CASE_COLORS.bear} />
      <TooltipRow label="Base" value={formatCurrency(values.base)} color={CASE_COLORS.base} />
      <TooltipRow label="Bull" value={formatCurrency(values.bull)} color={CASE_COLORS.bull} />
    </div>
  );
}

function ValueTooltip({
  active,
  payload,
  label,
  currentPrice
}: {
  active?: boolean;
  payload?: Array<{ value?: number; payload?: { label?: string } }>;
  label?: string;
  currentPrice: number | null;
}) {
  if (!active || !payload?.length) {
    return null;
  }

  const intrinsicValue = safeNumber(payload[0]?.value);
  const upside = currentPrice === null || intrinsicValue === null ? null : safeDivide(intrinsicValue - currentPrice, currentPrice);
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{label ?? payload[0]?.payload?.label ?? "Scenario"}</div>
      <TooltipRow label="Intrinsic Value" value={formatCurrency(intrinsicValue)} color={CASE_COLORS.base} />
      <TooltipRow label="Current Price" value={formatCurrency(currentPrice)} color="#FFD700" />
      <TooltipRow label="Upside / Downside" value={formatPercent(upside)} color="#00FF41" />
    </div>
  );
}

function TooltipRow({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="chart-tooltip-row">
      <span className="chart-tooltip-key">
        <span className="chart-tooltip-dot" style={{ background: color }} />
        {label}
      </span>
      <span className="chart-tooltip-value">{value}</span>
    </div>
  );
}

function buildDcfScenario(
  defaults: {
    projectionYears: number;
    revenue: number | null;
    sharesOutstanding: number | null;
    cashConversion: number;
  },
  controls: ScenarioControls,
  shift: -1 | 0 | 1
) {
  const revenueGrowth = clamp(controls.revenueGrowth + shift * 0.025, -0.08, 0.3);
  const discountRate = clamp(controls.discountRate - shift * 0.0125, 0.05, 0.2);
  const terminalGrowth = clamp(controls.terminalGrowth + shift * 0.006, -0.01, discountRate - 0.01);
  const operatingMargin = clamp(controls.operatingMargin + shift * 0.03, 0.03, 0.6);
  const capexPercent = clamp(controls.capexPercent - shift * 0.01, 0.005, 0.18);

  let revenue = defaults.revenue ?? 0;
  const cumulativePerShare: Array<{ year: number; value: number }> = [];
  let presentValueSum = 0;
  for (let year = 1; year <= defaults.projectionYears; year += 1) {
    revenue *= 1 + revenueGrowth;
    const operatingIncome = revenue * operatingMargin;
    const operatingCashFlow = operatingIncome * defaults.cashConversion;
    const freeCashFlow = operatingCashFlow - revenue * capexPercent;
    const presentValue = freeCashFlow / (1 + discountRate) ** year;
    presentValueSum += presentValue;
    cumulativePerShare.push({ year, value: presentValueSum / (defaults.sharesOutstanding ?? 1) });
  }

  const terminalFreeCashFlow = revenue * operatingMargin * defaults.cashConversion - revenue * capexPercent;
  const terminalValue = (terminalFreeCashFlow * (1 + terminalGrowth)) / Math.max(discountRate - terminalGrowth, 0.01);
  const terminalPresentValue = terminalValue / (1 + discountRate) ** defaults.projectionYears;
  const totalValue = presentValueSum + terminalPresentValue;
  const perShareValue = totalValue / (defaults.sharesOutstanding ?? 1);

  return {
    revenueGrowth,
    discountRate,
    terminalGrowth,
    operatingMargin,
    capexPercent,
    totalValue,
    perShareValue,
    cumulativePerShare: [
      ...cumulativePerShare,
      { year: defaults.projectionYears + 1, value: perShareValue }
    ]
  };
}

function buildFanSeries(
  cases: Record<"bear" | "base" | "bull", ReturnType<typeof buildDcfScenario>>,
  projectionYears: number
) {
  const labels = ["Now", ...Array.from({ length: projectionYears }, (_, index) => `Y${index + 1}`), "Terminal"];
  return labels.map((label, index) => {
    const bear = index === 0 ? 0 : cases.bear.cumulativePerShare[index - 1]?.value ?? cases.bear.perShareValue;
    const base = index === 0 ? 0 : cases.base.cumulativePerShare[index - 1]?.value ?? cases.base.perShareValue;
    const bull = index === 0 ? 0 : cases.bull.cumulativePerShare[index - 1]?.value ?? cases.bull.perShareValue;
    const lower = Math.min(bear, bull);
    const upper = Math.max(bear, bull);

    return {
      label,
      bear,
      base,
      bull,
      lower,
      range: upper - lower
    };
  });
}

function deriveSharesOutstanding(statement: FinancialPayload | null): number | null {
  if (!statement) {
    return null;
  }

  if (statement.shares_outstanding !== null && statement.shares_outstanding > 0) {
    return statement.shares_outstanding;
  }

  const derivedShares = safeDivide(statement.net_income, statement.eps);
  if (derivedShares === null || derivedShares <= 0) {
    return null;
  }

  return derivedShares;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function safeNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
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
    maximumFractionDigits: value >= 100 ? 0 : 2
  }).format(value);
}

function formatAxisCurrency(value: number): string {
  return `$${value.toFixed(0)}`;
}
