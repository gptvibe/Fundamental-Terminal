"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ChartSourceBadges } from "@/components/charts/chart-framework";
import { FinancialChartStateBar } from "@/components/charts/financial-chart-state-bar";
import { InteractiveChartFrame } from "@/components/charts/interactive-chart-frame";
import { PanelEmptyState } from "@/components/company/panel-empty-state";
import { useChartPreferences } from "@/hooks/use-chart-preferences";
import { formatChartTimeframeLabel, type ChartType } from "@/lib/chart-capabilities";
import { RANGE_TIMEFRAME_OPTIONS, STACKED_TIME_SERIES_CHART_TYPE_OPTIONS } from "@/lib/chart-expansion-presets";
import type { FinancialPayload } from "@/lib/types";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { normalizeExportFileStem } from "@/lib/export";
import { difference, findPointForStatement, formatSignedCompactDelta, type SharedFinancialChartState } from "@/lib/financial-chart-state";
import { buildWindowedSeries } from "@/lib/chart-windowing";
import { buildOperatingCostSeries, type OperatingCostSeriesRow } from "@/lib/financial-chart-transforms";
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
  const { chartType, timeframeMode, setChartType, setTimeframeMode } = useChartPreferences({
    chartFamily: "operating-cost-structure",
    defaultChartType: "line",
    defaultTimeframeMode: "max",
    allowedChartTypes: STACKED_TIME_SERIES_CHART_TYPE_OPTIONS,
    allowedTimeframeModes: RANGE_TIMEFRAME_OPTIONS,
  });

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
  const selectedChartType = chartType ?? "line";
  const selectedTimeframeMode = timeframeMode ?? "max";
  const source = useSharedState ? financials : periodView === "annual" ? annualStatements : quarterlyStatements;
  const costSeries = useMemo(() => buildOperatingCostSeries(source, activeCadence), [activeCadence, source]);
  const data = useMemo(
    () =>
      buildWindowedSeries(costSeries, {
        timeframeMode: selectedTimeframeMode,
        getDate: (point) => point.periodEnd,
      }),
    [costSeries, selectedTimeframeMode]
  );
  const focusPoint = useMemo(() => findPointForStatement(data, selectedFinancial), [data, selectedFinancial]);
  const comparisonPoint = useMemo(() => findPointForStatement(data, comparisonFinancial), [comparisonFinancial, data]);
  const latest = data.at(-1) ?? null;
  const summaryPoint = focusPoint ?? latest;
  const exportRows = useMemo(
    () => data.map((row) => ({ period: row.period, period_end: row.periodEnd, sga: row.sga, research_and_development: row.researchAndDevelopment, stock_based_compensation: row.stockBasedCompensation, interest_expense: row.interestExpense, income_tax_expense: row.incomeTaxExpense })),
    [data]
  );
  const badgeArea = data.length ? (
    <ChartSourceBadges
      badges={[
        { label: "Periods", value: String(data.length) },
        { label: "Cadence", value: activeCadence.toUpperCase() },
        { label: "Window", value: formatChartTimeframeLabel(selectedTimeframeMode) },
        { label: "Source", value: "Cached filing history" },
      ]}
    />
  ) : null;
  const resetDisabled = selectedChartType === "line" && selectedTimeframeMode === "max";

  return (
    <InteractiveChartFrame
      title="Operating cost structure"
      subtitle={data.length ? `${data.length} visible periods of operating cost history.` : "Awaiting cost structure history"}
      inspectorTitle="Operating cost structure"
      inspectorSubtitle="SG&A, R&D, stock-based compensation, interest expense, and tax expense across the visible filing history."
      hideInlineHeader
      badgeArea={badgeArea}
      controlState={{
        datasetKind: "stacked_time_series",
        chartType: selectedChartType,
        chartTypeOptions: STACKED_TIME_SERIES_CHART_TYPE_OPTIONS,
        onChartTypeChange: setChartType,
        timeframeMode: selectedTimeframeMode,
        timeframeModeOptions: RANGE_TIMEFRAME_OPTIONS,
        onTimeframeModeChange: setTimeframeMode,
      }}
      annotations={[
        { label: "SG&A", color: "var(--accent)" },
        { label: "R&D", color: "var(--warning)" },
        { label: "Stock-Based Comp", color: "var(--positive)" },
        { label: "Interest Expense", color: "var(--negative)" },
        { label: "Income Tax Expense", color: "#A855F7" },
      ]}
      footer={(
        <div className="chart-inspector-footer-stack">
          <div className="chart-inspector-footer-pill-row">
            <span className="pill">Visible periods {data.length}</span>
            <span className="pill">Cadence {activeCadence.toUpperCase()}</span>
            <span className="pill">Window {formatChartTimeframeLabel(selectedTimeframeMode)}</span>
            <span className="pill">Source: cached filing history</span>
          </div>
        </div>
      )}
      stageState={
        data.length
          ? undefined
          : {
              kind: "empty",
              kicker: "Operating cost structure",
              title: "No operating cost history yet",
              message: "This chart appears once cached filings include SG&A, R&D, stock-based compensation, interest expense, or tax expense history.",
            }
      }
      exportState={{
        pngFileName: `${normalizeExportFileStem("operating-cost-structure", "financials")}.png`,
        csvFileName: `${normalizeExportFileStem("operating-cost-structure", "financials")}.csv`,
        csvRows: exportRows,
      }}
      resetState={{
        onReset: () => {
          setChartType("line");
          setTimeframeMode("max");
        },
        disabled: resetDisabled,
      }}
      renderChart={({ expanded }) =>
        data.length ? (
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

            {renderOperatingCostChart({
              chartType: selectedChartType,
              data,
              expanded,
              focusPoint,
              comparisonPoint,
            })}
          </div>
        ) : (
          <PanelEmptyState message="No SG&A, R&D, stock-based compensation, interest, or tax expense history is available yet." />
        )
      }
    />
  );
}

function renderOperatingCostChart({
  chartType,
  data,
  expanded,
  focusPoint,
  comparisonPoint,
}: {
  chartType: ChartType;
  data: OperatingCostSeriesRow[];
  expanded: boolean;
  focusPoint: OperatingCostSeriesRow | null;
  comparisonPoint: OperatingCostSeriesRow | null;
}) {
  const margin = { top: 10, right: expanded ? 20 : 14, left: 4, bottom: 8 };
  const strokeWidth = expanded ? 2.6 : 2.2;
  const chartShellClassName = expanded ? "financial-chart-shell financial-chart-shell-expanded" : "financial-chart-shell financial-chart-shell-large";

  return (
    <div className={chartShellClassName}>
      <ResponsiveContainer>
        {chartType === "area" ? (
          <AreaChart data={data} margin={margin}>
            <SharedOperatingCostChrome expanded={expanded} focusPoint={focusPoint} comparisonPoint={comparisonPoint} />
            <Area type="monotone" dataKey="sga" name="SG&A" stackId="operating-costs" stroke="var(--accent)" fill="color-mix(in srgb, var(--accent) 18%, transparent)" strokeWidth={strokeWidth} connectNulls isAnimationActive={false} />
            <Area type="monotone" dataKey="researchAndDevelopment" name="R&D" stackId="operating-costs" stroke="var(--warning)" fill="color-mix(in srgb, var(--warning) 16%, transparent)" strokeWidth={strokeWidth} connectNulls isAnimationActive={false} />
            <Area type="monotone" dataKey="stockBasedCompensation" name="Stock-Based Comp" stackId="operating-costs" stroke="var(--positive)" fill="color-mix(in srgb, var(--positive) 16%, transparent)" strokeWidth={strokeWidth} connectNulls isAnimationActive={false} />
            <Area type="monotone" dataKey="interestExpense" name="Interest Expense" stackId="operating-costs" stroke="var(--negative)" fill="color-mix(in srgb, var(--negative) 14%, transparent)" strokeWidth={strokeWidth} connectNulls isAnimationActive={false} />
            <Area type="monotone" dataKey="incomeTaxExpense" name="Income Tax Expense" stackId="operating-costs" stroke="#A855F7" fill="color-mix(in srgb, #A855F7 14%, transparent)" strokeWidth={strokeWidth} connectNulls isAnimationActive={false} />
          </AreaChart>
        ) : chartType === "stacked_bar" ? (
          <BarChart data={data} margin={margin}>
            <SharedOperatingCostChrome expanded={expanded} focusPoint={focusPoint} comparisonPoint={comparisonPoint} />
            <Bar dataKey="sga" name="SG&A" stackId="operating-costs" fill="var(--accent)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="researchAndDevelopment" name="R&D" stackId="operating-costs" fill="var(--warning)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="stockBasedCompensation" name="Stock-Based Comp" stackId="operating-costs" fill="var(--positive)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="interestExpense" name="Interest Expense" stackId="operating-costs" fill="var(--negative)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="incomeTaxExpense" name="Income Tax Expense" stackId="operating-costs" fill="#A855F7" radius={[3, 3, 0, 0]} isAnimationActive={false} />
          </BarChart>
        ) : chartType === "composed" ? (
          <ComposedChart data={data} margin={margin}>
            <SharedOperatingCostChrome expanded={expanded} focusPoint={focusPoint} comparisonPoint={comparisonPoint} />
            <Bar dataKey="sga" name="SG&A" stackId="operating-costs" fill="color-mix(in srgb, var(--accent) 80%, transparent)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="researchAndDevelopment" name="R&D" stackId="operating-costs" fill="color-mix(in srgb, var(--warning) 80%, transparent)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="stockBasedCompensation" name="Stock-Based Comp" stackId="operating-costs" fill="color-mix(in srgb, var(--positive) 80%, transparent)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
            <Line type="monotone" dataKey="interestExpense" name="Interest Expense" stroke="var(--negative)" strokeWidth={strokeWidth} dot={false} connectNulls isAnimationActive={false} />
            <Line type="monotone" dataKey="incomeTaxExpense" name="Income Tax Expense" stroke="#A855F7" strokeWidth={strokeWidth} dot={false} connectNulls isAnimationActive={false} />
          </ComposedChart>
        ) : (
          <LineChart data={data} margin={margin}>
            <SharedOperatingCostChrome expanded={expanded} focusPoint={focusPoint} comparisonPoint={comparisonPoint} />
            <Line type="monotone" dataKey="sga" name="SG&A" stroke="var(--accent)" strokeWidth={strokeWidth} dot={false} connectNulls isAnimationActive={false} />
            <Line type="monotone" dataKey="researchAndDevelopment" name="R&D" stroke="var(--warning)" strokeWidth={strokeWidth} dot={false} connectNulls isAnimationActive={false} />
            <Line type="monotone" dataKey="stockBasedCompensation" name="Stock-Based Comp" stroke="var(--positive)" strokeWidth={strokeWidth} dot={false} connectNulls isAnimationActive={false} />
            <Line type="monotone" dataKey="interestExpense" name="Interest Expense" stroke="var(--negative)" strokeWidth={strokeWidth} dot={false} connectNulls isAnimationActive={false} />
            <Line type="monotone" dataKey="incomeTaxExpense" name="Income Tax Expense" stroke="#A855F7" strokeWidth={strokeWidth} dot={false} connectNulls isAnimationActive={false} />
          </LineChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

function SharedOperatingCostChrome({
  expanded,
  focusPoint,
  comparisonPoint,
}: {
  expanded: boolean;
  focusPoint: OperatingCostSeriesRow | null;
  comparisonPoint: OperatingCostSeriesRow | null;
}) {
  return (
    <>
      <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
      <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} />
      <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} tickFormatter={(value) => formatCompactNumber(Number(value))} width={82} />
      {comparisonPoint ? <ReferenceLine x={comparisonPoint.period} stroke="var(--warning)" strokeDasharray="4 3" /> : null}
      {focusPoint ? <ReferenceLine x={focusPoint.period} stroke="var(--accent)" strokeDasharray="4 3" /> : null}
      <Tooltip {...RECHARTS_TOOLTIP_PROPS} formatter={(value: number) => formatCompactNumber(value)} />
      <Legend formatter={(value) => <span className="chart-legend-label">{value}</span>} />
    </>
  );
}

