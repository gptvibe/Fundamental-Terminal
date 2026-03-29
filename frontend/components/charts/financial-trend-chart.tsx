"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { FinancialPayload } from "@/lib/types";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, CHART_LEGEND_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { formatCompactNumber } from "@/lib/format";

export function FinancialTrendChart({ financials }: { financials: FinancialPayload[] }) {
  const data = [...financials]
    .reverse()
    .map((item) => ({
      period: item.period_end.slice(0, 10),
      revenue: item.revenue,
      netIncome: item.net_income,
      freeCashFlow: item.free_cash_flow
    }));

  return (
    <div style={{ width: "100%", height: 320 }}>
      <ResponsiveContainer>
        <LineChart data={data}>
          <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
          <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
          <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatCompactNumber(Number(value))} />
          <Tooltip {...RECHARTS_TOOLTIP_PROPS} formatter={(value: number) => formatCompactNumber(value)} />
          <Legend formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}>{value}</span>} />
          <Line type="monotone" dataKey="revenue" stroke="var(--accent)" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="netIncome" stroke="var(--warning)" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="freeCashFlow" stroke="var(--positive)" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
