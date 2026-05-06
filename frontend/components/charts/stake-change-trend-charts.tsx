"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { formatDate } from "@/lib/format";

interface MonthlyTimelineItem {
  month: string;
  initials: number;
  amendments: number;
}

interface DirectionBreakdownItem {
  label: string;
  count: number;
}

interface StakeChangeTrendChartsProps {
  monthlyTimeline: MonthlyTimelineItem[];
  directionBreakdown: DirectionBreakdownItem[];
}

export function StakeChangeTrendCharts({ monthlyTimeline, directionBreakdown }: StakeChangeTrendChartsProps) {
  return (
    <div className="workspace-two-column-panels">
      <div className="metric-card workspace-chart-card">
        <div className="metric-label">Monthly Filing Pace</div>
        <div className="text-muted workspace-card-copy">
          More filings usually mean active stake updates or governance pressure.
        </div>
        <div className="workspace-chart-frame">
          <ResponsiveContainer>
            <BarChart data={monthlyTimeline} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
              <XAxis dataKey="month" stroke={CHART_AXIS_COLOR} tick={chartTick(11)} />
              <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick(11)} allowDecimals={false} />
              <Tooltip
                {...RECHARTS_TOOLTIP_PROPS}
                formatter={(value: number, name: string) => [value.toLocaleString(), name === "amendments" ? "Amendments" : "Initial filings"]}
              />
              <Bar dataKey="initials" name="Initial filings" stackId="filings" fill="var(--accent)" radius={[4, 4, 0, 0]} />
              <Bar dataKey="amendments" name="Amendments" stackId="filings" fill="#FFB020" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="metric-card workspace-chart-card">
        <div className="metric-label">Direction Breakdown</div>
        <div className="text-muted workspace-card-copy">
          Shows if disclosed ownership is mostly increasing, decreasing, or unclear.
        </div>
        <div className="workspace-chart-frame">
          <ResponsiveContainer>
            <BarChart data={directionBreakdown} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
              <XAxis dataKey="label" stroke={CHART_AXIS_COLOR} tick={chartTick(11)} interval={0} />
              <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick(11)} allowDecimals={false} />
              <Tooltip {...RECHARTS_TOOLTIP_PROPS} formatter={(value: number) => value.toLocaleString()} />
              <Bar dataKey="count" name="Filings" fill="#5EEA9D" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
