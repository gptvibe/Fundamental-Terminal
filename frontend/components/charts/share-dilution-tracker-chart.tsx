"use client";

import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { PanelEmptyState } from "@/components/company/panel-empty-state";
import type { FinancialPayload } from "@/lib/types";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, CHART_LEGEND_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { formatCompactNumber, formatPercent } from "@/lib/format";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);

export function ShareDilutionTrackerChart({ financials }: { financials: FinancialPayload[] }) {
  const history = selectShareHistory(financials);
  if (!history.length) {
    return <PanelEmptyState message="No shares outstanding history is available in the cached filings yet." />;
  }

  const data = history.map((statement, index) => {
    const previous = history[index - 1] ?? null;
    return {
      period: new Intl.DateTimeFormat("en-US", { year: "numeric" }).format(new Date(statement.period_end)),
      shares: statement.shares_outstanding,
      dilutionRate: growthRate(statement.shares_outstanding, previous?.shares_outstanding ?? null),
    };
  });

  return (
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
  );
}

function selectShareHistory(financials: FinancialPayload[]): FinancialPayload[] {
  const annualStatements = financials.filter((statement) => ANNUAL_FORMS.has(statement.filing_type) && statement.shares_outstanding !== null);
  const source = annualStatements.length >= 2 ? annualStatements : financials.filter((statement) => statement.shares_outstanding !== null);

  return [...source].sort((left, right) => Date.parse(left.period_end) - Date.parse(right.period_end));
}

function growthRate(current: number | null, previous: number | null): number | null {
  if (current === null || previous === null || previous === 0) {
    return null;
  }
  return (current - previous) / Math.abs(previous);
}
