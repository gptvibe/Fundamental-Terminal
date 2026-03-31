"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { FinancialChartStateBar } from "@/components/charts/financial-chart-state-bar";
import { PanelEmptyState } from "@/components/company/panel-empty-state";
import type { FinancialPayload } from "@/lib/types";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, CHART_LEGEND_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { difference, findPointForStatement, formatSignedCompactDelta, type SharedFinancialChartState } from "@/lib/financial-chart-state";
import { buildOperatingCostSeries } from "@/lib/financial-chart-transforms";
import { formatCompactNumber, formatDate } from "@/lib/format";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);
const QUARTERLY_FORMS = new Set(["10-Q", "6-K"]);

type PeriodView = "annual" | "quarterly";

interface OperatingCostStructureChartProps {
  financials: FinancialPayload[];
  chartState?: SharedFinancialChartState;
}

export function OperatingCostStructureChart({ financials, chartState }: OperatingCostStructureChartProps) {
  const [periodView, setPeriodView] = useState<PeriodView>("annual");
  const selectedFinancial = chartState?.selectedFinancial ?? null;
  const comparisonFinancial = chartState?.comparisonFinancial ?? null;
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

  const activeCadence: "annual" | "quarterly" | "ttm" | "reported" = useSharedState
    ? chartState?.effectiveCadence ?? chartState?.cadence ?? "annual"
    : periodView;
  const source = useSharedState ? financials : periodView === "annual" ? annualStatements : quarterlyStatements;
  const data = useMemo(() => buildOperatingCostSeries(source, activeCadence), [activeCadence, source]);
  const focusPoint = useMemo(() => findPointForStatement(data, selectedFinancial), [data, selectedFinancial]);
  const comparisonPoint = useMemo(() => findPointForStatement(data, comparisonFinancial), [comparisonFinancial, data]);
  const latest = data.at(-1) ?? null;
  const summaryPoint = focusPoint ?? latest;

  if (!data.length) {
    return <PanelEmptyState message="No SG&A, R&D, stock-based compensation, interest, or tax expense history is available yet." />;
  }

  return (
    <div className="cash-waterfall-shell">
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
          <span className="pill">{source.length} cached {periodView} filings</span>
        </div>
      )}

      {summaryPoint ? (
        <div className="cash-waterfall-meta">
          <span className="pill">Period {formatDate(summaryPoint.periodEnd)}</span>
          <span className="pill">SG&A {formatCompactNumber(summaryPoint.sga)}</span>
          <span className="pill">R&D {formatCompactNumber(summaryPoint.researchAndDevelopment)}</span>
          <span className="pill">SBC {formatCompactNumber(summaryPoint.stockBasedCompensation)}</span>
          <span className="pill">Interest {formatCompactNumber(summaryPoint.interestExpense)}</span>
          <span className="pill">Tax {formatCompactNumber(summaryPoint.incomeTaxExpense)}</span>
        </div>
      ) : null}

      {summaryPoint && comparisonPoint ? (
        <div className="cash-waterfall-meta">
          <span className="pill tone-gold">SG&A Δ {formatSignedCompactDelta(difference(summaryPoint.sga, comparisonPoint.sga))}</span>
          <span className="pill tone-gold">R&D Δ {formatSignedCompactDelta(difference(summaryPoint.researchAndDevelopment, comparisonPoint.researchAndDevelopment))}</span>
          <span className="pill tone-gold">SBC Δ {formatSignedCompactDelta(difference(summaryPoint.stockBasedCompensation, comparisonPoint.stockBasedCompensation))}</span>
          <span className="pill tone-gold">Interest Δ {formatSignedCompactDelta(difference(summaryPoint.interestExpense, comparisonPoint.interestExpense))}</span>
          <span className="pill tone-gold">Tax Δ {formatSignedCompactDelta(difference(summaryPoint.incomeTaxExpense, comparisonPoint.incomeTaxExpense))}</span>
        </div>
      ) : null}

      <div style={{ width: "100%", height: 340 }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 10, right: 14, left: 4, bottom: 8 }}>
            <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
            <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
            <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatCompactNumber(Number(value))} width={82} />
            {comparisonPoint ? <ReferenceLine x={comparisonPoint.period} stroke="var(--warning)" strokeDasharray="4 3" /> : null}
            {focusPoint ? <ReferenceLine x={focusPoint.period} stroke="var(--accent)" strokeDasharray="4 3" /> : null}
            <Tooltip {...RECHARTS_TOOLTIP_PROPS} formatter={(value: number) => formatCompactNumber(value)} />
            <Legend formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}>{value}</span>} />
            <Line type="monotone" dataKey="sga" name="SG&A" stroke="var(--accent)" strokeWidth={2.2} dot={false} connectNulls isAnimationActive={false} />
            <Line type="monotone" dataKey="researchAndDevelopment" name="R&D" stroke="var(--warning)" strokeWidth={2.2} dot={false} connectNulls isAnimationActive={false} />
            <Line type="monotone" dataKey="stockBasedCompensation" name="Stock-Based Comp" stroke="var(--positive)" strokeWidth={2.2} dot={false} connectNulls isAnimationActive={false} />
            <Line type="monotone" dataKey="interestExpense" name="Interest Expense" stroke="var(--negative)" strokeWidth={2.2} dot={false} connectNulls isAnimationActive={false} />
            <Line type="monotone" dataKey="incomeTaxExpense" name="Income Tax Expense" stroke="#A855F7" strokeWidth={2.2} dot={false} connectNulls isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

