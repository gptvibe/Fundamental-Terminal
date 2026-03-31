"use client";

import { useEffect, useMemo, useState } from "react";
import {
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

import { FinancialChartStateBar } from "@/components/charts/financial-chart-state-bar";
import { SnapshotSurfaceStatus } from "@/components/company/snapshot-surface-status";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, chartTick } from "@/lib/chart-theme";
import { difference, formatSignedCompactDelta, type SharedFinancialChartState } from "@/lib/financial-chart-state";
import { formatCompactNumber, formatDate } from "@/lib/format";
import { dedupeSnapshotSurfaceWarnings, resolveSnapshotSurfaceMode, type SnapshotSurfaceCapabilities, type SnapshotSurfaceWarning } from "@/lib/snapshot-surface";
import type { FinancialPayload } from "@/lib/types";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);
const QUARTERLY_FORMS = new Set(["10-Q", "6-K"]);
const POSITIVE_COLOR = "var(--positive)";
const NEGATIVE_COLOR = "var(--negative)";
const TOTAL_COLOR = POSITIVE_COLOR;
const CAPABILITIES: SnapshotSurfaceCapabilities = {
  supports_selected_period: true,
  supports_compare_mode: true,
  supports_trend_mode: true,
};
type PeriodView = "annual" | "quarterly";

type WaterfallDatum = {
  label: string;
  kind: "total" | "delta";
  start: number;
  end: number;
  base: number;
  span: number;
  delta: number;
  fill: string;
};

interface CashFlowWaterfallChartProps {
  financials: FinancialPayload[];
  chartState?: SharedFinancialChartState;
}

export function CashFlowWaterfallChart({ financials, chartState }: CashFlowWaterfallChartProps) {
  const [periodView, setPeriodView] = useState<PeriodView>("annual");
  const useSharedState = Boolean(chartState);

  const annualStatements = useMemo(
    () => financials.filter((statement) => ANNUAL_FORMS.has(statement.filing_type)),
    [financials]
  );
  const quarterlyStatements = useMemo(
    () => financials.filter((statement) => QUARTERLY_FORMS.has(statement.filing_type)),
    [financials]
  );

  useEffect(() => {
    if (useSharedState) {
      return;
    }
    if (periodView === "annual" && annualStatements.length > 0) {
      return;
    }
    if (periodView === "quarterly" && quarterlyStatements.length > 0) {
      return;
    }
    if (annualStatements.length > 0) {
      setPeriodView("annual");
      return;
    }
    if (quarterlyStatements.length > 0) {
      setPeriodView("quarterly");
    }
  }, [annualStatements.length, periodView, quarterlyStatements.length, useSharedState]);

  const focusStatement = useMemo(() => {
    if (chartState?.selectedFinancial) {
      return chartState.selectedFinancial;
    }
    const statementSet = periodView === "annual" ? annualStatements : quarterlyStatements;
    return statementSet[0] ?? annualStatements[0] ?? quarterlyStatements[0] ?? financials[0] ?? null;
  }, [annualStatements, chartState?.selectedFinancial, financials, periodView, quarterlyStatements]);
  const comparisonStatement = chartState?.comparisonFinancial ?? null;

  const chartData = useMemo(() => buildWaterfallData(focusStatement), [focusStatement]);
  const trendData = useMemo(() => buildTrendData(financials), [financials]);
  const warnings = useMemo(() => buildWarnings(financials, comparisonStatement), [comparisonStatement, financials]);
  const mode = resolveSnapshotSurfaceMode({
    comparisonAvailable: comparisonStatement !== null,
    trendAvailable: trendData.length > 1,
    capabilities: CAPABILITIES,
  });

  if (!focusStatement || chartData.length === 0) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 280 }}>
        <div className="grid-empty-kicker">Cash flow bridge</div>
        <div className="grid-empty-title">No cash flow waterfall available</div>
        <div className="grid-empty-copy">Refresh cached filings to load operating cash flow, capex, and capital allocation inputs.</div>
      </div>
    );
  }

  return (
    <div className="cash-waterfall-shell">
      <SnapshotSurfaceStatus capabilities={CAPABILITIES} mode={mode} warnings={warnings} />

      {chartState ? (
        <FinancialChartStateBar state={chartState} />
      ) : (
        <div className="cash-waterfall-toolbar">
          <div className="cash-waterfall-toggle-group">
            <button
              type="button"
              className={`chart-chip${periodView === "annual" ? " chart-chip-active" : ""}`}
              onClick={() => setPeriodView("annual")}
              disabled={!annualStatements.length}
            >
              Annual
            </button>
            <button
              type="button"
              className={`chart-chip${periodView === "quarterly" ? " chart-chip-active" : ""}`}
              onClick={() => setPeriodView("quarterly")}
              disabled={!quarterlyStatements.length}
            >
              Quarterly
            </button>
          </div>
          <span className="pill">{periodView === "annual" ? annualStatements.length : quarterlyStatements.length} cached {periodView} filings</span>
        </div>
      )}

      <div className="cash-waterfall-meta">
        <span className="pill">Period {formatDate(focusStatement.period_end)}</span>
        <span className="pill">Form {focusStatement.filing_type}</span>
        <span className="pill">Revenue {formatCompactNumber(focusStatement.revenue)}</span>
        <span className="pill">Operating CF {formatCompactNumber(focusStatement.operating_cash_flow)}</span>
        <span className="pill">FCF {formatCompactNumber(focusStatement.free_cash_flow)}</span>
      </div>

      {comparisonStatement ? (
        <div className="cash-waterfall-meta">
          <span className="pill tone-gold">Revenue Δ {formatSignedCompactDelta(difference(focusStatement.revenue, comparisonStatement.revenue))}</span>
          <span className="pill tone-gold">Operating CF Δ {formatSignedCompactDelta(difference(focusStatement.operating_cash_flow, comparisonStatement.operating_cash_flow))}</span>
          <span className="pill tone-gold">FCF Δ {formatSignedCompactDelta(difference(focusStatement.free_cash_flow, comparisonStatement.free_cash_flow))}</span>
          <span className="pill tone-gold">Buybacks Δ {formatSignedCompactDelta(difference(focusStatement.share_buybacks, comparisonStatement.share_buybacks))}</span>
          <span className="pill tone-gold">Dividends Δ {formatSignedCompactDelta(difference(focusStatement.dividends, comparisonStatement.dividends))}</span>
        </div>
      ) : null}

      <div className="cash-waterfall-chart-shell">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 12, right: 24, left: 4, bottom: 26 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_COLOR} vertical={false} />
            <XAxis dataKey="label" stroke={CHART_AXIS_COLOR} tick={chartTick()} angle={-14} textAnchor="end" height={58} />
            <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={formatAxisNumber} width={74} />
            <ReferenceLine y={0} stroke="var(--panel-border)" />
            <Tooltip content={<WaterfallTooltip />} />
            <Bar dataKey="base" stackId="waterfall" fill="transparent" stroke="transparent" />
            <Bar dataKey="span" stackId="waterfall" radius={[2, 2, 0, 0]}>
              {chartData.map((entry) => (
                <Cell key={entry.label} fill={entry.fill} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {trendData.length > 1 ? (
        <div className="segment-chart-card" style={{ display: "grid", gap: 10 }}>
          <div className="segment-section-title">Cash Flow Trend</div>
          <div className="segment-section-subtitle">Trend mode shows revenue, operating cash flow, and free cash flow across the visible filing window.</div>
          <div style={{ width: "100%", height: 260 }}>
            <ResponsiveContainer>
              <BarChart data={trendData} margin={{ top: 12, right: 18, left: 6, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_COLOR} vertical={false} />
                <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick()} interval={0} angle={-12} textAnchor="end" height={56} />
                <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={formatAxisNumber} width={74} />
                <Tooltip />
                <Bar dataKey="revenue" name="Revenue" fill="var(--accent)" radius={[2, 2, 0, 0]} />
                <Bar dataKey="operatingCashFlow" name="Operating CF" fill="var(--positive)" radius={[2, 2, 0, 0]} />
                <Bar dataKey="freeCashFlow" name="Free Cash Flow" fill="var(--warning)" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function WaterfallTooltip({
  active,
  payload,
  label
}: {
  active?: boolean;
  payload?: Array<{ payload?: WaterfallDatum }>;
  label?: string;
}) {
  if (!active || !payload?.length || !payload[0]?.payload) {
    return null;
  }

  const point = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{label}</div>
      <TooltipRow label={point.kind === "total" ? "Total" : "Change"} value={formatSignedCompact(point.kind === "total" ? point.end : point.delta)} color={point.fill} />
      <TooltipRow label="Running Total" value={formatSignedCompact(point.end)} color={TOTAL_COLOR} />
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

function buildWaterfallData(statement: FinancialPayload | null): WaterfallDatum[] {
  if (!statement) {
    return [];
  }

  const revenue = asNumber(statement.revenue);
  const operatingCashFlow = asNumber(statement.operating_cash_flow);
  const capex = asPositiveNumber(statement.capex) ?? deriveCapex(statement);
  const acquisitions = asPositiveNumber(statement.acquisitions) ?? 0;
  const debtChanges = asNumber(statement.debt_changes) ?? 0;
  const dividends = asPositiveNumber(statement.dividends) ?? 0;
  const shareBuybacks = asPositiveNumber(statement.share_buybacks) ?? 0;
  const freeCashFlow = asNumber(statement.free_cash_flow) ?? (operatingCashFlow !== null && capex !== null ? operatingCashFlow - capex : null);

  if (revenue === null && operatingCashFlow === null && freeCashFlow === null) {
    return [];
  }

  const items: WaterfallDatum[] = [];
  let runningTotal = 0;

  if (revenue !== null) {
    items.push(totalStep("Revenue", revenue));
    runningTotal = revenue;
  }

  const ocfBridge = operatingCashFlow === null ? null : operatingCashFlow - runningTotal;
  if (ocfBridge !== null) {
    items.push(deltaStep("OCF Bridge", runningTotal, ocfBridge));
    runningTotal += ocfBridge;
    items.push(totalStep("Operating CF", runningTotal));
  }

  if (capex !== null) {
    items.push(deltaStep("Capex", runningTotal, -capex));
    runningTotal -= capex;
  }

  if (freeCashFlow !== null) {
    items.push(totalStep("Free Cash Flow", freeCashFlow));
    runningTotal = freeCashFlow;
  }

  if (acquisitions !== 0) {
    items.push(deltaStep("Acquisitions", runningTotal, -acquisitions));
    runningTotal -= acquisitions;
  }
  if (debtChanges !== 0) {
    items.push(deltaStep("Debt Changes", runningTotal, debtChanges));
    runningTotal += debtChanges;
  }
  if (dividends !== 0) {
    items.push(deltaStep("Dividends", runningTotal, -dividends));
    runningTotal -= dividends;
  }
  if (shareBuybacks !== 0) {
    items.push(deltaStep("Buybacks", runningTotal, -shareBuybacks));
    runningTotal -= shareBuybacks;
  }

  items.push(totalStep("Ending Cash Proxy", runningTotal));
  return items;
}

function totalStep(label: string, value: number): WaterfallDatum {
  return {
    label,
    kind: "total",
    start: 0,
    end: value,
    base: Math.min(0, value),
    span: Math.abs(value),
    delta: value,
    fill: value >= 0 ? TOTAL_COLOR : NEGATIVE_COLOR
  };
}

function deltaStep(label: string, start: number, delta: number): WaterfallDatum {
  const end = start + delta;
  return {
    label,
    kind: "delta",
    start,
    end,
    base: Math.min(start, end),
    span: Math.abs(delta),
    delta,
    fill: delta >= 0 ? POSITIVE_COLOR : NEGATIVE_COLOR
  };
}

function deriveCapex(statement: FinancialPayload): number | null {
  if (statement.operating_cash_flow === null || statement.free_cash_flow === null) {
    return null;
  }
  return Math.abs(statement.operating_cash_flow - statement.free_cash_flow);
}

function asNumber(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asPositiveNumber(value: number | null | undefined): number | null {
  const number = asNumber(value);
  if (number === null) {
    return null;
  }
  return Math.abs(number);
}

function formatAxisNumber(value: number): string {
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

function formatSignedCompact(value: number): string {
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 2,
    signDisplay: "exceptZero"
  }).format(value);
}

function buildTrendData(financials: FinancialPayload[]) {
  return [...financials]
    .reverse()
    .map((statement) => ({
      period: `${statement.filing_type} ${formatDate(statement.period_end)}`,
      revenue: statement.revenue,
      operatingCashFlow: statement.operating_cash_flow,
      freeCashFlow: statement.free_cash_flow,
    }));
}

function buildWarnings(financials: FinancialPayload[], comparisonStatement: FinancialPayload | null): SnapshotSurfaceWarning[] {
  const warnings: SnapshotSurfaceWarning[] = [];
  if (comparisonStatement && !financials.some((statement) => statement.period_end === comparisonStatement.period_end && statement.filing_type === comparisonStatement.filing_type)) {
    warnings.push({
      code: "cash_flow_compare_missing",
      label: "Comparison period unavailable",
      detail: "The selected comparison period is not visible in the current cash flow window, so compare mode falls back to the focused filing only.",
      tone: "warning",
    });
  }
  if (financials.length < 2) {
    warnings.push({
      code: "cash_flow_trend_sparse",
      label: "Sparse cash flow history",
      detail: "Only one filing is visible, so trend mode falls back to the selected-period bridge.",
      tone: "info",
    });
  }
  return dedupeSnapshotSurfaceWarnings(warnings);
}
