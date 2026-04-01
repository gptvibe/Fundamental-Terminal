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

import { ChartSourceBadges } from "@/components/charts/chart-framework";
import { FinancialChartStateBar } from "@/components/charts/financial-chart-state-bar";
import { InteractiveChartFrame } from "@/components/charts/interactive-chart-frame";
import { PanelEmptyState } from "@/components/company/panel-empty-state";
import type { FinancialPayload } from "@/lib/types";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { normalizeExportFileStem } from "@/lib/export";
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
  const data = useMemo(() => buildLiquiditySeries(statements, chartState?.effectiveCadence ?? chartState?.cadence), [chartState?.cadence, chartState?.effectiveCadence, statements]);
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
  const exportRows = useMemo(
    () => data.map((row) => ({ period: row.period, period_end: row.periodEnd, current_assets: row.currentAssets, current_liabilities: row.currentLiabilities, current_ratio: row.currentRatio, working_capital: row.workingCapital, retained_earnings: row.retainedEarnings })),
    [data]
  );
  const badgeArea = data.length ? (
    <ChartSourceBadges
      badges={[
        { label: "Periods", value: String(data.length) },
        { label: "Focus", value: summaryPoint ? formatDate(summaryPoint.periodEnd) : "Latest" },
        { label: "Source", value: "Cached filing history" },
      ]}
    />
  ) : null;

  return (
    <InteractiveChartFrame
      title="Liquidity and capital"
      subtitle={data.length ? `${data.length} periods of liquidity and retained-earnings history.` : "Awaiting liquidity history"}
      inspectorTitle="Liquidity and capital"
      inspectorSubtitle="Current assets, current liabilities, current ratio, working capital, and retained earnings across the visible filing history."
      hideInlineHeader
      badgeArea={badgeArea}
      annotations={[
        { label: "Current Assets", color: "var(--accent)" },
        { label: "Current Liabilities", color: "var(--warning)" },
        { label: "Current Ratio", color: "var(--positive)" },
        { label: "Retained Earnings", color: "#64D2FF" },
      ]}
      footer={(
        <div className="chart-inspector-footer-stack">
          <div className="chart-inspector-footer-pill-row">
            <span className="pill">Visible periods {data.length}</span>
            <span className="pill">Source: cached filing history</span>
          </div>
        </div>
      )}
      stageState={
        data.length
          ? undefined
          : {
              kind: "empty",
              kicker: "Liquidity and capital",
              title: "No liquidity or retained earnings history yet",
              message: "This chart appears once cached filings include liquidity and retained-earnings fields.",
            }
      }
      exportState={{
        pngFileName: `${normalizeExportFileStem("liquidity-capital", "financials")}.png`,
        csvFileName: `${normalizeExportFileStem("liquidity-capital", "financials")}.csv`,
        csvRows: exportRows,
      }}
      renderChart={({ expanded }) =>
        data.length ? (
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
                <div className="liquidity-chart-shell" style={expanded ? { minHeight: 360 } : undefined}>
                  <ResponsiveContainer>
                    <ComposedChart data={data} margin={{ top: 10, right: 18, left: 4, bottom: 8 }}>
                      <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                      <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} />
                      <YAxis
                        yAxisId="values"
                        stroke={CHART_AXIS_COLOR}
                        tick={chartTick(expanded ? 11 : 10)}
                        tickFormatter={(value) => formatCompactNumber(Number(value))}
                        width={74}
                      />
                      <YAxis
                        yAxisId="ratio"
                        orientation="right"
                        stroke={CHART_AXIS_COLOR}
                        tick={chartTick(expanded ? 11 : 10)}
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
                        strokeWidth={expanded ? 2.8 : 2.4}
                        dot={{ r: expanded ? 4 : 3, fill: "var(--positive)" }}
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
                <div className="liquidity-chart-shell" style={expanded ? { minHeight: 320 } : undefined}>
                  {hasRetainedSeries ? (
                    <ResponsiveContainer>
                      <ComposedChart data={retainedSeries} margin={{ top: 10, right: 12, left: 4, bottom: 8 }}>
                        <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                        <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} />
                        <YAxis
                          stroke={CHART_AXIS_COLOR}
                          tick={chartTick(expanded ? 11 : 10)}
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
                          strokeWidth={expanded ? 2.8 : 2.4}
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
        ) : (
          <PanelEmptyState message="No liquidity or retained earnings history is available in cached filings yet." />
        )
      }
    />
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
  cadence?: "annual" | "quarterly" | "ttm" | "reported"
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




















