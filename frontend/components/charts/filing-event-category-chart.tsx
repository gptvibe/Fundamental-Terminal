"use client";

import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { CHART_AXIS_COLOR, CHART_GRID_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import type { FilingEventPayload } from "@/lib/types";

const CATEGORY_COLORS: Record<string, string> = {
  Earnings: "#00E5FF",
  Accounting: "#F97316",
  Leadership: "#FFD700",
  Deal: "#FF6B6B",
  Financing: "#7CFFCB",
  "Capital Markets": "#00FF41",
  "General Update": "#94A3B8",
  Other: "#C084FC"
};

export function FilingEventCategoryChart({ events }: { events: FilingEventPayload[] }) {
  const data = useMemo(() => buildChartData(events), [events]);

  if (!data.length) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 220 }}>
        <div className="grid-empty-kicker">Event intelligence</div>
        <div className="grid-empty-title">No 8-K events yet</div>
        <div className="grid-empty-copy">This chart fills in once SEC submissions include current reports for the company.</div>
      </div>
    );
  }

  return (
    <div style={{ width: "100%", height: 300 }}>
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
          <XAxis dataKey="category" stroke={CHART_AXIS_COLOR} tick={chartTick(11)} interval={0} angle={-14} textAnchor="end" height={62} />
          <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} allowDecimals={false} width={48} />
          <Tooltip {...RECHARTS_TOOLTIP_PROPS} />
          <Bar dataKey="count" name="Events" radius={[6, 6, 0, 0]}>
            {data.map((entry) => (
              <Cell key={entry.category} fill={CATEGORY_COLORS[entry.category] ?? CATEGORY_COLORS.Other} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function buildChartData(events: FilingEventPayload[]) {
  const grouped = new Map<string, number>();
  for (const event of events) {
    grouped.set(event.category, (grouped.get(event.category) ?? 0) + 1);
  }
  return [...grouped.entries()]
    .map(([category, count]) => ({ category, count }))
    .sort((left, right) => right.count - left.count || left.category.localeCompare(right.category));
}