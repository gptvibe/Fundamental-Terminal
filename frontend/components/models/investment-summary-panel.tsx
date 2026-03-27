"use client";

import { useMemo } from "react";
import { PolarAngleAxis, RadialBar, RadialBarChart, ResponsiveContainer } from "recharts";

import { formatPercent } from "@/lib/format";
import { formatPiotroskiDisplay as formatResolvedPiotroskiDisplay, resolvePiotroskiScoreState } from "@/lib/piotroski";
import type { FinancialPayload, ModelPayload, PriceHistoryPoint } from "@/lib/types";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);

interface InvestmentSummaryPanelProps {
  ticker: string;
  models: ModelPayload[];
  financials: FinancialPayload[];
  priceHistory: PriceHistoryPoint[];
  strictOfficialMode?: boolean;
}

export function InvestmentSummaryPanel({ ticker, models, financials, priceHistory, strictOfficialMode = false }: InvestmentSummaryPanelProps) {
  const summary = useMemo(() => buildInvestmentSummary(models, financials, priceHistory), [models, financials, priceHistory]);

  if (summary === null) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 260 }}>
        <div className="grid-empty-kicker">Investment view</div>
        <div className="grid-empty-title">Investment summary unavailable</div>
        <div className="grid-empty-copy">
          {strictOfficialMode
            ? "Strict official mode disables commercial equity price inputs. Cached fair value and market-price comparison cards stay limited until an official end-of-day price source is configured."
            : "Warm the cached DCF model, annual financials, and price series to unlock the summary panel."}
        </div>
      </div>
    );
  }

  return (
    <div className="investment-summary-shell">
      {strictOfficialMode ? (
        <div className="text-muted" style={{ marginBottom: 12 }}>
          Strict official mode disables commercial equity price inputs. Latest price, fair value gap, and market-price comparison notes remain unavailable unless an official closing-price source is enabled.
        </div>
      ) : null}
      <div className="investment-summary-cards">
        <SummaryCard label="DCF Fair Value / Share" value={formatCurrency(summary.fairValuePerShare)} accent="cyan" detail={summary.fairValueBasis} />
        <SummaryCard label="Latest Price" value={formatCurrency(summary.latestPrice)} accent="gold" detail={summary.priceDateLabel} />
        <SummaryCard label="Fair Value Gap" value={formatPercent(summary.marginOfSafety)} accent={summary.marginOfSafety != null && summary.marginOfSafety >= 0 ? "green" : "red"} detail={summary.marginBand} />
        <SummaryCard label="Net Debt" value={formatCurrency(summary.netDebt)} accent="red" detail={summary.netDebtLabel} />
      </div>

      <div className="investment-summary-gauges">
        {summary.gauges.map((gauge) => (
          <GaugeCard key={gauge.label} label={gauge.label} score={gauge.score} detail={gauge.detail} />
        ))}
      </div>

      <div className="investment-summary-notes">
        {summary.notes.map((note) => (
          <div key={note.title} className="investment-summary-note">
            <div className="investment-summary-note-title">{note.title}</div>
            <div className="investment-summary-note-copy">{note.copy}</div>
          </div>
        ))}
      </div>

      <div className="investment-summary-inputs">
        <span className="pill">{ticker} summary</span>
        <span className="pill">DCF state {summary.valuationStateLabel}</span>
        <span className="pill">Piotroski {summary.piotroskiDisplay}</span>
        <span className="pill">Altman Proxy {formatSigned(summary.altmanZScore)}</span>
        <span className="pill">Revenue Growth {formatPercent(summary.revenueGrowth)}</span>
        <span className="pill">Net Margin {formatPercent(summary.netMargin)}</span>
        <span className="pill">Debt / Equity {formatSigned(summary.debtToEquity)}</span>
      </div>
    </div>
  );
}

function GaugeCard({ label, score, detail }: { label: string; score: number; detail: string }) {
  const clampedScore = clamp(score, 0, 10);
  const color = gaugeColor(clampedScore);
  const chartData = [{ value: clampedScore, fill: color }];

  return (
    <div className="investment-gauge-card">
      <div className="investment-gauge-title">{label}</div>
      <div className="investment-gauge-shell">
        <ResponsiveContainer width="100%" height="100%">
          <RadialBarChart data={chartData} innerRadius="72%" outerRadius="100%" startAngle={90} endAngle={-270} barSize={14}>
            <PolarAngleAxis type="number" domain={[0, 10]} tick={false} axisLine={false} />
            <RadialBar dataKey="value" background={{ fill: "var(--panel-border)" }} cornerRadius={12} />
          </RadialBarChart>
        </ResponsiveContainer>
        <div className="investment-gauge-center">
          <div className="investment-gauge-value" style={{ color }}>{clampedScore.toFixed(1)}</div>
          <div className="investment-gauge-scale">/ 10</div>
        </div>
      </div>
      <div className="investment-gauge-detail">{detail}</div>
    </div>
  );
}

function SummaryCard({
  label,
  value,
  accent,
  detail
}: {
  label: string;
  value: string;
  accent: "green" | "cyan" | "gold" | "red";
  detail: string;
}) {
  return (
    <div className={`investment-summary-card accent-${accent}`}>
      <div className="investment-summary-card-label">{label}</div>
      <div className="investment-summary-card-value">{value}</div>
      <div className="investment-summary-card-detail">{detail}</div>
    </div>
  );
}

function buildInvestmentSummary(models: ModelPayload[], financials: FinancialPayload[], priceHistory: PriceHistoryPoint[]) {
  const annualFinancials = financials.filter((statement) => ANNUAL_FORMS.has(statement.filing_type));
  const current = annualFinancials[0] ?? financials[0] ?? null;
  const previous = annualFinancials[1] ?? financials[1] ?? null;
  const latestPrice = priceHistory.at(-1) ?? null;
  if (!current && models.length === 0 && !latestPrice) {
    return null;
  }

  const byName = Object.fromEntries(models.map((model) => [model.model_name, model])) as Record<string, ModelPayload | undefined>;
  const dcf = asRecord(byName.dcf?.result);
  const ratios = asRecord(byName.ratios?.result);
  const ratioValues = asRecord(ratios.values);
  const dupont = asRecord(byName.dupont?.result);
  const piotroski = asRecord(byName.piotroski?.result);
  const altman = asRecord(byName.altman_z?.result);
  const piotroskiState = resolvePiotroskiScoreState(piotroski);

  const valuationState = normalizeModelState(dcf.model_status ?? dcf.status);
  const fairValuePerShare = safeNumber(dcf.fair_value_per_share);
  const netDebt = safeNumber(dcf.net_debt);
  const currentPrice = latestPrice?.close ?? null;
  const marginOfSafety =
    fairValuePerShare !== null && currentPrice !== null && currentPrice > 0 ? (fairValuePerShare - currentPrice) / currentPrice : null;

  const piotroskiScore = piotroskiState.score;
  const piotroskiDisplay = formatResolvedPiotroskiDisplay(piotroskiState);
  const altmanZScore = safeNumber(altman.z_score_approximate) ?? fallbackAltman(current);
  const altmanApproximate = altmanZScore !== null && (safeNumber(altman.z_score_approximate) === null || isApproximateAltman(altman));
  const revenueGrowth = safeNumber(ratioValues.revenue_growth) ?? growthRate(current?.revenue ?? null, previous?.revenue ?? null);
  const netMargin =
    safeNumber(dupont.net_profit_margin) ??
    safeNumber(ratioValues.net_margin) ??
    safeDivide(current?.net_income ?? null, current?.revenue ?? null);
  const debtToEquity =
    computeDebtToEquity(current) ??
    deriveDebtToEquityFromRatios(safeNumber(ratioValues.liabilities_to_assets), safeNumber(ratioValues.equity_ratio));

  const valuationRating = marginOfSafety !== null ? clamp(scaleRange(marginOfSafety, -0.2, 0.35) ?? 0, 0, 10) : 0;
  const financialStrengthRating = averageScore([
    scaleToTen(piotroskiScore, piotroskiState.scoreMax),
    altmanApproximate ? null : altmanToTen(altmanZScore),
    inverseRangeToTen(debtToEquity, 0.3, 2.5)
  ]);
  const growthRating = averageScore([
    scaleRange(revenueGrowth, -0.05, 0.2),
    scaleRange(netMargin, 0.02, 0.25)
  ]);
  const overallQualityScore = averageScore([
    valuationRating,
    financialStrengthRating,
    growthRating
  ]);

  return {
    fairValuePerShare,
    latestPrice: currentPrice,
    netDebt,
    valuationState,
    valuationStateLabel: formatModelState(valuationState),
    marginOfSafety,
    valuationRating,
    financialStrengthRating,
    growthRating,
    overallQualityScore,
    piotroskiScore,
    piotroskiDisplay,
    altmanZScore,
    revenueGrowth,
    netMargin,
    debtToEquity,
    fairValueBasis: fairValuePerShare !== null ? "Derived from cached DCF equity value per share." : "Awaiting DCF fair value per share",
    priceDateLabel: latestPrice?.date ? `Latest close ${new Intl.DateTimeFormat("en-US", { month: "short", day: "2-digit", year: "numeric" }).format(new Date(latestPrice.date))}` : "Awaiting cached market price",
    netDebtLabel: netDebt === null ? "Net debt unavailable" : "From latest cached DCF run",
    marginBand: valuationBandLabel(marginOfSafety),
    valuationLabel: valuationRatingLabel(valuationRating),
    gauges: [
      {
        label: "Valuation",
        score: valuationRating,
        detail: `${valuationRatingLabel(valuationRating)} · Gap ${formatPercent(marginOfSafety)}`
      },
      {
        label: "Financial Strength",
        score: financialStrengthRating,
        detail: `Piotroski ${piotroskiDisplay} · Altman proxy ${formatSigned(altmanZScore)}`
      },
      {
        label: "Growth",
        score: growthRating,
        detail: `Revenue ${formatPercent(revenueGrowth)} · Margin ${formatPercent(netMargin)}`
      },
      {
        label: "Overall Quality",
        score: overallQualityScore,
        detail: overallQualityLabel(overallQualityScore)
      }
    ],
    notes: [
      {
        title: "Valuation View",
        copy: buildValuationSummary(marginOfSafety, fairValuePerShare, currentPrice, valuationState)
      },
      {
        title: "Financial Strength",
        copy: buildStrengthSummary(piotroskiScore, altmanZScore, debtToEquity, altmanApproximate, piotroskiState.isPartial)
      },
      {
        title: "Growth & Profitability",
        copy: buildGrowthSummary(revenueGrowth, netMargin)
      },
      {
        title: "Bottom Line",
        copy: buildOverallSummary(overallQualityScore, valuationRating, financialStrengthRating, growthRating)
      }
    ]
  };
}

function buildValuationSummary(
  marginOfSafety: number | null,
  fairValuePerShare: number | null,
  latestPrice: number | null,
  valuationState: string
) {
  if (valuationState === "unsupported") {
    return "DCF valuation is unsupported for this company classification, so fair-value gap is intentionally withheld.";
  }
  if (valuationState === "insufficient_data") {
    return "DCF valuation is currently insufficient due to missing core inputs; refresh or new filings are required before a fair-value call.";
  }
  if (marginOfSafety === null || fairValuePerShare === null || latestPrice === null) {
    return "DCF fair value per share or latest price is incomplete, so the valuation signal remains provisional until both are cached.";
  }
  if (marginOfSafety >= 0.25) {
    return "DCF fair value per share sits materially above the latest cached price, suggesting a healthy valuation cushion.";
  }
  if (marginOfSafety >= 0.08) {
    return "Latest price screens modestly below DCF fair value per share, suggesting some upside but not a deep discount.";
  }
  if (marginOfSafety >= -0.08) {
    return "Latest price sits roughly in line with DCF fair value per share, so valuation looks balanced rather than obviously cheap.";
  }
  return "Latest price sits above DCF fair value per share, which points to a thinner safety cushion and a richer valuation setup.";
}

function normalizeModelState(value: unknown): "ok" | "partial" | "proxy" | "insufficient_data" | "unsupported" | "unknown" {
  if (value === "ok" || value === "partial" || value === "proxy" || value === "insufficient_data" || value === "unsupported") {
    return value;
  }
  return "unknown";
}

function formatModelState(state: "ok" | "partial" | "proxy" | "insufficient_data" | "unsupported" | "unknown"): string {
  if (state === "insufficient_data") {
    return "insufficient_data";
  }
  return state;
}

function buildStrengthSummary(
  piotroskiScore: number | null,
  altmanZScore: number | null,
  debtToEquity: number | null,
  altmanApproximate: boolean,
  piotroskiPartial: boolean
) {
  const piotroskiText = piotroskiPartial
    ? "Piotroski is partial and excluded from the scorecard"
    : piotroskiScore === null
      ? "Piotroski is unavailable"
      : `Piotroski is ${piotroskiScore.toFixed(1)}/9`;
  const altmanText =
    altmanZScore === null
      ? "Altman proxy is unavailable"
      : altmanApproximate
        ? `Altman proxy is ${altmanZScore.toFixed(2)}`
        : `Altman Z is ${altmanZScore.toFixed(2)}`;
  const debtText = debtToEquity === null ? "debt/equity is unavailable" : `debt/equity is ${debtToEquity.toFixed(2)}`;
  const strongPiotroski = piotroskiPartial || (piotroskiScore ?? 0) >= 7;
  const weakPiotroski = !piotroskiPartial && (piotroskiScore ?? 0) < 4;

  if (strongPiotroski && (debtToEquity ?? 99) <= 1 && (altmanApproximate || (altmanZScore ?? 0) >= 3)) {
    return `${piotroskiText}, ${altmanText}, and ${debtText}, which together point to a strong balance-sheet and operating quality profile${altmanApproximate ? ", while treating the Altman reading as contextual rather than threshold-based" : ""}.`;
  }
  if (weakPiotroski || (debtToEquity ?? 0) > 2.2 || (!altmanApproximate && (altmanZScore ?? 99) < 1.8)) {
    return `${piotroskiText}, ${altmanText}, and ${debtText}, which flags weaker financial resilience and higher balance-sheet risk${altmanApproximate ? "; the Altman value is shown as a partial proxy only" : ""}.`;
  }
  return `${piotroskiText}, ${altmanText}, and ${debtText}, suggesting a workable but not pristine financial strength profile${altmanApproximate ? ", with the Altman proxy included for context rather than a hard cutoff" : ""}.`;
}

function buildGrowthSummary(revenueGrowth: number | null, netMargin: number | null) {
  if (revenueGrowth === null && netMargin === null) {
    return "Growth and profitability inputs are still incomplete, so the expansion outlook remains tentative.";
  }
  if ((revenueGrowth ?? 0) >= 0.12 && (netMargin ?? 0) >= 0.12) {
    return `Revenue growth and net margin both point to a strong compounding profile, with scale translating into healthy profitability.`;
  }
  if ((revenueGrowth ?? 0) < 0 || (netMargin ?? 0) < 0.05) {
    return `The operating picture looks softer, with either slowing top-line momentum or thinner net margins holding back the growth case.`;
  }
  return `Growth is positive but measured, and profitability suggests a middle-ground quality profile rather than breakout expansion.`;
}

function buildOverallSummary(overall: number, valuation: number, strength: number, growth: number) {
  const strongest = [
    { label: "valuation", score: valuation },
    { label: "financial strength", score: strength },
    { label: "growth", score: growth }
  ].sort((left, right) => right.score - left.score)[0];

  if (overall >= 7.5) {
    return `Overall quality scores ${overall.toFixed(1)}/10, led by ${strongest.label}. This reads like a high-conviction setup if the operating thesis holds.`;
  }
  if (overall >= 5) {
    return `Overall quality scores ${overall.toFixed(1)}/10. The setup is mixed, with some support from ${strongest.label} but not enough to remove all debate.`;
  }
  return `Overall quality scores ${overall.toFixed(1)}/10, which leans speculative. The weakest areas still outweigh the strongest part of the thesis.`;
}

function ratingAccent(score: number) {
  if (score < 4) {
    return "red" as const;
  }
  if (score < 7) {
    return "gold" as const;
  }
  return "green" as const;
}

function valuationBandLabel(marginOfSafety: number | null) {
  if (marginOfSafety === null) {
    return "Awaiting margin signal";
  }
  if (marginOfSafety >= 0.25) {
    return "Deep discount";
  }
  if (marginOfSafety >= 0.08) {
    return "Discount to fair value";
  }
  if (marginOfSafety >= -0.08) {
    return "Near fair value";
  }
  return "Premium to fair value";
}

function valuationRatingLabel(score: number) {
  if (score < 4) {
    return "Rich / expensive";
  }
  if (score < 7) {
    return "Fairly valued";
  }
  return "Attractive";
}

function overallQualityLabel(score: number) {
  if (score < 4) {
    return "Low conviction";
  }
  if (score < 7) {
    return "Balanced / mixed";
  }
  return "High quality";
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function safeNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function shareCount(statement: FinancialPayload | null): number | null {
  if (!statement) {
    return null;
  }
  if (statement.shares_outstanding !== null && statement.shares_outstanding > 0) {
    return statement.shares_outstanding;
  }
  if (statement.eps !== null && statement.eps !== 0 && statement.net_income !== null) {
    const derivedShares = statement.net_income / statement.eps;
    return derivedShares > 0 ? derivedShares : null;
  }
  return null;
}

function fallbackAltman(statement: FinancialPayload | null): number | null {
  if (!statement || statement.total_assets === null || statement.total_liabilities === null || statement.revenue === null || statement.operating_income === null) {
    return null;
  }
  if (statement.total_assets === 0 || statement.total_liabilities === 0) {
    return null;
  }
  const bookEquity = statement.total_assets - statement.total_liabilities;
  return 3.3 * (statement.operating_income / statement.total_assets) + 0.6 * (bookEquity / statement.total_liabilities) + statement.revenue / statement.total_assets;
}

function safeDivide(numerator: number | null | undefined, denominator: number | null | undefined): number | null {
  if (numerator === null || numerator === undefined || denominator === null || denominator === undefined || denominator === 0) {
    return null;
  }
  return numerator / denominator;
}

function computeDebtToEquity(statement: FinancialPayload | null): number | null {
  if (!statement) {
    return null;
  }
  const equity =
    statement.total_assets !== null && statement.total_liabilities !== null
      ? statement.total_assets - statement.total_liabilities
      : null;
  return safeDivide(statement.total_liabilities, equity);
}

function deriveDebtToEquityFromRatios(liabilitiesToAssets: number | null, equityRatio: number | null): number | null {
  return safeDivide(liabilitiesToAssets, equityRatio);
}

function growthRate(current: number | null | undefined, previous: number | null | undefined): number | null {
  if (current === null || current === undefined || previous === null || previous === undefined || previous === 0) {
    return null;
  }
  return (current - previous) / Math.abs(previous);
}

function scaleRange(value: number | null, weak: number, strong: number): number | null {
  if (value === null) {
    return null;
  }
  return clamp(((value - weak) / (strong - weak)) * 10, 0, 10);
}

function inverseRangeToTen(value: number | null, strong: number, weak: number): number | null {
  if (value === null) {
    return null;
  }
  return clamp(((weak - value) / (weak - strong)) * 10, 0, 10);
}

function altmanToTen(value: number | null): number | null {
  if (value === null) {
    return null;
  }
  if (value <= 1.8) {
    return clamp((value / 1.8) * 3, 0, 3);
  }
  if (value <= 3) {
    return 3 + ((value - 1.8) / 1.2) * 4;
  }
  return clamp(7 + ((value - 3) / 3) * 3, 0, 10);
}

function isApproximateAltman(result: Record<string, unknown>): boolean {
  const status = typeof result.status === "string" ? result.status : null;
  const missingFactors = Array.isArray(result.missing_factors) ? result.missing_factors.length : 0;
  return status === "approximate" || missingFactors > 0;
}

function scaleToTen(value: number | null, max: number): number | null {
  if (value === null) {
    return null;
  }
  return clamp((value / max) * 10, 0, 10);
}

function averageScore(values: Array<number | null>): number {
  const valid = values.filter((value): value is number => value !== null && Number.isFinite(value));
  if (!valid.length) {
    return 0;
  }
  return valid.reduce((sum, value) => sum + value, 0) / valid.length;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function gaugeColor(score: number): string {
  if (score < 4) {
    return "#FF6B6B";
  }
  if (score < 7) {
    return "#FFD700";
  }
  return "#00FF41";
}

function formatSigned(value: number | null): string {
  if (value === null) {
    return "—";
  }
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2, signDisplay: "exceptZero" }).format(value);
}

function formatCurrency(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "—";
  }
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(value);
}

function formatScore(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "—";
  }
  return `${value.toFixed(1)} / 10`;
}

function formatRawScore(value: number | null, scale: number): string {
  if (value === null || Number.isNaN(value)) {
    return "—";
  }
  return `${value.toFixed(1)}/${scale}`;
}

function formatPiotroskiDisplay(value: number | null, scale: number, isPartial: boolean): string {
  if (isPartial) {
    return "Partial";
  }
  return formatRawScore(value, scale);
}
