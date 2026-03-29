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

import { CHART_AXIS_COLOR, CHART_GRID_COLOR, chartTick } from "@/lib/chart-theme";
import { formatCompactNumber, formatDate } from "@/lib/format";
import type { FinancialPayload } from "@/lib/types";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);
const QUARTERLY_FORMS = new Set(["10-Q", "6-K"]);
const POSITIVE_COLOR = "var(--positive)";
const NEGATIVE_COLOR = "var(--negative)";
const TOTAL_COLOR = POSITIVE_COLOR;
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

export function CashFlowWaterfallChart({ financials }: { financials: FinancialPayload[] }) {
  const [periodView, setPeriodView] = useState<PeriodView>("annual");

  const annualStatements = useMemo(
    () => financials.filter((statement) => ANNUAL_FORMS.has(statement.filing_type)),
    [financials]
  );
  const quarterlyStatements = useMemo(
    () => financials.filter((statement) => QUARTERLY_FORMS.has(statement.filing_type)),
    [financials]
  );

  useEffect(() => {
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
  }, [annualStatements.length, periodView, quarterlyStatements.length]);

  const latestStatement = useMemo(() => {
    const statementSet = periodView === "annual" ? annualStatements : quarterlyStatements;
    return statementSet[0] ?? annualStatements[0] ?? quarterlyStatements[0] ?? financials[0] ?? null;
  }, [annualStatements, financials, periodView, quarterlyStatements]);

  const chartData = useMemo(() => buildWaterfallData(latestStatement), [latestStatement]);

  if (!latestStatement || chartData.length === 0) {
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

      <div className="cash-waterfall-meta">
        <span className="pill">Period {formatDate(latestStatement.period_end)}</span>
        <span className="pill">Form {latestStatement.filing_type}</span>
        <span className="pill">Revenue {formatCompactNumber(latestStatement.revenue)}</span>
        <span className="pill">FCF {formatCompactNumber(latestStatement.free_cash_flow)}</span>
      </div>

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
