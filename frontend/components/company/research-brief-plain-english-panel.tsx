"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { Panel } from "@/components/ui/panel";
import { useJobStream } from "@/hooks/use-job-stream";
import { MetricLabel } from "@/components/ui/metric-label";
import { PlainEnglishScorecard } from "@/components/ui/plain-english-scorecard";
import { getCompanyDerivedMetricsSummary, getCompanyFinancialRestatements, invalidateApiReadCacheForTicker } from "@/lib/api";
import { formatPercent } from "@/lib/format";
import { resolvePiotroskiScoreState } from "@/lib/piotroski";
import type {
  CompanyDerivedMetricsSummaryResponse,
  CompanyFinancialRestatementsResponse,
  DataQualityDiagnosticsPayload,
  FinancialPayload,
  ModelPayload,
} from "@/lib/types";

type TrafficLightTone = "green" | "yellow" | "red";

type ScorecardSection = {
  title: string;
  label: string;
  tone: "high" | "medium" | "low";
  summary: string;
  explanation: string;
  chips: ReactNode[];
};

interface ResearchBriefPlainEnglishPanelProps {
  ticker: string;
  models: ModelPayload[];
  modelsLoading?: boolean;
  modelsError?: string | null;
  latestFinancial: FinancialPayload | null;
  previousAnnual: FinancialPayload | null;
  diagnostics?: DataQualityDiagnosticsPayload | null;
  confidenceFlags?: string[] | null;
  strictOfficialMode?: boolean;
  reloadKey?: string;
}

export function ResearchBriefPlainEnglishPanel({
  ticker,
  models,
  modelsLoading = false,
  modelsError = null,
  latestFinancial,
  previousAnnual,
  diagnostics = null,
  confidenceFlags = null,
  strictOfficialMode = false,
  reloadKey,
}: ResearchBriefPlainEnglishPanelProps) {
  const [metricsSummary, setMetricsSummary] = useState<CompanyDerivedMetricsSummaryResponse | null>(null);
  const [restatements, setRestatements] = useState<CompanyFinancialRestatementsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [metricsError, setMetricsError] = useState<string | null>(null);
  const [restatementError, setRestatementError] = useState<string | null>(null);
  const [refreshJobId, setRefreshJobId] = useState<string | null>(null);
  const { lastEvent } = useJobStream(refreshJobId);

  const loadPanelData = useCallback(
    async (showLoading: boolean) => {
      if (showLoading) {
        setLoading(true);
      }

      const [metricsResult, restatementResult] = await Promise.allSettled([
        getCompanyDerivedMetricsSummary(ticker, { periodType: "ttm" }),
        getCompanyFinancialRestatements(ticker),
      ]);

      if (metricsResult.status === "fulfilled") {
        setMetricsSummary(metricsResult.value);
        setMetricsError(null);
      } else {
        setMetricsError(metricsResult.reason instanceof Error ? metricsResult.reason.message : "Unable to load derived metrics summary");
      }

      if (restatementResult.status === "fulfilled") {
        setRestatements(restatementResult.value);
        setRestatementError(null);
      } else {
        setRestatementError(restatementResult.reason instanceof Error ? restatementResult.reason.message : "Unable to load filing-quality summary");
      }

      const nextJobId =
        (metricsResult.status === "fulfilled" ? metricsResult.value.refresh.job_id : null) ??
        (restatementResult.status === "fulfilled" ? restatementResult.value.refresh.job_id : null) ??
        null;
      setRefreshJobId(nextJobId);

      if (showLoading) {
        setLoading(false);
      }
    },
    [ticker]
  );

  useEffect(() => {
    void loadPanelData(true);
  }, [loadPanelData, reloadKey]);

  useEffect(() => {
    if (!refreshJobId || !lastEvent) {
      return;
    }
    if (lastEvent.status !== "completed" && lastEvent.status !== "failed") {
      return;
    }

    invalidateApiReadCacheForTicker(ticker);
    void loadPanelData(false);
  }, [lastEvent, loadPanelData, refreshJobId, ticker]);

  const sections = useMemo(
    () =>
      buildSections({
        models,
        latestFinancial,
        previousAnnual,
        metricsSummary,
        restatements,
        diagnostics,
        confidenceFlags: confidenceFlags ?? [],
        strictOfficialMode,
      }),
    [confidenceFlags, diagnostics, latestFinancial, metricsSummary, models, previousAnnual, restatements, strictOfficialMode]
  );

  const errorMessages = [modelsError, metricsError, restatementError].filter((value): value is string => Boolean(value));

  return (
    <Panel
      title="Plain-English Scorecard"
      subtitle="A single top-of-brief traffic-light read that blends quality, resilience, capital allocation, and reporting hygiene."
      variant="subtle"
    >
      <div className="plain-english-scorecard-panel">
        {loading && modelsLoading && !sections.length ? <div className="text-muted">Loading the top-of-brief scorecard...</div> : null}

        <div className="plain-english-scorecard-grid">
          {sections.map((section) => (
            <PlainEnglishScorecard
              key={section.title}
              title={section.title}
              label={section.label}
              tone={section.tone}
              summary={section.summary}
              explanation={section.explanation}
              chips={section.chips}
            />
          ))}
        </div>

        {errorMessages.length ? (
          <div className="text-muted">Some score inputs are still warming: {errorMessages.join(" · ")}.</div>
        ) : null}
      </div>
    </Panel>
  );
}

function buildSections({
  models,
  latestFinancial,
  previousAnnual,
  metricsSummary,
  restatements,
  diagnostics,
  confidenceFlags,
  strictOfficialMode,
}: {
  models: ModelPayload[];
  latestFinancial: FinancialPayload | null;
  previousAnnual: FinancialPayload | null;
  metricsSummary: CompanyDerivedMetricsSummaryResponse | null;
  restatements: CompanyFinancialRestatementsResponse | null;
  diagnostics: DataQualityDiagnosticsPayload | null;
  confidenceFlags: string[];
  strictOfficialMode: boolean;
}): ScorecardSection[] {
  const modelMap = new Map(models.map((model) => [model.model_name, model]));
  const piotroskiState = resolvePiotroskiScoreState(modelMap.get("piotroski")?.result);
  const altmanResult = asRecord(modelMap.get("altman_z")?.result);
  const altmanZ = asNumber(altmanResult.z_score_approximate);

  const metricMap = new Map((metricsSummary?.metrics ?? []).map((metric) => [metric.metric_key, metric.metric_value]));
  const aggregatedMetricFlags = Array.from(new Set((metricsSummary?.metrics ?? []).flatMap((metric) => metric.quality_flags)));

  const revenueGrowth = metricValue(metricMap, "revenue_growth") ?? growthRate(latestFinancial?.revenue ?? null, previousAnnual?.revenue ?? null);
  const operatingMargin = metricValue(metricMap, "operating_margin") ?? safeDivide(latestFinancial?.operating_income ?? null, latestFinancial?.revenue ?? null);
  const fcfMargin = metricValue(metricMap, "fcf_margin") ?? safeDivide(latestFinancial?.free_cash_flow ?? null, latestFinancial?.revenue ?? null);
  const roic = metricValue(metricMap, "roic_proxy");
  const currentRatio = metricValue(metricMap, "current_ratio") ?? safeDivide(latestFinancial?.current_assets ?? null, latestFinancial?.current_liabilities ?? null);
  const leverageRatio = metricValue(metricMap, "leverage_ratio") ?? safeDivide(latestFinancial?.total_liabilities ?? null, latestFinancial?.total_assets ?? null);
  const shareholderYield = metricValue(metricMap, "shareholder_yield");
  const buybackYield = metricValue(metricMap, "buyback_yield");
  const dividendYield = metricValue(metricMap, "dividend_yield");
  const shareDilution = metricValue(metricMap, "share_dilution");

  const coverageRatio = metricsSummary?.diagnostics.coverage_ratio ?? diagnostics?.coverage_ratio ?? null;
  const fallbackRatio = metricsSummary?.diagnostics.fallback_ratio ?? diagnostics?.fallback_ratio ?? null;
  const staleFlags = Array.from(new Set([...(metricsSummary?.diagnostics.stale_flags ?? []), ...(diagnostics?.stale_flags ?? [])]));
  const combinedConfidenceFlags = Array.from(new Set([...(metricsSummary?.confidence_flags ?? []), ...confidenceFlags, ...aggregatedMetricFlags]));
  const restatementCount = restatements?.summary.total_restatements ?? 0;

  const businessTone = toneFromCounts(
    [isAtLeast(revenueGrowth, 0.08), isAtLeast(operatingMargin, 0.15), isAtLeast(roic, 0.12), isAtLeast(fcfMargin, 0.1)],
    [isLessThan(revenueGrowth, 0), isLessThan(operatingMargin, 0.08), isLessThan(roic, 0.06), isLessThan(fcfMargin, 0.04)]
  );
  const financialTone = toneFromCounts(
    [isAtLeast(piotroskiState.score, 7), isAtLeast(altmanZ, 3), isAtLeast(currentRatio, 1.5), isLessThan(leverageRatio, 0.55)],
    [isLessThan(piotroskiState.score, 4), isLessThan(altmanZ, 1.8), isLessThan(currentRatio, 1), isAtLeast(leverageRatio, 0.75)]
  );
  const capitalTone = toneFromCounts(
    [isAtLeast(shareholderYield, 0.02), isLessThan(shareDilution, 0.01), isAtLeast(fcfMargin, 0.08), isAtLeast(buybackYield, 0.01)],
    [isLessThan(shareholderYield, 0), isAtLeast(shareDilution, 0.03), isLessThan(fcfMargin, 0.04)]
  );
  const filingTone = toneFromCounts(
    [restatementCount === 0, staleFlags.length === 0, isAtLeast(coverageRatio, 0.85), isLessThan(fallbackRatio, 0.2), combinedConfidenceFlags.length === 0],
    [restatementCount > 0, staleFlags.length > 0, isLessThan(coverageRatio, 0.65), isAtLeast(fallbackRatio, 0.5), combinedConfidenceFlags.length >= 3]
  );

  return [
    {
      title: "Business Quality",
      label: toneLabel(businessTone),
      tone: toneToScorecardTone(businessTone),
      summary:
        businessTone === "green"
          ? "Operating quality still looks like a compounding engine."
          : businessTone === "red"
            ? "Operating quality is soft enough to pressure the thesis."
            : "Operating quality is acceptable, but not clean enough to dismiss debate.",
      explanation: `Revenue growth ${formatPercentOrDash(revenueGrowth)}, operating margin ${formatPercentOrDash(operatingMargin)}, and ROIC ${formatPercentOrDash(roic)} point to a ${businessTone === "green" ? "healthy" : businessTone === "red" ? "weaker" : "mixed"} operating profile.`,
      chips: [
        metricChip("Revenue Growth", formatPercentOrDash(revenueGrowth), "revenue_growth"),
        metricChip("Operating Margin", formatPercentOrDash(operatingMargin), "operating_margin"),
        metricChip("ROIC", formatPercentOrDash(roic), "roic_proxy"),
      ],
    },
    {
      title: "Financial Health",
      label: toneLabel(financialTone),
      tone: toneToScorecardTone(financialTone),
      summary:
        financialTone === "green"
          ? "The balance sheet reads resilient rather than fragile."
          : financialTone === "red"
            ? "The balance sheet needs more caution than confidence."
            : "Financial resilience is serviceable, but not pristine.",
      explanation: `${piotroskiState.score == null ? "Piotroski is unavailable" : `Piotroski is ${piotroskiState.score.toFixed(1)}/9`}, Altman Z is ${formatMultipleOrDash(altmanZ)}, and current ratio is ${formatMultipleOrDash(currentRatio)}, which leaves the financial profile ${financialTone === "green" ? "comfortably strong" : financialTone === "red" ? "more fragile" : "middle of the road"}.`,
      chips: [
        metricChip("Piotroski F-Score", piotroskiState.score == null ? "—" : `${piotroskiState.score.toFixed(1)}/9`, "piotroski_score"),
        metricChip("Altman Z-Score", formatMultipleOrDash(altmanZ), "altman_z_score"),
        metricChip("Current Ratio", formatMultipleOrDash(currentRatio), "current_ratio"),
        metricChip("Leverage Ratio", formatMultipleOrDash(leverageRatio), "leverage_ratio"),
      ],
    },
    {
      title: "Capital Allocation",
      label: toneLabel(capitalTone),
      tone: toneToScorecardTone(capitalTone),
      summary:
        capitalTone === "green"
          ? "Cash returns and dilution are working for shareholders."
          : capitalTone === "red"
            ? "Capital allocation is eroding the equity claim."
            : "Capital allocation is directionally fine, but not consistently shareholder-friendly.",
      explanation: `${strictOfficialMode && shareholderYield == null ? "Strict official mode hides price-based yield overlays" : `Shareholder yield is ${formatPercentOrDash(shareholderYield)}`}, share dilution is ${formatPercentOrDash(shareDilution)}, and free-cash-flow margin is ${formatPercentOrDash(fcfMargin)}, which makes the capital-allocation read ${capitalTone === "green" ? "constructive" : capitalTone === "red" ? "concerning" : "mixed"}.`,
      chips: [
        metricChip("Shareholder Yield", strictOfficialMode && shareholderYield == null ? "Strict mode" : formatPercentOrDash(shareholderYield), "shareholder_yield"),
        metricChip("Buyback Yield", formatPercentOrDash(buybackYield), "buyback_yield"),
        metricChip("Dividend Yield", formatPercentOrDash(dividendYield), "dividend_yield"),
        metricChip("Share Dilution", formatPercentOrDash(shareDilution), "share_dilution"),
      ],
    },
    {
      title: "Filing Quality",
      label: toneLabel(filingTone),
      tone: toneToScorecardTone(filingTone),
      summary:
        filingTone === "green"
          ? "The cached reporting trail looks clean and current."
          : filingTone === "red"
            ? "Reporting quality needs extra skepticism before underwriting conclusions."
            : "The reporting trail is usable, but not spotless.",
      explanation: `${restatementCount} restatements, ${staleFlags.length} stale-period flags, and ${formatPercentOrDash(coverageRatio)} metric coverage make the filing-quality read ${filingTone === "green" ? "comfortably clean" : filingTone === "red" ? "too noisy" : "adequate but not perfect"}.`,
      chips: [
        metricChip("Restatement Count", String(restatementCount), "restatement_count"),
        metricChip("Filing Coverage", formatPercentOrDash(coverageRatio)),
        metricChip("Fallback Ratio", formatPercentOrDash(fallbackRatio)),
        metricChip("Stale Flags", String(staleFlags.length), "stale_period_flag"),
      ],
    },
  ];
}

function metricValue(metricMap: Map<string, number | null>, key: string): number | null {
  return metricMap.get(key) ?? null;
}

function toneFromCounts(positives: boolean[], negatives: boolean[]): TrafficLightTone {
  const positiveCount = positives.filter(Boolean).length;
  const negativeCount = negatives.filter(Boolean).length;

  if (negativeCount >= 2) {
    return "red";
  }
  if (positiveCount >= 2 && negativeCount === 0) {
    return "green";
  }
  return "yellow";
}

function toneLabel(tone: TrafficLightTone): string {
  if (tone === "green") {
    return "Green";
  }
  if (tone === "red") {
    return "Red";
  }
  return "Yellow";
}

function toneToScorecardTone(tone: TrafficLightTone): "high" | "medium" | "low" {
  if (tone === "green") {
    return "high";
  }
  if (tone === "red") {
    return "low";
  }
  return "medium";
}

function metricChip(label: string, value: string, metricKey?: string) {
  return (
    <>
      <MetricLabel label={label} metricKey={metricKey} /> {value}
    </>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function safeDivide(numerator: number | null, denominator: number | null): number | null {
  if (numerator == null || denominator == null || denominator === 0) {
    return null;
  }
  return numerator / denominator;
}

function growthRate(current: number | null, previous: number | null): number | null {
  if (current == null || previous == null || previous === 0) {
    return null;
  }
  return (current - previous) / Math.abs(previous);
}

function isAtLeast(value: number | null, threshold: number): boolean {
  return value != null && value >= threshold;
}

function isLessThan(value: number | null, threshold: number): boolean {
  return value != null && value < threshold;
}

function formatPercentOrDash(value: number | null): string {
  return value == null ? "—" : formatPercent(value);
}

function formatMultipleOrDash(value: number | null): string {
  return value == null ? "—" : `${value.toFixed(2)}x`;
}