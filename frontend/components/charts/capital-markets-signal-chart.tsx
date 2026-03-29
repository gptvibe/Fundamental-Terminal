"use client";

import { useMemo } from "react";
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { CHART_AXIS_COLOR, CHART_GRID_COLOR, CHART_LEGEND_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { buildCapitalMarketsSignalSeries } from "@/lib/financial-chart-transforms";
import { formatCompactNumber } from "@/lib/format";
import type { FilingEventPayload, FinancialPayload } from "@/lib/types";

export function CapitalMarketsSignalChart({ financials, events }: { financials: FinancialPayload[]; events: FilingEventPayload[] }) {
  const data = useMemo(() => buildCapitalMarketsSignalSeries(financials, events), [events, financials]);

  if (!data.length) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 220 }}>
        <div className="grid-empty-kicker">Capital markets</div>
        <div className="grid-empty-title">No financing signal history yet</div>
        <div className="grid-empty-copy">This chart fills in once the cache includes debt-change fields or financing-related current reports.</div>
      </div>
    );
  }

  return (
    <div style={{ width: "100%", height: 320 }}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 16, left: 4, bottom: 8 }}>
          <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
          <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
          <YAxis yAxisId="events" stroke={CHART_AXIS_COLOR} tick={chartTick()} allowDecimals={false} width={46} />
          <YAxis yAxisId="debt" orientation="right" stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatCompactNumber(Number(value))} width={72} />
          <Tooltip
            {...RECHARTS_TOOLTIP_PROPS}
            formatter={(value: number, name: string) => (name === "Financing Events" ? String(value) : formatCompactNumber(value))}
          />
          <Legend formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}>{value}</span>} />
          <Bar yAxisId="events" dataKey="financingEvents" name="Financing Events" fill="var(--warning)" radius={[2, 2, 0, 0]} />
          <Line yAxisId="debt" type="monotone" dataKey="debtChanges" name="Debt Changes" stroke="var(--accent)" strokeWidth={2.4} dot={{ r: 3, fill: "var(--accent)" }} connectNulls isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
