"use client";

import { useEffect, useMemo, useState } from "react";

import { getCompanyModels } from "@/lib/api";
import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import type { FinancialPayload, ModelPayload } from "@/lib/types";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);

type AlertLevel = "high" | "medium" | "clear" | "muted";

type RiskAlert = {
  key: string;
  title: string;
  level: AlertLevel;
  icon: string;
  explanation: string;
  metric: string;
};

interface RiskRedFlagPanelProps {
  ticker: string;
  financials: FinancialPayload[];
  reloadKey?: string;
}

export function RiskRedFlagPanel({ ticker, financials, reloadKey }: RiskRedFlagPanelProps) {
  const [altmanModel, setAltmanModel] = useState<ModelPayload | null>(null);
  const [loadingAltman, setLoadingAltman] = useState(true);
  const [altmanError, setAltmanError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadAltman() {
      try {
        setLoadingAltman(true);
        setAltmanError(null);
        const response = await getCompanyModels(ticker, ["altman_z"]);
        if (!cancelled) {
          const nextModel = response.models.find((model) => model.model_name.toLowerCase() === "altman_z") ?? null;
          setAltmanModel(nextModel);
        }
      } catch (nextError) {
        if (!cancelled) {
          setAltmanError(nextError instanceof Error ? nextError.message : "Unable to load Altman model cache");
          setAltmanModel(null);
        }
      } finally {
        if (!cancelled) {
          setLoadingAltman(false);
        }
      }
    }

    void loadAltman();
    return () => {
      cancelled = true;
    };
  }, [ticker, reloadKey]);

  const alerts = useMemo(() => buildRiskAlerts(financials, altmanModel, loadingAltman, altmanError), [altmanError, altmanModel, financials, loadingAltman]);
  const sortedAlerts = useMemo(() => [...alerts].sort((left, right) => severityRank(left.level) - severityRank(right.level)), [alerts]);
  const activeAlerts = sortedAlerts.filter((alert) => alert.level === "high" || alert.level === "medium");
  const backgroundAlerts = sortedAlerts.filter((alert) => alert.level === "clear" || alert.level === "muted");
  const priorityAlerts = activeAlerts.length ? activeAlerts : backgroundAlerts.slice(0, 3);
  const deferredAlerts = activeAlerts.length ? backgroundAlerts : backgroundAlerts.slice(3);
  const activeCount = alerts.filter((alert) => alert.level === "high" || alert.level === "medium").length;
  const headline = activeCount ? `${activeCount} active risk signal${activeCount === 1 ? "" : "s"}` : "No active red flags";

  return (
    <div className="risk-panel-shell">
      <div className="risk-panel-meta">
        <span className="pill">
          Active alerts: <span className={activeCount ? "risk-pill-danger" : "risk-pill-safe"}>{activeCount}</span>
        </span>
        <span className="pill">Checks: {alerts.length}</span>
      </div>

      <div className="risk-feed-headline">
        <div className={`risk-feed-title ${activeCount ? "risk-feed-title-danger" : "risk-feed-title-safe"}`}>{headline}</div>
        <div className="risk-feed-subcopy">
          {activeCount
            ? "Priority items are pinned first so the biggest issues stay visible in the side rail."
            : "Everything currently reads stable or informational. Background checks remain available below."}
        </div>
      </div>

      <div className="risk-card-stack">
        {priorityAlerts.map((alert) => renderRiskCard(alert))}
      </div>

      {deferredAlerts.length ? (
        <details className="risk-details" open={activeCount === 0}>
          <summary>
            Background checks
            <span className="pill">{deferredAlerts.length}</span>
          </summary>
          <div className="risk-details-body">{deferredAlerts.map((alert) => renderRiskCard(alert))}</div>
        </details>
      ) : null}
    </div>
  );
}

function renderRiskCard(alert: RiskAlert) {
  return (
    <article key={alert.key} className={`risk-card risk-card-${alert.level}`}>
      <div className="risk-card-topline">
        <span className={`risk-card-badge risk-card-badge-${alert.level}`}>{levelLabel(alert.level)}</span>
        <div className="risk-card-metric">{alert.metric}</div>
      </div>
      <div className="risk-card-header">
        <div className="risk-icon" aria-hidden="true">
          {alert.icon}
        </div>
        <div>
          <div className="risk-card-title">{alert.title}</div>
          <div className="risk-card-explanation">{alert.explanation}</div>
        </div>
      </div>
    </article>
  );
}

function severityRank(level: AlertLevel): number {
  switch (level) {
    case "high":
      return 0;
    case "medium":
      return 1;
    case "clear":
      return 2;
    default:
      return 3;
  }
}

function levelLabel(level: AlertLevel): string {
  switch (level) {
    case "high":
      return "High Priority";
    case "medium":
      return "Watch";
    case "clear":
      return "Clear";
    default:
      return "Info";
  }
}

function buildRiskAlerts(
  financials: FinancialPayload[],
  altmanModel: ModelPayload | null,
  loadingAltman: boolean,
  altmanError: string | null
): RiskAlert[] {
  const annuals = financials.filter((statement) => ANNUAL_FORMS.has(statement.filing_type));

  return [
    detectRevenueDecline(annuals),
    detectNegativeFreeCashFlow(annuals, financials),
    detectIncreasingDebt(annuals),
    detectFallingMargins(annuals),
    detectShareDilution(annuals),
    detectLowAltmanZ(financials, altmanModel, loadingAltman, altmanError)
  ];
}

function detectRevenueDecline(annuals: FinancialPayload[]): RiskAlert {
  const sample = latestDefined(annuals, "revenue", 3);
  if (sample.length < 3) {
    return mutedAlert("declining-revenue", "Declining Revenue", "Need three annual revenue points to evaluate the trend.");
  }

  const [current, previous, older] = sample;
  const declining = isLower(current.revenue, previous.revenue) && isLower(previous.revenue, older.revenue);
  if (declining) {
    return {
      key: "declining-revenue",
      title: "Declining Revenue",
      level: "high",
      icon: "⚠",
      explanation: `Revenue fell in each of the last three annual periods ending ${formatDate(older.period_end)}, ${formatDate(previous.period_end)}, and ${formatDate(current.period_end)}.`,
      metric: `${formatCompactNumber(older.revenue)} → ${formatCompactNumber(previous.revenue)} → ${formatCompactNumber(current.revenue)}`
    };
  }

  return {
    key: "declining-revenue",
    title: "Declining Revenue",
    level: "clear",
    icon: "✓",
    explanation: "Top-line revenue is not in a three-year downward trend based on the latest annual filings.",
    metric: `${formatCompactNumber(older.revenue)} → ${formatCompactNumber(previous.revenue)} → ${formatCompactNumber(current.revenue)}`
  };
}

function detectNegativeFreeCashFlow(annuals: FinancialPayload[], financials: FinancialPayload[]): RiskAlert {
  const latest = annuals.find((statement) => statement.free_cash_flow != null) ?? financials.find((statement) => statement.free_cash_flow != null) ?? null;
  if (!latest || latest.free_cash_flow == null) {
    return mutedAlert("negative-fcf", "Negative Free Cash Flow", "Free cash flow is unavailable in the current cache.");
  }

  if (latest.free_cash_flow < 0) {
    return {
      key: "negative-fcf",
      title: "Negative Free Cash Flow",
      level: "high",
      icon: "⚠",
      explanation: `The latest ${latest.filing_type} shows cash generation after capex remains negative.`,
      metric: `${formatDate(latest.period_end)} · ${formatCompactNumber(latest.free_cash_flow)}`
    };
  }

  return {
    key: "negative-fcf",
    title: "Negative Free Cash Flow",
    level: "clear",
    icon: "✓",
    explanation: "The latest cached filing shows positive free cash flow after capital expenditures.",
    metric: `${formatDate(latest.period_end)} · ${formatCompactNumber(latest.free_cash_flow)}`
  };
}

function detectIncreasingDebt(annuals: FinancialPayload[]): RiskAlert {
  const liabilitySeries = latestDefined(annuals, "total_liabilities", 3);
  const latestDebtChange = annuals.find((statement) => statement.debt_changes != null) ?? null;
  if (liabilitySeries.length < 2 && !latestDebtChange) {
    return mutedAlert("increasing-debt", "Increasing Debt", "Need liabilities or debt issuance history to assess leverage pressure.");
  }

  const risingLiabilities =
    liabilitySeries.length >= 3 &&
    isHigher(liabilitySeries[0].total_liabilities, liabilitySeries[1].total_liabilities) &&
    isHigher(liabilitySeries[1].total_liabilities, liabilitySeries[2].total_liabilities);
  const positiveDebtChange = typeof latestDebtChange?.debt_changes === "number" && latestDebtChange.debt_changes > 0;

  if (risingLiabilities || positiveDebtChange) {
    return {
      key: "increasing-debt",
      title: "Increasing Debt",
      level: risingLiabilities ? "high" : "medium",
      icon: "⚠",
      explanation: risingLiabilities
        ? "Total liabilities have increased across the last three annual filings, signaling a rising debt burden."
        : "The latest annual filing shows net debt issuance outpacing repayments.",
      metric: risingLiabilities
        ? `${formatCompactNumber(liabilitySeries[2].total_liabilities)} → ${formatCompactNumber(liabilitySeries[1].total_liabilities)} → ${formatCompactNumber(liabilitySeries[0].total_liabilities)}`
        : `${formatDate(latestDebtChange?.period_end ?? null)} · Net debt change ${formatCompactNumber(latestDebtChange?.debt_changes)}`
    };
  }

  return {
    key: "increasing-debt",
    title: "Increasing Debt",
    level: "clear",
    icon: "✓",
    explanation: "Liabilities are not in a persistent upward trend and recent net debt issuance looks contained.",
    metric:
      liabilitySeries.length >= 2
        ? `${formatCompactNumber(liabilitySeries.at(-1)?.total_liabilities)} → ${formatCompactNumber(liabilitySeries[0].total_liabilities)}`
        : `${formatDate(latestDebtChange?.period_end ?? null)} · ${formatCompactNumber(latestDebtChange?.debt_changes)}`
  };
}

function detectFallingMargins(annuals: FinancialPayload[]): RiskAlert {
  const marginSeries = annuals
    .map((statement) => ({ statement, margin: marginValue(statement) }))
    .filter((entry): entry is { statement: FinancialPayload; margin: number } => entry.margin != null)
    .slice(0, 3);

  if (marginSeries.length < 3) {
    return mutedAlert("falling-margins", "Falling Margins", "Need three annual operating margin points to evaluate margin compression.");
  }

  const [current, previous, older] = marginSeries;
  const falling = current.margin < previous.margin && previous.margin < older.margin;
  if (falling) {
    return {
      key: "falling-margins",
      title: "Falling Margins",
      level: "medium",
      icon: "▲",
      explanation: "Operating margin has compressed for three consecutive annual periods, which can signal weakening pricing power or cost control.",
      metric: `${formatPercent(older.margin)} → ${formatPercent(previous.margin)} → ${formatPercent(current.margin)}`
    };
  }

  return {
    key: "falling-margins",
    title: "Falling Margins",
    level: "clear",
    icon: "✓",
    explanation: "Margins are stable or improving relative to recent annual history.",
    metric: `${formatPercent(older.margin)} → ${formatPercent(previous.margin)} → ${formatPercent(current.margin)}`
  };
}

function detectShareDilution(annuals: FinancialPayload[]): RiskAlert {
  const sample = latestDefined(annuals, "shares_outstanding", 2);
  if (sample.length < 2) {
    return mutedAlert("share-dilution", "Share Dilution", "Need at least two annual share-count observations to assess dilution.");
  }

  const [current, previous] = sample;
  const dilutionRate = growthRate(current.shares_outstanding, previous.shares_outstanding);
  if (dilutionRate != null && dilutionRate > 0.01) {
    return {
      key: "share-dilution",
      title: "Share Dilution",
      level: dilutionRate > 0.05 ? "high" : "medium",
      icon: "⚠",
      explanation: "Shares outstanding increased versus the prior annual filing, which can dilute per-share value creation.",
      metric: `${formatCompactNumber(previous.shares_outstanding)} → ${formatCompactNumber(current.shares_outstanding)} (${formatPercent(dilutionRate)})`
    };
  }

  return {
    key: "share-dilution",
    title: "Share Dilution",
    level: "clear",
    icon: "✓",
    explanation: "Share count is flat or lower versus the prior annual filing.",
    metric: `${formatCompactNumber(previous.shares_outstanding)} → ${formatCompactNumber(current.shares_outstanding)}`
  };
}

function detectLowAltmanZ(
  financials: FinancialPayload[],
  altmanModel: ModelPayload | null,
  loadingAltman: boolean,
  altmanError: string | null
): RiskAlert {
  if (loadingAltman) {
    return mutedAlert("low-altman-z", "Altman Z Proxy", "Loading the cached Altman model from PostgreSQL...");
  }
  if (altmanError) {
    return mutedAlert("low-altman-z", "Altman Z Proxy", altmanError);
  }

  const altmanResult = asRecord(altmanModel?.result);
  const modelZScore = asNumber(altmanResult.z_score_approximate);
  const zScore = modelZScore ?? fallbackAltmanZ(financials);
  const periodEnd =
    (typeof altmanModel?.result?.period_end === "string" ? altmanModel.result.period_end : null) ??
    financials.find((statement) => ANNUAL_FORMS.has(statement.filing_type))?.period_end ??
    financials[0]?.period_end ??
    null;
  if (zScore == null) {
    return mutedAlert("low-altman-z", "Altman Z Proxy", "The cached model does not have enough inputs to estimate the Altman proxy yet.");
  }

  if (modelZScore === null || isApproximateAltman(altmanResult)) {
    return {
      key: "low-altman-z",
      title: "Altman Z Proxy",
      level: "muted",
      icon: "…",
      explanation: "This estimate uses a partial Altman proxy, so the classic 1.8 and 3.0 distress cutoffs do not apply to it.",
      metric: `${periodEnd ? `${formatDate(periodEnd)} · ` : ""}Z proxy ≈ ${zScore.toFixed(2)}`
    };
  }

  if (zScore < 1.8) {
    return {
      key: "low-altman-z",
      title: "Low Altman Z Score",
      level: "high",
      icon: "⚠",
      explanation: "The latest cached Altman Z estimate sits in the distress zone, which can indicate elevated balance-sheet risk.",
      metric: `${periodEnd ? `${formatDate(periodEnd)} · ` : ""}Z ≈ ${zScore.toFixed(2)}`
    };
  }

  if (zScore < 3) {
    return {
      key: "low-altman-z",
      title: "Low Altman Z Score",
      level: "medium",
      icon: "▲",
      explanation: "The Altman Z estimate is above distress but still below the stronger safety range.",
      metric: `${periodEnd ? `${formatDate(periodEnd)} · ` : ""}Z ≈ ${zScore.toFixed(2)}`
    };
  }

  return {
    key: "low-altman-z",
    title: "Low Altman Z Score",
    level: "clear",
    icon: "✓",
    explanation: "The cached Altman Z estimate is comfortably above the low-risk threshold.",
    metric: `${periodEnd ? `${formatDate(periodEnd)} · ` : ""}Z ≈ ${zScore.toFixed(2)}`
  };
}

function mutedAlert(key: string, title: string, explanation: string): RiskAlert {
  return {
    key,
    title,
    level: "muted",
    icon: "…",
    explanation,
    metric: "Awaiting more cached data"
  };
}

function latestDefined<T extends keyof FinancialPayload>(financials: FinancialPayload[], field: T, count: number): FinancialPayload[] {
  return financials.filter((statement) => typeof statement[field] === "number").slice(0, count);
}

function isLower(left: number | null | undefined, right: number | null | undefined) {
  return typeof left === "number" && typeof right === "number" && left < right;
}

function isHigher(left: number | null | undefined, right: number | null | undefined) {
  return typeof left === "number" && typeof right === "number" && left > right;
}

function marginValue(statement: FinancialPayload): number | null {
  if (statement.revenue == null || statement.revenue === 0) {
    return null;
  }
  if (statement.operating_income != null) {
    return statement.operating_income / statement.revenue;
  }
  if (statement.net_income != null) {
    return statement.net_income / statement.revenue;
  }
  return null;
}

function growthRate(current: number | null | undefined, previous: number | null | undefined): number | null {
  if (typeof current !== "number" || typeof previous !== "number" || previous === 0) {
    return null;
  }
  return (current - previous) / Math.abs(previous);
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function isApproximateAltman(result: Record<string, unknown>): boolean {
  const status = typeof result.status === "string" ? result.status : null;
  const missingFactors = Array.isArray(result.missing_factors) ? result.missing_factors.length : 0;
  return status === "approximate" || missingFactors > 0;
}

function fallbackAltmanZ(financials: FinancialPayload[]): number | null {
  const current = financials.find((statement) => ANNUAL_FORMS.has(statement.filing_type)) ?? financials[0] ?? null;
  if (!current) {
    return null;
  }

  const totalAssets = current.total_assets;
  const totalLiabilities = current.total_liabilities;
  const revenue = current.revenue;
  const operatingIncome = current.operating_income;
  if (
    typeof totalAssets !== "number" ||
    typeof totalLiabilities !== "number" ||
    typeof revenue !== "number" ||
    typeof operatingIncome !== "number" ||
    totalAssets === 0 ||
    totalLiabilities === 0
  ) {
    return null;
  }

  const bookEquityProxy = totalAssets - totalLiabilities;
  return 3.3 * (operatingIncome / totalAssets) + 0.6 * (bookEquityProxy / totalLiabilities) + revenue / totalAssets;
}
