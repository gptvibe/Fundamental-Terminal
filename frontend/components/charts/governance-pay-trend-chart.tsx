"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { RECHARTS_TOOLTIP_PROPS, CHART_GRID_COLOR, chartTick } from "@/lib/chart-theme";
import { formatCompactNumber } from "@/lib/format";

interface GovernancePayTrendChartProps {
  data: { year: number; total: number }[];
}

export function GovernancePayTrendChart({ data }: GovernancePayTrendChartProps) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_COLOR} vertical={false} />
        <XAxis dataKey="year" tick={chartTick()} axisLine={false} tickLine={false} />
        <YAxis
          tick={chartTick()}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) => formatCompactNumber(v) ?? ""}
        />
        <Tooltip
          {...RECHARTS_TOOLTIP_PROPS}
          formatter={(value: number) => [`$${Math.round(value).toLocaleString()}`, "Peak Total"]}
        />
        <Bar dataKey="total" fill="var(--positive)" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
