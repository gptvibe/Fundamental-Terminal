"use client";

import { useMemo } from "react";
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { FinancialChartStateBar } from "@/components/charts/financial-chart-state-bar";
import { PanelEmptyState } from "@/components/company/panel-empty-state";
import type { FinancialPayload } from "@/lib/types";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, CHART_LEGEND_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { formatCompactNumber, formatPercent } from "@/lib/format";
import { difference, findPointForStatement, formatSignedCompactDelta, formatSignedPointDelta, formatStatementAxisLabel, type SharedFinancialChartState } from "@/lib/financial-chart-state";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);

interface ShareDilutionTrackerChartProps {
  financials: FinancialPayload[];
  chartState?: SharedFinancialChartState;
}

export function ShareDilutionTrackerChart({ financials, chartState }: ShareDilutionTrackerChartProps) {
  const selectedFinancial = chartState?.selectedFinancial ?? null;
  const comparisonFinancial = chartState?.comparisonFinancial ?? null;
  const history = useMemo(() => selectShareHistory(financials, !chartState), [chartState, financials]);
  const data = useMemo(
    () => history.map((statement, index) => {
      const previous = history[index - 1] ?? null;
      return {
        period: formatStatementAxisLabel(statement, chartState?.cadence),
        periodEnd: statement.period_end,
        filingType: statement.filing_type,
        shares: statement.shares_outstanding,
        dilutionRate: growthRate(statement.shares_outstanding, previous?.shares_outstanding ?? null),
        shareBuybacks: statement.share_buybacks,
        dividends: statement.dividends,
      };
    }),
    [chartState?.cadence, history]
  );
  const focusPoint = useMemo(() => findPointForStatement(data, selectedFinancial), [data, selectedFinancial]);
  const comparisonPoint = useMemo(() => findPointForStatement(data, comparisonFinancial), [comparisonFinancial, data]);
  const summaryPoint = focusPoint ?? data.at(-1) ?? null;

  if (!history.length) {
    return <PanelEmptyState message="No shares outstanding history is available in the cached filings yet." />;
  }

  return (
    <div className="cash-waterfall-shell">
      {chartState ? <FinancialChartStateBar state={chartState} /> : null}

      {summaryPoint ? (
        <div className="cash-waterfall-meta">
          <span className="pill">Shares {formatCompactNumber(summaryPoint.shares)}</span>
          <span className="pill">Dilution {formatPercent(summaryPoint.dilutionRate)}</span>
          <span className="pill">Buybacks {formatCompactNumber(summaryPoint.shareBuybacks)}</span>
          <span className="pill">Dividends {formatCompactNumber(summaryPoint.dividends)}</span>
        </div>
      ) : null}

      {summaryPoint && comparisonPoint ? (
        <div className="cash-waterfall-meta">
          <span className="pill tone-gold">Shares Δ {formatSignedCompactDelta(difference(summaryPoint.shares, comparisonPoint.shares))}</span>
          <span className="pill tone-gold">Dilution Δ {formatSignedPointDelta(difference(summaryPoint.dilutionRate, comparisonPoint.dilutionRate) == null ? null : difference(summaryPoint.dilutionRate, comparisonPoint.dilutionRate)! * 100)}</span>
          <span className="pill tone-gold">Buybacks Δ {formatSignedCompactDelta(difference(summaryPoint.shareBuybacks, comparisonPoint.shareBuybacks))}</span>
          <span className="pill tone-gold">Dividends Δ {formatSignedCompactDelta(difference(summaryPoint.dividends, comparisonPoint.dividends))}</span>
        </div>
      ) : null}

      <div style={{ width: "100%", height: 340 }}>
        <ResponsiveContainer>
          <ComposedChart data={data} margin={{ top: 10, right: 14, left: 4, bottom: 0 }}>
            <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
            <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
            <YAxis
              yAxisId="shares"
              stroke={CHART_AXIS_COLOR}
              tick={chartTick()}
              tickFormatter={(value) => formatCompactNumber(Number(value))}
              width={72}
            />
            <YAxis
              yAxisId="dilution"
              orientation="right"
              stroke={CHART_AXIS_COLOR}
              tick={chartTick()}
              tickFormatter={(value) => formatPercent(Number(value))}
              width={62}
            />
            {comparisonPoint ? <ReferenceLine x={comparisonPoint.period} yAxisId="shares" stroke="var(--warning)" strokeDasharray="4 3" /> : null}
            {focusPoint ? <ReferenceLine x={focusPoint.period} yAxisId="shares" stroke="var(--accent)" strokeDasharray="4 3" /> : null}
            <Tooltip
              {...RECHARTS_TOOLTIP_PROPS}
              formatter={(value: number, name: string) => {
                if (name === "Shares Outstanding") {
                  return formatCompactNumber(value);
                }
                return formatPercent(value);
              }}
            />
            <Legend formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}>{value}</span>} />
            <Bar yAxisId="shares" dataKey="shares" name="Shares Outstanding" fill="var(--accent)" radius={[2, 2, 0, 0]} />
            <Line
              yAxisId="dilution"
              type="monotone"
              dataKey="dilutionRate"
              name="Dilution Rate"
              stroke="var(--warning)"
              strokeWidth={2.4}
              dot={{ r: 3, fill: "var(--warning)" }}
              activeDot={{ r: 5, fill: "var(--warning)", stroke: "var(--panel)", strokeWidth: 2 }}
              connectNulls
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function selectShareHistory(financials: FinancialPayload[], preferAnnual: boolean): FinancialPayload[] {
  const annualStatements = financials.filter((statement) => ANNUAL_FORMS.has(statement.filing_type) && statement.shares_outstanding !== null);
  const source = preferAnnual && annualStatements.length >= 2 ? annualStatements : financials.filter((statement) => statement.shares_outstanding !== null);

  return [...source].sort((left, right) => Date.parse(left.period_end) - Date.parse(right.period_end));
}

function growthRate(current: number | null, previous: number | null): number | null {
  if (current === null || previous === null || previous === 0) {
    return null;
  }
  return (current - previous) / Math.abs(previous);
}
