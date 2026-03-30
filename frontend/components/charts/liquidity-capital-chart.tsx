"use client";

import { useMemo } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { FinancialChartStateBar } from "@/components/charts/financial-chart-state-bar";
import { PanelEmptyState } from "@/components/company/panel-empty-state";
import type { FinancialPayload } from "@/lib/types";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { difference, findPointForStatement, formatSignedCompactDelta, formatSignedMultipleDelta, formatStatementAxisLabel, type SharedFinancialChartState } from "@/lib/financial-chart-state";
import { formatCompactNumber, formatDate } from "@/lib/format";

type LiquidityStatement = FinancialPayload & {
  current_assets?: number | null;
  current_liabilities?: number | null;
  retained_earnings?: number | null;
};

type LiquidityDatum = {
  period: string;
  periodEnd: string;
  filingType: string;
  currentAssets: number | null;
  currentLiabilities: number | null;
  currentRatio: number | null;
  workingCapital: number | null;
  retainedEarnings: number | null;
};

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);

interface LiquidityCapitalChartProps {
  financials: FinancialPayload[];
  chartState?: SharedFinancialChartState;
}

export function LiquidityCapitalChart({ financials, chartState }: LiquidityCapitalChartProps) {
  const selectedFinancial = chartState?.selectedFinancial ?? null;
  const comparisonFinancial = chartState?.comparisonFinancial ?? null;
  const statements = useMemo(
    () => selectLiquidityStatements(financials, !chartState),
    [chartState, financials]
  );
  const data = useMemo(() => buildLiquiditySeries(statements, chartState?.cadence), [chartState?.cadence, statements]);
  const focusPoint = useMemo(() => findPointForStatement(data, selectedFinancial), [data, selectedFinancial]);
  const comparisonPoint = useMemo(() => findPointForStatement(data, comparisonFinancial), [comparisonFinancial, data]);
  const latest = data.length ? data[data.length - 1] : null;
  const summaryPoint = focusPoint ?? latest;
  const retainedSeries = useMemo(() => data.filter((item) => item.retainedEarnings !== null), [data]);
  const focusRetainedPoint = useMemo(() => findPointForStatement(retainedSeries, selectedFinancial), [retainedSeries, selectedFinancial]);
  const comparisonRetainedPoint = useMemo(
    () => findPointForStatement(retainedSeries, comparisonFinancial),
    [comparisonFinancial, retainedSeries]
  );
  const hasRetainedSeries = retainedSeries.length >= 2;

  if (!data.length) {
    return <PanelEmptyState message="No liquidity or retained earnings history is available in cached filings yet." />;
  }

  return (
    <div className="liquidity-shell">
      {chartState ? <FinancialChartStateBar state={chartState} /> : null}

      {summaryPoint ? (
        <div className="liquidity-meta">
          <span>Period {formatDate(summaryPoint.periodEnd)}</span>
          <span>Current ratio {formatRatio(summaryPoint.currentRatio)}</span>
          <span>Working capital {formatCompactNumber(summaryPoint.workingCapital)}</span>
          <span>Retained earnings {formatCompactNumber(summaryPoint.retainedEarnings)}</span>
        </div>
      ) : null}

      {summaryPoint && comparisonPoint ? (
        <div className="liquidity-meta">
          <span>Current ratio Δ {formatSignedMultipleDelta(difference(summaryPoint.currentRatio, comparisonPoint.currentRatio))}</span>
          <span>Working capital Δ {formatSignedCompactDelta(difference(summaryPoint.workingCapital, comparisonPoint.workingCapital))}</span>
          <span>Retained earnings Δ {formatSignedCompactDelta(difference(summaryPoint.retainedEarnings, comparisonPoint.retainedEarnings))}</span>
        </div>
      ) : null}

      <div className="liquidity-grid">
        <div className="liquidity-chart-card">
          <div className="liquidity-chart-title">Current Assets vs Current Liabilities</div>
          <div className="liquidity-chart-subtitle">Liquidity coverage with current ratio overlay.</div>
          <div className="liquidity-chart-shell">
            <ResponsiveContainer>
              <ComposedChart data={data} margin={{ top: 10, right: 18, left: 4, bottom: 8 }}>
                <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
                <YAxis
                  yAxisId="values"
                  stroke={CHART_AXIS_COLOR}
                  tick={chartTick()}
                  tickFormatter={(value) => formatCompactNumber(Number(value))}
                  width={74}
                />
                <YAxis
                  yAxisId="ratio"
                  orientation="right"
                  stroke={CHART_AXIS_COLOR}
                  tick={chartTick()}
                  tickFormatter={(value) => formatRatio(Number(value))}
                  width={66}
                />
                {comparisonPoint ? <ReferenceLine x={comparisonPoint.period} yAxisId="values" stroke="var(--warning)" strokeDasharray="4 3" /> : null}
                {focusPoint ? <ReferenceLine x={focusPoint.period} yAxisId="values" stroke="var(--accent)" strokeDasharray="4 3" /> : null}
                <Tooltip
                  {...RECHARTS_TOOLTIP_PROPS}
                  formatter={(value: number, name: string) => {
                    if (name === "Current Ratio") {
                      return formatRatio(value);
                    }
                    return formatCompactNumber(value);
                  }}
                />
                <Bar yAxisId="values" dataKey="currentAssets" name="Current Assets" fill="var(--accent)" radius={[2, 2, 0, 0]} />
                <Bar
                  yAxisId="values"
                  dataKey="currentLiabilities"
                  name="Current Liabilities"
                  fill="var(--warning)"
                  radius={[2, 2, 0, 0]}
                />
                <Line
                  yAxisId="ratio"
                  type="monotone"
                  dataKey="currentRatio"
                  name="Current Ratio"
                  stroke="var(--positive)"
                  strokeWidth={2.4}
                  dot={{ r: 3, fill: "var(--positive)" }}
                  activeDot={{ r: 5, fill: "var(--positive)", stroke: "var(--panel)", strokeWidth: 2 }}
                  connectNulls
                  isAnimationActive={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="liquidity-chart-card">
          <div className="liquidity-chart-title">Retained Earnings Trend</div>
          <div className="liquidity-chart-subtitle">Capital retention across reported periods.</div>
          <div className="liquidity-chart-shell">
            {hasRetainedSeries ? (
              <ResponsiveContainer>
                <ComposedChart data={retainedSeries} margin={{ top: 10, right: 12, left: 4, bottom: 8 }}>
                  <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                  <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
                  <YAxis
                    stroke={CHART_AXIS_COLOR}
                    tick={chartTick()}
                    tickFormatter={(value) => formatCompactNumber(Number(value))}
                    width={78}
                  />
                  {comparisonRetainedPoint ? <ReferenceLine x={comparisonRetainedPoint.period} stroke="var(--warning)" strokeDasharray="4 3" /> : null}
                  {focusRetainedPoint ? <ReferenceLine x={focusRetainedPoint.period} stroke="var(--accent)" strokeDasharray="4 3" /> : null}
                  <Tooltip
                    {...RECHARTS_TOOLTIP_PROPS}
                    formatter={(value: number) => formatCompactNumber(value)}
                  />
                  <Line
                    type="monotone"
                    dataKey="retainedEarnings"
                    name="Retained Earnings"
                    stroke="#64D2FF"
                    strokeWidth={2.4}
                    dot={false}
                    activeDot={{ r: 4, fill: "#64D2FF", stroke: "var(--panel)", strokeWidth: 2 }}
                    connectNulls
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <div className="liquidity-chart-empty">Retained earnings data is limited for this issuer.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function selectLiquidityStatements(financials: FinancialPayload[], preferAnnual: boolean): LiquidityStatement[] {
  const casted = financials as LiquidityStatement[];
  const annual = casted.filter(
    (statement) =>
      ANNUAL_FORMS.has(statement.filing_type) &&
      (statement.current_assets != null || statement.current_liabilities != null || statement.retained_earnings != null)
  );
  if (preferAnnual && annual.length >= 2) {
    return annual;
  }
  return casted.filter(
    (statement) =>
      statement.current_assets != null || statement.current_liabilities != null || statement.retained_earnings != null
  );
}

function buildLiquiditySeries(
  statements: LiquidityStatement[],
  cadence?: "annual" | "quarterly" | "ttm"
): LiquidityDatum[] {
  return [...statements]
    .sort((left, right) => Date.parse(left.period_end) - Date.parse(right.period_end))
    .map((statement) => {
      const currentAssets = statement.current_assets == null ? null : statement.current_assets;
      const currentLiabilities = statement.current_liabilities == null ? null : statement.current_liabilities;
      const currentRatio = computeRatio(currentAssets, currentLiabilities);
      const workingCapital = computeWorkingCapital(currentAssets, currentLiabilities);
      return {
        period: formatStatementAxisLabel(statement, cadence),
        periodEnd: statement.period_end,
        filingType: statement.filing_type,
        currentAssets,
        currentLiabilities,
        currentRatio,
        workingCapital,
        retainedEarnings: statement.retained_earnings == null ? null : statement.retained_earnings
      };
    });
}

function computeRatio(currentAssets: number | null, currentLiabilities: number | null): number | null {
  if (currentAssets === null || currentLiabilities === null || currentLiabilities === 0) {
    return null;
  }
  return currentAssets / currentLiabilities;
}

function computeWorkingCapital(currentAssets: number | null, currentLiabilities: number | null): number | null {
  if (currentAssets === null || currentLiabilities === null) {
    return null;
  }
  return currentAssets - currentLiabilities;
}

function formatRatio(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "\u2014";
  }
  return `${value.toFixed(2)}x`;
}




















