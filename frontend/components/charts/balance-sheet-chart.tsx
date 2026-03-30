"use client";

import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { FinancialChartStateBar } from "@/components/charts/financial-chart-state-bar";
import { PanelEmptyState } from "@/components/company/panel-empty-state";
import { FinancialPayload } from "@/lib/types";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, CHART_LEGEND_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { formatCompactNumber } from "@/lib/format";
import { difference, findPointForStatement, formatSignedCompactDelta, formatStatementAxisLabel, type SharedFinancialChartState } from "@/lib/financial-chart-state";

interface BalanceSheetChartProps {
  financials: FinancialPayload[];
  chartState?: SharedFinancialChartState;
}

export function BalanceSheetChart({ financials, chartState }: BalanceSheetChartProps) {
  const selectedFinancial = chartState?.selectedFinancial ?? null;
  const comparisonFinancial = chartState?.comparisonFinancial ?? null;
  const data = useMemo(
    () =>
      [...financials]
        .reverse()
        .map((item) => ({
          period: formatStatementAxisLabel(item, chartState?.cadence),
          periodEnd: item.period_end,
          filingType: item.filing_type,
          assets: item.total_assets,
          liabilities: item.total_liabilities,
          equity:
            item.total_assets != null && item.total_liabilities != null
              ? item.total_assets - item.total_liabilities
              : null,
        })),
    [chartState?.cadence, financials]
  );
  const focusPoint = useMemo(() => findPointForStatement(data, selectedFinancial), [data, selectedFinancial]);
  const comparisonPoint = useMemo(() => findPointForStatement(data, comparisonFinancial), [comparisonFinancial, data]);
  const latest = data.at(-1) ?? null;
  const summaryPoint = focusPoint ?? latest;

  if (!data.length) {
    return <PanelEmptyState message="No balance-sheet history is available yet." />;
  }

  return (
    <div className="cash-waterfall-shell">
      {chartState ? <FinancialChartStateBar state={chartState} /> : null}

      {summaryPoint ? (
        <div className="cash-waterfall-meta">
          <span className="pill">Assets {formatCompactNumber(summaryPoint.assets)}</span>
          <span className="pill">Liabilities {formatCompactNumber(summaryPoint.liabilities)}</span>
          <span className="pill">Net Assets {formatCompactNumber(summaryPoint.equity)}</span>
        </div>
      ) : null}

      {summaryPoint && comparisonPoint ? (
        <div className="cash-waterfall-meta">
          <span className="pill tone-gold">Assets Δ {formatSignedCompactDelta(difference(summaryPoint.assets, comparisonPoint.assets))}</span>
          <span className="pill tone-gold">Liabilities Δ {formatSignedCompactDelta(difference(summaryPoint.liabilities, comparisonPoint.liabilities))}</span>
          <span className="pill tone-gold">Net Assets Δ {formatSignedCompactDelta(difference(summaryPoint.equity, comparisonPoint.equity))}</span>
        </div>
      ) : null}

      <div style={{ width: "100%", height: 320 }}>
        <ResponsiveContainer>
          <BarChart data={data}>
            <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
            <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
            <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatCompactNumber(Number(value))} />
            {comparisonPoint ? <ReferenceLine x={comparisonPoint.period} stroke="var(--warning)" strokeDasharray="4 3" /> : null}
            {focusPoint ? <ReferenceLine x={focusPoint.period} stroke="var(--accent)" strokeDasharray="4 3" /> : null}
            <Tooltip {...RECHARTS_TOOLTIP_PROPS} formatter={(value: number) => formatCompactNumber(value)} />
            <Legend formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}>{value}</span>} />
            <Bar dataKey="assets" fill="var(--accent)" radius={[2, 2, 0, 0]} />
            <Bar dataKey="liabilities" fill="var(--warning)" radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
