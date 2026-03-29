"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { FinancialPayload } from "@/lib/types";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, CHART_LEGEND_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { formatCompactNumber } from "@/lib/format";

export function BalanceSheetChart({ financials }: { financials: FinancialPayload[] }) {
  const data = [...financials]
    .reverse()
    .map((item) => ({
      period: item.period_end.slice(0, 10),
      assets: item.total_assets,
      liabilities: item.total_liabilities
    }));

  return (
    <div style={{ width: "100%", height: 320 }}>
      <ResponsiveContainer>
        <BarChart data={data}>
          <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
          <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
          <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatCompactNumber(Number(value))} />
          <Tooltip {...RECHARTS_TOOLTIP_PROPS} formatter={(value: number) => formatCompactNumber(value)} />
          <Legend formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}>{value}</span>} />
          <Bar dataKey="assets" fill="var(--accent)" radius={[2, 2, 0, 0]} />
          <Bar dataKey="liabilities" fill="var(--warning)" radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
