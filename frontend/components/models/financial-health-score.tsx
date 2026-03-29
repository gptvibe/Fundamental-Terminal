"use client";

import { useMemo } from "react";
import { PolarAngleAxis, RadialBar, RadialBarChart, ResponsiveContainer } from "recharts";

import { formatPercent } from "@/lib/format";
import { formatPiotroskiDisplay as formatResolvedPiotroskiDisplay, resolvePiotroskiScoreState } from "@/lib/piotroski";
import type { FinancialPayload, ModelPayload } from "@/lib/types";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);

interface FinancialHealthScoreProps {
  models: ModelPayload[];
  financials: FinancialPayload[];
}

export function FinancialHealthScore({ models, financials }: FinancialHealthScoreProps) {
  const health = useMemo(() => buildHealthScores(models, financials), [models, financials]);

  if (health === null) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 240 }}>
        <div className="grid-empty-kicker">Health engine</div>
        <div className="grid-empty-title">Financial health scores unavailable</div>
        <div className="grid-empty-copy">Warm the cached models and annual financial statements first to unlock the gauge view.</div>
      </div>
    );
  }

  return (
    <div className="health-score-shell">
      <div className="health-score-grid">
        {health.cards.map((card) => (
          <GaugeCard key={card.label} label={card.label} score={card.score} detail={card.detail} />
        ))}
      </div>

      <div className="health-score-inputs">
        <span className="pill">Piotroski {health.inputs.piotroskiDisplay}</span>
        <span className="pill">Altman Proxy {formatSigned(health.inputs.altmanProxyScore)}</span>
        <span className="pill">ROA {formatPercent(health.inputs.returnOnAssets)}</span>
        <span className="pill">Debt / Equity {formatSigned(health.inputs.debtToEquity)}</span>
        <span className="pill">Revenue Growth {formatPercent(health.inputs.revenueGrowth)}</span>
      </div>
    </div>
  );
}

function GaugeCard({ label, score, detail }: { label: string; score: number; detail: string }) {
  const clampedScore = clamp(score, 0, 10);
  const color = gaugeColor(clampedScore);
  const chartData = [{ value: clampedScore, fill: color }];

  return (
    <div className="health-score-card">
      <div className="health-score-title">{label}</div>
      <div className="health-gauge-shell">
        <ResponsiveContainer width="100%" height="100%">
          <RadialBarChart data={chartData} innerRadius="72%" outerRadius="100%" startAngle={90} endAngle={-270} barSize={14}>
            <PolarAngleAxis type="number" domain={[0, 10]} tick={false} axisLine={false} />
            <RadialBar dataKey="value" background={{ fill: "var(--panel-border)" }} cornerRadius={12} />
          </RadialBarChart>
        </ResponsiveContainer>
        <div className="health-gauge-center">
          <div className="health-gauge-value" style={{ color }}>{clampedScore.toFixed(1)}</div>
          <div className="health-gauge-scale">/ 10</div>
        </div>
      </div>
      <div className="health-score-detail">{detail}</div>
    </div>
  );
}

function buildHealthScores(models: ModelPayload[], financials: FinancialPayload[]) {
  const annualFinancials = financials.filter((statement) => ANNUAL_FORMS.has(statement.filing_type));
  const current = annualFinancials[0] ?? financials[0] ?? null;
  const previous = annualFinancials[1] ?? financials[1] ?? null;
  if (!current) {
    return null;
  }

  const byName = Object.fromEntries(models.map((model) => [model.model_name, model])) as Record<string, ModelPayload | undefined>;
  const ratios = asRecord(byName.ratios?.result);
  const ratioValues = asRecord(ratios.values);
  const dupont = asRecord(byName.dupont?.result);
  const piotroski = asRecord(byName.piotroski?.result);
  const altman = asRecord(byName.altman_z?.result);
  const piotroskiState = resolvePiotroskiScoreState(piotroski);

  const piotroskiRaw = piotroskiState.rawScore;
  const piotroskiSignal = scaleToTen(piotroskiState.score, piotroskiState.scoreMax);
  const altmanRaw = safeNumber(altman.z_score_approximate);
  const altmanSignal = isApproximateAltman(altman) ? null : altmanToTen(altmanRaw);
  const returnOnAssets = safeNumber(ratioValues.return_on_assets) ?? computeReturnOnAssets(current, previous ?? null);
  const debtToEquity =
    computeDebtToEquity(current) ??
    deriveDebtToEquityFromRatios(safeNumber(ratioValues.liabilities_to_assets), safeNumber(ratioValues.equity_ratio));
  const revenueGrowth =
    safeNumber(ratioValues.revenue_growth) ??
    growthRate(current.revenue, previous?.revenue ?? null);
  const piotroskiDisplay = formatResolvedPiotroskiDisplay(piotroskiState);

  const profitability = averageScore([
    piotroskiSignal,
    scaleRange(returnOnAssets, 0, 0.18),
    scaleRange(safeNumber(dupont.return_on_equity) ?? safeNumber(ratioValues.return_on_equity), 0, 0.25)
  ]);
  const financialStrength = averageScore([
    altmanSignal,
    inverseRangeToTen(debtToEquity, 0.2, 2.5),
    piotroskiSignal
  ]);
  const growth = averageScore([
    scaleRange(revenueGrowth, -0.05, 0.22),
    scaleRange(returnOnAssets, 0, 0.18),
    piotroskiSignal
  ]);
  const overall = averageScore([profitability, financialStrength, growth]);

  return {
    inputs: {
      piotroskiDisplay,
      altmanProxyScore: altmanRaw,
      returnOnAssets,
      debtToEquity,
      revenueGrowth
    },
    cards: [
      {
        label: "Profitability",
        score: profitability,
        detail: `ROA ${formatPercent(returnOnAssets)} · Piotroski ${piotroskiDisplay}`
      },
      {
        label: "Financial Strength",
        score: financialStrength,
        detail: `Altman proxy ${formatSigned(altmanRaw)} · D/E ${formatSigned(debtToEquity)}`
      },
      {
        label: "Growth",
        score: growth,
        detail: `Revenue growth ${formatPercent(revenueGrowth)} · ROA ${formatPercent(returnOnAssets)}`
      },
      {
        label: "Overall",
        score: overall,
        detail: scoreBandLabel(overall)
      }
    ]
  };
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

function computeReturnOnAssets(current: FinancialPayload, previous: FinancialPayload | null): number | null {
  const previousAssets = previous?.total_assets ?? null;
  const averageAssets =
    current.total_assets !== null && previousAssets !== null
      ? (current.total_assets + previousAssets) / 2
      : current.total_assets;
  return safeDivide(current.net_income, averageAssets);
}

function computeDebtToEquity(statement: FinancialPayload): number | null {
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
    return "var(--negative)";
  }
  if (score < 7) {
    return "var(--warning)";
  }
  return "var(--positive)";
}

function scoreBandLabel(score: number): string {
  if (score < 4) {
    return "Weak profile";
  }
  if (score < 7) {
    return "Mixed profile";
  }
  return "Strong profile";
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

function formatPiotroskiScore(value: number | null, scale: number, isPartial: boolean): string {
  if (isPartial) {
    return "Partial";
  }
  if (value === null) {
    return "—";
  }
  return `${value.toFixed(1)}/${scale}`;
}
